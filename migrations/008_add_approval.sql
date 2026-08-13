-- Manager approval for request categories that need sign-off (Access
-- Request, Equipment Request) before a technician can resolve/close them.
-- NULL approval_status means the ticket never needed approval in the
-- first place (most tickets).
CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected');

ALTER TABLE tickets ADD COLUMN approval_status approval_status;
ALTER TABLE tickets ADD COLUMN approved_by_id UUID REFERENCES users(id);
ALTER TABLE tickets ADD COLUMN approved_at TIMESTAMPTZ;
ALTER TABLE tickets ADD COLUMN approval_note TEXT;

ALTER TYPE notification_event ADD VALUE 'ticket_approved';
ALTER TYPE notification_event ADD VALUE 'ticket_rejected';
