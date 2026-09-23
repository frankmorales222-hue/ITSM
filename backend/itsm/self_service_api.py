"""HTTP API for curated Smart Self-Service."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import KnowledgeArticle, KnowledgeArticleVersion, Role, SelfServiceAttempt, Ticket, TicketStatus, User, now
from .security import current_user, require_roles
from .self_service import (
    add_article_version, add_public_guidance, article_snapshot, article_usage, guidance_body,
    policy_for, record_outcome, sanitize_knowledge_text, save_policy,
)
from .services import audit, can_view_ticket, notify

router = APIRouter(prefix="/api", tags=["Smart Self-Service"])


class PolicyIn(BaseModel):
    enabled: bool = False
    mode: str = Field(default="suggest_to_tech", pattern=r"^(suggest_to_tech|auto_send)$")
    confidence_threshold: int = Field(default=60, ge=1, le=100)
    waiting_hours: int = Field(default=48, ge=1, le=720)
    safe_categories: list[str] = Field(default_factory=list, max_length=50)
    excluded_categories: list[str] = Field(default_factory=list, max_length=50)


class ArticleIn(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    summary: str = Field(min_length=10, max_length=12000)
    steps: list[str] = Field(min_length=1, max_length=30)
    category: str = Field(default="General", min_length=2, max_length=100)
    status: str = Field(default="draft", pattern=r"^(draft|published|archived)$")
    tags: list[str] = Field(default_factory=list, max_length=50)
    applicability: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(default="low", pattern=r"^(low|medium|high)$")
    auto_send_allowed: bool = False


class OutcomeIn(BaseModel):
    outcome: str = Field(pattern=r"^(fixed|not_fixed|live_help)$")


def _article_dict(db: Session, item: KnowledgeArticle) -> dict[str, Any]:
    successful, total = article_usage(db, item.id)
    return {
        "id": item.id, "title": item.title, "summary": item.problem_summary,
        "steps": item.steps or [], "tags": item.tags or [], "category": item.category,
        "applicability": item.applicability or {}, "risk_level": item.risk_level,
        "status": item.status, "auto_send_allowed": item.auto_send_allowed,
        "version": item.version, "successful_uses": successful, "total_uses": total,
        "approved_by_id": item.approved_by_id, "approved_at": item.approved_at,
        "updated_at": item.updated_at,
    }


def _assign_article(item: KnowledgeArticle, payload: ArticleIn, *, allow_publish: bool = False) -> None:
    if payload.status == "published" and not allow_publish:
        raise HTTPException(422, "Use the publish action after reviewing the article")
    item.title = sanitize_knowledge_text(payload.title)[:240]
    item.problem_summary = sanitize_knowledge_text(payload.summary)
    item.steps = [sanitize_knowledge_text(step)[:2000] for step in payload.steps if sanitize_knowledge_text(step)]
    if not item.steps:
        raise HTTPException(422, "At least one non-empty troubleshooting step is required")
    item.category = payload.category.strip()
    item.tags = [sanitize_knowledge_text(tag)[:80] for tag in payload.tags if sanitize_knowledge_text(tag)]
    item.applicability = payload.applicability
    item.risk_level = payload.risk_level
    item.auto_send_allowed = bool(payload.auto_send_allowed)
    item.status = payload.status
    if item.risk_level != "low":
        item.auto_send_allowed = False


@router.get("/admin/smart-self-service")
def admin_overview(user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                   db: Session = Depends(get_db)):
    rows = db.scalars(select(KnowledgeArticle).order_by(KnowledgeArticle.updated_at.desc())).all()
    return {"settings": policy_for(db), "articles": [_article_dict(db, item) for item in rows]}


@router.put("/admin/smart-self-service")
def admin_save_policy(payload: PolicyIn,
                      user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                      db: Session = Depends(get_db)):
    try:
        settings = save_policy(db, payload.model_dump(), user)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {"settings": settings,
            "articles": [_article_dict(db, item) for item in db.scalars(
                select(KnowledgeArticle).order_by(KnowledgeArticle.updated_at.desc())).all()]}


@router.post("/admin/smart-self-service/articles", status_code=201)
def create_article(payload: ArticleIn,
                   user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                   db: Session = Depends(get_db)):
    if payload.status == "published":
        raise HTTPException(422, "Create the article as a draft, then publish it")
    item = KnowledgeArticle(title="", problem_summary="", steps=[], tags=[], category="General",
                            applicability={}, risk_level="low", status="draft",
                            auto_send_allowed=False, created_by_id=user.id)
    # Editing a published article creates a new draft version that must be
    # explicitly reviewed and published again.
    _assign_article(item, payload, allow_publish=True)
    db.add(item); db.flush(); add_article_version(db, item, user.id)
    audit(db, "knowledge_article.created", "knowledge_article", item.id, user.id,
          new=article_snapshot(item))
    db.commit(); db.refresh(item)
    return _article_dict(db, item)


@router.patch("/admin/smart-self-service/articles/{article_id}")
def update_article(article_id: int, payload: ArticleIn,
                   user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                   db: Session = Depends(get_db)):
    item = db.get(KnowledgeArticle, article_id)
    if not item:
        raise HTTPException(404, "Knowledge article not found")
    previous = article_snapshot(item)
    _assign_article(item, payload)
    item.version += 1
    item.approved_by_id = None; item.approved_at = None
    if item.status == "published":
        item.status = "draft"
    add_article_version(db, item, user.id)
    audit(db, "knowledge_article.updated", "knowledge_article", item.id, user.id,
          previous=previous, new=article_snapshot(item))
    db.commit(); db.refresh(item)
    return _article_dict(db, item)


@router.post("/admin/smart-self-service/articles/{article_id}/publish")
def publish_article(article_id: int,
                    user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                    db: Session = Depends(get_db)):
    item = db.get(KnowledgeArticle, article_id)
    if not item or item.status == "archived":
        raise HTTPException(404, "Knowledge article not found")
    if not item.steps or not item.problem_summary:
        raise HTTPException(422, "Complete the summary and troubleshooting steps before publishing")
    previous = article_snapshot(item)
    item.version += 1; item.status = "published"
    item.approved_by_id = user.id; item.approved_at = now()
    if item.risk_level != "low":
        item.auto_send_allowed = False
    add_article_version(db, item, user.id)
    audit(db, "knowledge_article.published", "knowledge_article", item.id, user.id,
          previous=previous, new=article_snapshot(item))
    db.commit(); db.refresh(item)
    return _article_dict(db, item)


@router.delete("/admin/smart-self-service/articles/{article_id}")
def archive_article(article_id: int,
                    user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                    db: Session = Depends(get_db)):
    item = db.get(KnowledgeArticle, article_id)
    if not item:
        raise HTTPException(404, "Knowledge article not found")
    previous = article_snapshot(item)
    item.status = "archived"; item.auto_send_allowed = False
    audit(db, "knowledge_article.archived", "knowledge_article", item.id, user.id,
          previous=previous, new=article_snapshot(item))
    db.commit(); db.refresh(item)
    return _article_dict(db, item)


@router.get("/admin/smart-self-service/articles/{article_id}/versions")
def article_versions(article_id: int,
                     user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                     db: Session = Depends(get_db)):
    if not db.get(KnowledgeArticle, article_id):
        raise HTTPException(404, "Knowledge article not found")
    rows = db.scalars(select(KnowledgeArticleVersion).where(
        KnowledgeArticleVersion.article_id == article_id,
    ).order_by(KnowledgeArticleVersion.version.desc())).all()
    return [{"id": row.id, "version": row.version, "snapshot": row.snapshot,
             "created_by_id": row.created_by_id, "created_at": row.created_at} for row in rows]


@router.post("/admin/smart-self-service/articles/from-ticket/{ticket_id}", status_code=201)
def draft_from_ticket(ticket_id: int,
                      user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
                      db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(404, "Ticket not found")
    if not ticket.resolution_summary:
        raise HTTPException(422, "A resolution summary is required to create a draft")
    summary = sanitize_knowledge_text(ticket.subject)
    resolution = sanitize_knowledge_text(ticket.resolution_summary)
    steps = [line.strip(" -\t") for line in resolution.splitlines() if line.strip(" -\t")]
    item = KnowledgeArticle(title=summary[:240], problem_summary=summary,
                            steps=(steps or [resolution])[:30], tags=[], category=ticket.category,
                            applicability={"categories": [ticket.category]}, risk_level="low",
                            status="draft", auto_send_allowed=False, source_ticket_id=ticket.id,
                            created_by_id=user.id)
    db.add(item); db.flush(); add_article_version(db, item, user.id)
    audit(db, "knowledge_article.draft_created_from_ticket", "knowledge_article", item.id,
          user.id, new={"source_ticket_id": ticket.id, "version": item.version})
    db.commit(); db.refresh(item)
    return _article_dict(db, item)


def _attempt_dict(item: SelfServiceAttempt) -> dict[str, Any]:
    snap = item.article_snapshot or {}
    return {"id": item.id, "article_id": item.article_id, "title": snap.get("title", ""),
            "summary": snap.get("summary", ""), "steps": snap.get("steps", []),
            "confidence": item.score, "source_version": item.article_version,
            "sent_at": item.offered_at, "outcome": item.status}


@router.get("/tickets/{ticket_id}/self-service")
def ticket_self_service(ticket_id: int, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(404, "Ticket not found")
    item = db.scalar(select(SelfServiceAttempt).where(
        SelfServiceAttempt.ticket_id == ticket.id,
    ).order_by(SelfServiceAttempt.created_at.desc()))
    policy = policy_for(db)
    # Technician suggestions are internal until a technician explicitly sends one.
    if item and item.status == "suggested" and user.role == Role.END_USER:
        item = None
    return {"enabled": policy["enabled"], "status": item.status if item else "none",
            "suggestion": _attempt_dict(item) if item else None}


def _latest_actionable_attempt(db: Session, ticket_id: int) -> SelfServiceAttempt | None:
    return db.scalar(select(SelfServiceAttempt).where(
        SelfServiceAttempt.ticket_id == ticket_id,
        SelfServiceAttempt.status.in_(["suggested", "offered"]),
    ).order_by(SelfServiceAttempt.created_at.desc()))


@router.post("/tickets/{ticket_id}/self-service/{attempt_id}/send")
def send_technician_suggestion(ticket_id: int, attempt_id: int,
                               user: User = Depends(require_roles(
                                   Role.TECHNICIAN, Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN)),
                               db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    attempt = db.get(SelfServiceAttempt, attempt_id)
    if not ticket or not attempt or attempt.ticket_id != ticket.id or not can_view_ticket(user, ticket):
        raise HTTPException(404, "Self-service suggestion not found")
    if attempt.status != "suggested":
        raise HTTPException(409, "This suggestion is no longer awaiting technician review")
    snap = attempt.article_snapshot or {}
    notify(db, ticket.requester_id, "self_service.solution_offered",
           f"[{ticket.number}] Suggested solution: {snap.get('title', '')}",
           guidance_body(attempt),
           ticket.id, email=True)
    add_public_guidance(db, ticket, attempt)
    attempt.status = "offered"; attempt.offered_at = now()
    ticket.status = TicketStatus.WAITING_USER
    ticket.next_action_owner = "Requester"; ticket.next_action = "Try the suggested solution"
    audit(db, "smart_self_service.sent_by_technician", "self_service_attempt", attempt.id,
          user.id, new={"ticket_id": ticket.id, "article_id": attempt.article_id,
                        "article_version": attempt.article_version})
    db.commit(); db.refresh(attempt)
    return {"enabled": policy_for(db)["enabled"], "status": attempt.status,
            "suggestion": _attempt_dict(attempt)}


@router.post("/tickets/{ticket_id}/self-service")
def latest_ticket_self_service_outcome(ticket_id: int, payload: OutcomeIn,
                                       user: User = Depends(current_user),
                                       db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(404, "Self-service suggestion not found")
    attempt = _latest_actionable_attempt(db, ticket.id)
    if not attempt or attempt.status != "offered":
        raise HTTPException(404, "No active self-service suggestion was found")
    try:
        record_outcome(db, ticket, attempt, user, payload.outcome)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit(); db.refresh(attempt)
    return {"enabled": policy_for(db)["enabled"], "status": attempt.status,
            "suggestion": _attempt_dict(attempt)}


@router.post("/tickets/{ticket_id}/self-service/outcome")
def compatible_ticket_self_service_outcome(ticket_id: int, payload: OutcomeIn,
                                            user: User = Depends(current_user),
                                            db: Session = Depends(get_db)):
    return latest_ticket_self_service_outcome(ticket_id, payload, user, db)


@router.post("/tickets/{ticket_id}/self-service/{attempt_id}/outcome")
def ticket_self_service_outcome(ticket_id: int, attempt_id: int, payload: OutcomeIn,
                                user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    attempt = db.get(SelfServiceAttempt, attempt_id)
    if not ticket or not attempt or not can_view_ticket(user, ticket):
        raise HTTPException(404, "Self-service suggestion not found")
    if attempt.status != "offered":
        raise HTTPException(404, "No active self-service suggestion was found")
    try:
        record_outcome(db, ticket, attempt, user, payload.outcome)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit(); db.refresh(attempt)
    return {"enabled": policy_for(db)["enabled"], "status": attempt.status,
            "suggestion": _attempt_dict(attempt)}
