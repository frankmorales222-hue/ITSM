"""Curated Smart Self-Service matching and outcome workflow.

This module intentionally uses deterministic retrieval over administrator-approved
articles.  It never trains on, or sends, raw ticket conversations.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .admin_services import evaluate_group
from .models import (
    AuditEvent, ConfigItem, KnowledgeArticle, KnowledgeArticleVersion, Role,
    SelfServiceAttempt, Ticket, TicketHistory, TicketMessage, TicketStatus, User, now,
)
from .services import (
    audit, can_view_ticket, notification_delivery_enabled,
    notify, outbound_email_delivery_enabled,
)


POLICY_SECTION = "smart_self_service"
POLICY_NAME = "Smart Self-Service"
DEFAULT_POLICY: dict[str, Any] = {
    "enabled": False,
    "mode": "suggest_to_tech",
    "confidence_threshold": 60,
    "waiting_hours": 48,
    "safe_categories": ["General", "Hardware", "Software", "Network"],
    "excluded_categories": ["Security", "Access", "Change", "Outage"],
}
VALID_MODES = {"suggest_to_tech", "auto_send"}
VALID_OUTCOMES = {"fixed", "not_fixed", "live_help"}
OPEN_ATTEMPT_STATUSES = {"suggested", "offered"}
EMAIL_OUTCOME_COMMANDS = {
    "FIXED": "fixed",
    "IT WORKED": "fixed",
    "DID NOT WORK": "not_fixed",
    "REQUEST LIVE HELP": "live_help",
}
STOP_WORDS = {
    "about", "after", "again", "also", "been", "before", "being", "cannot", "could",
    "does", "from", "have", "into", "issue", "need", "please", "request", "some", "that",
    "their", "there", "these", "they", "this", "ticket", "unable", "user", "with", "would",
}
SENSITIVE_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"),
    re.compile(r"\b(?:password|passcode|secret|token|api[_ -]?key)\s*[:=]\s*\S+", re.I),
)


def policy_for(db: Session) -> dict[str, Any]:
    item = db.scalar(select(ConfigItem).where(
        ConfigItem.section == POLICY_SECTION, ConfigItem.name == POLICY_NAME,
    ))
    value = dict(DEFAULT_POLICY)
    if item:
        value.update(item.value or {})
    value["enabled"] = bool(value.get("enabled", False))
    value["mode"] = value.get("mode") if value.get("mode") in VALID_MODES else "suggest_to_tech"
    try:
        value["confidence_threshold"] = min(100, max(1, int(value.get("confidence_threshold", 60))))
        value["waiting_hours"] = min(720, max(1, int(value.get("waiting_hours", 48))))
    except (TypeError, ValueError):
        value["confidence_threshold"], value["waiting_hours"] = 60, 48
    for key in ("safe_categories", "excluded_categories"):
        value[key] = [str(entry).strip() for entry in value.get(key, []) if str(entry).strip()]
    return value


def save_policy(db: Session, values: dict[str, Any], actor: User) -> dict[str, Any]:
    merged = dict(policy_for(db))
    merged.update({key: values[key] for key in DEFAULT_POLICY if key in values})
    # Normalize through the same reader without relying on uncommitted ORM state.
    merged["enabled"] = bool(merged.get("enabled", False))
    if merged.get("mode") not in VALID_MODES:
        raise ValueError("Mode must be suggest_to_tech or auto_send")
    merged["confidence_threshold"] = min(100, max(1, int(merged.get("confidence_threshold", 60))))
    merged["waiting_hours"] = min(720, max(1, int(merged.get("waiting_hours", 48))))
    for key in ("safe_categories", "excluded_categories"):
        merged[key] = [str(entry).strip() for entry in merged.get(key, []) if str(entry).strip()]
    item = db.scalar(select(ConfigItem).where(
        ConfigItem.section == POLICY_SECTION, ConfigItem.name == POLICY_NAME,
    ))
    previous = dict(item.value or {}) if item else None
    if not item:
        item = ConfigItem(section=POLICY_SECTION, name=POLICY_NAME, value=merged,
                          description="Approved knowledge suggestions for low-risk requests.")
        db.add(item)
        db.flush()
    else:
        item.value = merged
    audit(db, "smart_self_service.policy_updated", "config_item", item.id, actor.id,
          previous=previous, new=merged)
    return merged


def article_snapshot(article: KnowledgeArticle) -> dict[str, Any]:
    return {
        "id": article.id, "title": article.title, "summary": article.problem_summary,
        "steps": list(article.steps or []), "tags": list(article.tags or []),
        "category": article.category, "applicability": dict(article.applicability or {}),
        "risk_level": article.risk_level, "status": article.status,
        "auto_send_allowed": bool(article.auto_send_allowed), "version": article.version,
    }


def add_article_version(db: Session, article: KnowledgeArticle, actor_id: int | None) -> None:
    db.flush()
    db.add(KnowledgeArticleVersion(article_id=article.id, version=article.version,
                                   snapshot=article_snapshot(article), created_by_id=actor_id))


def sanitize_knowledge_text(value: str) -> str:
    text = str(value or "")[:12000]
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub("[removed]", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9+#.-]{2,}", value.lower())
            if token not in STOP_WORDS and not token.isdigit()}


def exclusion_reason(ticket: Ticket, policy: dict[str, Any]) -> str | None:
    if not policy.get("enabled"):
        return "disabled"
    if ticket.restricted:
        return "restricted_ticket"
    if str(ticket.priority).lower() in {"critical", "high"}:
        return "priority_excluded"
    combined = " ".join(filter(None, [ticket.category, ticket.subcategory, ticket.request_type,
                                       ticket.subject, ticket.description])).lower()
    blocked = {value.lower() for value in policy.get("excluded_categories", [])}
    if any(value and (value == str(ticket.category).lower() or value in combined) for value in blocked):
        return "category_excluded"
    if any(term in combined for term in ("security incident", "data breach", "ransomware", "outage",
                                         "service down", "privileged access", "change request")):
        return "risk_excluded"
    snapshot = ticket.requester_snapshot or {}
    if any(bool(snapshot.get(key)) for key in ("vip", "is_vip", "executive")):
        return "vip_requester"
    safe = {value.lower() for value in policy.get("safe_categories", [])}
    if safe and str(ticket.category).lower() not in safe:
        return "category_not_allowlisted"
    return None


def _applicable(article: KnowledgeArticle, ticket: Ticket) -> tuple[bool, list[str]]:
    applicability = article.applicability or {}
    categories = {str(value).lower() for value in applicability.get("categories", [])}
    request_types = {str(value).lower() for value in applicability.get("request_types", [])}
    if categories and str(ticket.category).lower() not in categories:
        return False, ["category did not match"]
    if request_types and str(ticket.request_type).lower() not in request_types:
        return False, ["request type did not match"]
    conditions = applicability.get("conditions")
    if conditions:
        sample = {
            "category": ticket.category, "subcategory": ticket.subcategory or "",
            "request_type": ticket.request_type, "priority": ticket.priority,
            "subject": ticket.subject, "description": ticket.description,
            "ticket": {"category": ticket.category, "subcategory": ticket.subcategory or "",
                       "request_type": ticket.request_type, "priority": ticket.priority,
                       "subject": ticket.subject},
        }
        return evaluate_group(conditions, sample)
    return True, []


def score_article(article: KnowledgeArticle, ticket: Ticket) -> tuple[int, dict[str, Any]]:
    applicable, trace = _applicable(article, ticket)
    if not applicable:
        return 0, {"applicability": trace}
    query_tokens = _tokens(" ".join(filter(None, [ticket.subject, ticket.description,
                                                   ticket.category, ticket.subcategory])))
    title_tokens = _tokens(article.title)
    body_tokens = _tokens(" ".join([article.problem_summary, " ".join(article.tags or [])]))
    matched_title = sorted(query_tokens & title_tokens)
    matched_body = sorted(query_tokens & body_tokens)
    matched = set(matched_title) | set(matched_body)
    if not matched:
        return 0, {"matched_tokens": [], "applicability": trace}
    score = min(100, len(matched_title) * 20 + len(matched_body) * 10)
    if article.category.lower() == str(ticket.category).lower():
        score += 25
    score = min(100, score)
    return score, {"matched_tokens": sorted(matched), "title_matches": matched_title,
                   "category_match": article.category.lower() == str(ticket.category).lower(),
                   "applicability": trace}


def best_match(db: Session, ticket: Ticket, policy: dict[str, Any] | None = None):
    policy = policy or policy_for(db)
    reason = exclusion_reason(ticket, policy)
    if reason:
        return None, 0, {"excluded": reason}
    articles = db.scalars(select(KnowledgeArticle).where(
        KnowledgeArticle.status == "published", KnowledgeArticle.risk_level == "low",
    ).order_by(KnowledgeArticle.id).limit(1000)).all()
    ranked = [(score_article(article, ticket), article) for article in articles]
    ranked = [(score, why, article) for (score, why), article in ranked if score > 0]
    if not ranked:
        return None, 0, {"reason": "no_match"}
    score, why, article = max(ranked, key=lambda row: (row[0], -row[2].id))
    if score < policy["confidence_threshold"]:
        return None, score, {**why, "reason": "below_threshold"}
    return article, score, why


def render_steps(snapshot: dict[str, Any]) -> str:
    steps = [sanitize_knowledge_text(str(step)) for step in snapshot.get("steps", [])]
    lines = [f"{index}. {step}" for index, step in enumerate(steps, 1) if step]
    return "\n".join(lines)


def guidance_body(attempt: SelfServiceAttempt) -> str:
    snapshot = attempt.article_snapshot or {}
    return (f"{sanitize_knowledge_text(snapshot.get('summary', ''))}\n\n"
            f"Try these steps:\n{render_steps(snapshot)}\n\n"
            "If this did not fix the issue, reply DID NOT WORK or request live help in the ticket.")


def add_public_guidance(db: Session, ticket: Ticket, attempt: SelfServiceAttempt) -> None:
    """Persist exactly what the requester was sent in the durable ticket timeline."""
    db.add(TicketMessage(ticket_id=ticket.id, author_id=None, body=guidance_body(attempt),
                         kind="public", source="self_service"))


def email_outcome_command(body: str) -> str | None:
    """Recognize only explicit first-line commands to avoid interpreting prose."""
    first_line = next((line.strip() for line in str(body or "").splitlines() if line.strip()), "")
    normalized = re.sub(r"[.!]+$", "", first_line).strip().upper()
    return EMAIL_OUTCOME_COMMANDS.get(normalized)


def record_email_outcome(db: Session, ticket: Ticket, requester: User,
                         body: str) -> SelfServiceAttempt | None:
    outcome = email_outcome_command(body)
    if not outcome:
        return None
    attempt = db.scalar(select(SelfServiceAttempt).where(
        SelfServiceAttempt.ticket_id == ticket.id,
        SelfServiceAttempt.status == "offered",
    ).order_by(SelfServiceAttempt.created_at.desc()))
    return record_outcome(db, ticket, attempt, requester, outcome, "email") if attempt else None


def evaluate_ticket(db: Session, ticket: Ticket) -> SelfServiceAttempt | None:
    policy = policy_for(db)
    article, score, reason = best_match(db, ticket, policy)
    if not article:
        return None
    existing = db.scalar(select(SelfServiceAttempt).where(
        SelfServiceAttempt.ticket_id == ticket.id, SelfServiceAttempt.article_id == article.id,
        SelfServiceAttempt.article_version == article.version,
    ))
    if existing:
        return existing
    snapshot = article_snapshot(article)
    mode = policy["mode"]
    if mode == "auto_send" and not (article.auto_send_allowed and article.approved_by_id and article.approved_at):
        mode = "suggest_to_tech"
        reason = {**reason, "downgraded": "article_not_approved_for_auto_send"}
    attempt = SelfServiceAttempt(ticket_id=ticket.id, article_id=article.id,
                                 article_version=article.version, score=score,
                                 match_reason=reason, article_snapshot=snapshot,
                                 status="offered" if mode == "auto_send" else "suggested",
                                 offered_at=now())
    try:
        # A savepoint keeps a duplicate evaluation race from rolling back unrelated
        # worker changes (mail intake, SLA work, or notifications).
        with db.begin_nested():
            db.add(attempt)
            db.flush()
    except IntegrityError:
        return db.scalar(select(SelfServiceAttempt).where(
            SelfServiceAttempt.ticket_id == ticket.id, SelfServiceAttempt.article_id == article.id,
            SelfServiceAttempt.article_version == article.version,
        ))
    subject = f"[{ticket.number}] Suggested solution: {article.title}"
    body = f"{article.problem_summary}\n\nTry these steps:\n{render_steps(snapshot)}"
    if mode == "auto_send":
        if notification_delivery_enabled(db) and outbound_email_delivery_enabled(db):
            notify(db, ticket.requester_id, "self_service.solution_offered", subject,
                   guidance_body(attempt),
                   ticket.id, email=True)
            add_public_guidance(db, ticket, attempt)
            ticket.status = TicketStatus.WAITING_USER
            ticket.next_action_owner = "Requester"
            ticket.next_action = "Try the suggested solution"
        else:
            attempt.status = "suppressed"
            attempt.match_reason = {**reason, "suppressed": "notification_or_email_disabled"}
    else:
        notify(db, ticket.assigned_user_id, "self_service.technician_suggestion", subject,
               body, ticket.id, email=False)
    audit(db, f"smart_self_service.{attempt.status}", "self_service_attempt", attempt.id,
          new={"ticket_id": ticket.id, "ticket_number": ticket.number,
               "article_id": article.id, "article_version": article.version,
               "score": score, "mode": mode})
    return attempt


def return_unanswered_to_it(db: Session) -> int:
    """Return expired offers to IT once; never silently close a requester ticket."""
    policy = policy_for(db)
    if not policy["enabled"]:
        return 0
    cutoff = now() - timedelta(hours=policy["waiting_hours"])
    rows = db.scalars(select(SelfServiceAttempt).where(
        SelfServiceAttempt.status == "offered",
        SelfServiceAttempt.offered_at.is_not(None),
        SelfServiceAttempt.offered_at <= cutoff,
    ).order_by(SelfServiceAttempt.offered_at).limit(500)).all()
    returned = 0
    for attempt in rows:
        ticket = db.get(Ticket, attempt.ticket_id)
        if not ticket:
            attempt.status = "timed_out"; attempt.responded_at = now(); attempt.outcome_source = "timeout"
            continue
        attempt.status = "timed_out"; attempt.responded_at = now(); attempt.outcome_source = "timeout"
        if ticket.status == TicketStatus.WAITING_USER:
            ticket.status = TicketStatus.IN_PROGRESS if ticket.assigned_user_id else TicketStatus.NEW
        ticket.next_action_owner = ticket.assigned_user.display_name if ticket.assigned_user else "IT"
        ticket.next_action = "Follow up after unanswered self-service suggestion"
        body = "The requester did not respond to the suggested solution before the configured timeout. The ticket was returned to IT."
        db.add(TicketMessage(ticket_id=ticket.id, author_id=None, body=body,
                             kind="public", source="self_service"))
        notify(db, ticket.assigned_user_id, "self_service.timed_out",
               f"[{ticket.number}] Self-service follow-up required: {ticket.subject}", body,
               ticket.id, email=True)
        audit(db, "smart_self_service.timed_out", "self_service_attempt", attempt.id,
              new={"ticket_id": ticket.id, "ticket_number": ticket.number,
                   "waiting_hours": policy["waiting_hours"]})
        returned += 1
    return returned


def record_outcome(db: Session, ticket: Ticket, attempt: SelfServiceAttempt, requester: User,
                   outcome: str, source: str = "web") -> SelfServiceAttempt:
    if outcome not in VALID_OUTCOMES:
        raise ValueError("Outcome must be fixed, not_fixed, or live_help")
    if requester.id != ticket.requester_id:
        raise PermissionError("Only the requester can respond to this suggestion")
    if attempt.ticket_id != ticket.id:
        raise ValueError("Suggestion does not belong to this ticket")
    if attempt.status not in OPEN_ATTEMPT_STATUSES:
        return attempt
    attempt.status = outcome
    attempt.responded_at = now()
    attempt.outcome_source = source
    if outcome == "fixed":
        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = now()
        ticket.resolution_summary = ticket.resolution_summary or f"Resolved using approved article: {attempt.article_snapshot.get('title', '')}"
        body = f"{requester.display_name} confirmed that the suggested solution fixed the issue."
        event = "self_service.fixed"
        notify(db, ticket.assigned_user_id, event,
               f"[{ticket.number}] Requester confirmed resolution: {ticket.subject}", body,
               ticket.id, email=True)
    else:
        ticket.status = TicketStatus.IN_PROGRESS if ticket.assigned_user_id else TicketStatus.NEW
        ticket.closed_at = None
        ticket.next_action_owner = ticket.assigned_user.display_name if ticket.assigned_user else "IT"
        ticket.next_action = "Requester needs live assistance" if outcome == "live_help" else "Suggested steps did not resolve the issue"
        body = (f"{requester.display_name} requested live help after trying the suggested solution."
                if outcome == "live_help" else
                f"{requester.display_name} reported that the suggested solution did not work.")
        event = "self_service.live_help_requested" if outcome == "live_help" else "self_service.not_fixed"
        notify(db, ticket.assigned_user_id, event,
               f"[{ticket.number}] Requester needs assistance: {ticket.subject}", body,
               ticket.id, email=True)
    db.add(TicketMessage(ticket_id=ticket.id, author_id=requester.id, body=body,
                         kind="public", source=source))
    db.add(TicketHistory(ticket_id=ticket.id, event_type=event, actor_id=requester.id,
                         new_value={"attempt_id": attempt.id, "outcome": outcome}))
    audit(db, event, "self_service_attempt", attempt.id, requester.id,
          new={"ticket_id": ticket.id, "ticket_number": ticket.number, "outcome": outcome,
               "source": source})
    return attempt


def article_usage(db: Session, article_id: int) -> tuple[int, int]:
    total = db.scalar(select(func.count(SelfServiceAttempt.id)).where(
        SelfServiceAttempt.article_id == article_id)) or 0
    successful = db.scalar(select(func.count(SelfServiceAttempt.id)).where(
        SelfServiceAttempt.article_id == article_id, SelfServiceAttempt.status == "fixed")) or 0
    return successful, total
