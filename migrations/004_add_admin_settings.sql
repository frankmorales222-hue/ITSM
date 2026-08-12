-- Encrypted key/value store for integration config (Azure AD, IMAP) that
-- technicians set through /admin instead of editing .env. value_encrypted
-- holds AES-256-GCM output (iv + authTag + ciphertext); never plaintext.
CREATE TABLE admin_settings (
    key                 TEXT PRIMARY KEY,
    value_encrypted     TEXT NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by_id       UUID REFERENCES users(id)
);
