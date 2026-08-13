-- Escalation: a technician can flag a ticket as escalated, which bumps its
-- priority and notifies the rest of the assigned team.
ALTER TABLE tickets ADD COLUMN is_escalated BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE tickets ADD COLUMN escalated_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN escalated_by_id UUID REFERENCES users(id);
ALTER TABLE tickets ADD COLUMN escalation_reason TEXT;

ALTER TYPE notification_event ADD VALUE 'ticket_escalated';
