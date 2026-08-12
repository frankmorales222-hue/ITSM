-- One-time links technicians generate to let a new user set their first
-- password. Only the hash is stored (same reasoning as password_hash
-- itself) so a DB leak doesn't hand out live tokens.
ALTER TABLE users ADD COLUMN password_setup_token_hash TEXT;
ALTER TABLE users ADD COLUMN password_setup_expires_at TIMESTAMPTZ;
