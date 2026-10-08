-- Saved/custom views: a user can save a filter combination (status,
-- category, free-text search) on /tickets or /technician and reapply it
-- with one click instead of re-filtering every visit.
CREATE TABLE saved_views (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    page                TEXT NOT NULL CHECK (page IN ('tickets', 'technician')),
    name                TEXT NOT NULL,
    filters             JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_saved_views_user_page ON saved_views(user_id, page);
