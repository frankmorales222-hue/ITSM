-- Minimal self-service knowledge base: technician-authored articles,
-- optionally categorized (reuses the existing categories table), with a
-- draft/published flag so technicians can write before publishing.
CREATE TABLE kb_articles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    category_id         UUID REFERENCES categories(id),
    is_published        BOOLEAN NOT NULL DEFAULT false,
    author_id           UUID NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_kb_articles_published ON kb_articles(is_published);
