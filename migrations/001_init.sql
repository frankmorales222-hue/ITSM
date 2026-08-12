-- Phase 1 IT Support schema
-- See it-support-phase1-data-model.md for full rationale.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

CREATE TYPE request_type AS ENUM ('incident', 'assistance');
CREATE TYPE submission_channel AS ENUM ('web', 'email', 'technician');
CREATE TYPE impact_level AS ENUM ('high', 'medium', 'low');
CREATE TYPE urgency_level AS ENUM ('high', 'medium', 'low');
CREATE TYPE priority_level AS ENUM ('critical', 'high', 'medium', 'normal', 'low');
CREATE TYPE ticket_status AS ENUM (
    'open', 'assigned', 'in_progress',
    'waiting_on_you', 'waiting_on_vendor', 'on_hold',
    'pending_verification', 'resolved', 'closed', 'cancelled'
);
CREATE TYPE notification_channel AS ENUM ('email', 'in_app');
CREATE TYPE notification_event AS ENUM (
    'ticket_created', 'ticket_assigned', 'technician_replied',
    'requester_replied', 'status_changed', 'ticket_resolved',
    'ticket_closed', 'ticket_reopened'
);

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_number     TEXT UNIQUE,
    display_name        TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE,
    phone               TEXT,
    department          TEXT,
    job_title           TEXT,
    manager_id          UUID REFERENCES users(id),
    location            TEXT,
    time_zone           TEXT DEFAULT 'America/New_York',
    is_technician       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE teams (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE team_members (
    team_id             UUID NOT NULL REFERENCES teams(id),
    user_id             UUID NOT NULL REFERENCES users(id),
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE categories (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE SEQUENCE ticket_number_seq START 1;

CREATE TABLE tickets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number       TEXT NOT NULL UNIQUE,
    request_type        request_type NOT NULL DEFAULT 'incident',
    submission_channel  submission_channel NOT NULL,

    requester_id        UUID NOT NULL REFERENCES users(id),
    opened_by_id        UUID NOT NULL REFERENCES users(id),

    subject             TEXT NOT NULL,
    description         TEXT NOT NULL,

    category_id         UUID REFERENCES categories(id),

    impact              impact_level,
    urgency             urgency_level,
    priority            priority_level NOT NULL DEFAULT 'normal',
    priority_overridden BOOLEAN NOT NULL DEFAULT FALSE,
    priority_override_reason TEXT,

    status              ticket_status NOT NULL DEFAULT 'open',

    assigned_team_id    UUID REFERENCES teams(id),
    assigned_tech_id    UUID REFERENCES users(id),

    reopen_count        INTEGER NOT NULL DEFAULT 0,

    resolution_summary  TEXT,
    resolved_at         TIMESTAMPTZ,
    resolved_by_id      UUID REFERENCES users(id),
    closed_at           TIMESTAMPTZ,
    closed_by_id        UUID REFERENCES users(id),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tickets_requester ON tickets(requester_id);
CREATE INDEX idx_tickets_assigned_tech ON tickets(assigned_tech_id);
CREATE INDEX idx_tickets_status ON tickets(status);

CREATE TABLE ticket_replies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           UUID NOT NULL REFERENCES tickets(id),
    author_id           UUID NOT NULL REFERENCES users(id),
    body                TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ticket_notes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           UUID NOT NULL REFERENCES tickets(id),
    author_id           UUID NOT NULL REFERENCES users(id),
    body                TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ticket_attachments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           UUID NOT NULL REFERENCES tickets(id),
    reply_id            UUID REFERENCES ticket_replies(id),
    uploaded_by_id      UUID NOT NULL REFERENCES users(id),
    file_name           TEXT NOT NULL,
    storage_path        TEXT NOT NULL,
    content_type        TEXT NOT NULL,
    size_bytes          BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ticket_status_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           UUID NOT NULL REFERENCES tickets(id),
    changed_by_id       UUID REFERENCES users(id),
    from_status         ticket_status,
    to_status           ticket_status NOT NULL,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assignment_state (
    team_id                 UUID PRIMARY KEY REFERENCES teams(id),
    last_assigned_user_id   UUID REFERENCES users(id),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ticket_notifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           UUID NOT NULL REFERENCES tickets(id),
    recipient_id        UUID NOT NULL REFERENCES users(id),
    event               notification_event NOT NULL,
    channel             notification_channel NOT NULL,
    sent_at             TIMESTAMPTZ,
    read_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inbound_email_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id          TEXT NOT NULL UNIQUE,
    in_reply_to         TEXT,
    from_address        TEXT NOT NULL,
    ticket_id           UUID REFERENCES tickets(id),
    processed_status    TEXT NOT NULL DEFAULT 'pending',
    raw_storage_path    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed: starter categories (flat list, phase 1)
INSERT INTO categories (name, sort_order) VALUES
    ('Hardware', 1),
    ('Software', 2),
    ('Account & Password', 3),
    ('Access Request', 4),
    ('Equipment Request', 5),
    ('Email & Collaboration', 6),
    ('Network & Connectivity', 7),
    ('Security Concern', 8),
    ('Other', 9);

-- Seed: one default team so round-robin has somewhere to assign to
INSERT INTO teams (name, description) VALUES ('IT Support', 'Default phase-1 support queue');
