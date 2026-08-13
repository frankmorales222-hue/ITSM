-- SLA due date, computed from priority at ticket creation time.
ALTER TABLE tickets ADD COLUMN due_at TIMESTAMPTZ;

CREATE INDEX idx_tickets_due_at ON tickets(due_at);
