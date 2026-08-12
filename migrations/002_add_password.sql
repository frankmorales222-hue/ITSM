-- Adds real credential storage. NULL means the user has no password set yet
-- (e.g. seeded users before this migration) and can't log in until one is.
ALTER TABLE users ADD COLUMN password_hash TEXT;
