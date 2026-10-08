-- Per-user dashboard widget order/visibility. NULL means "use the default
-- set and order" — only users who've actually customized get a row value,
-- so adding a new default widget later doesn't require a backfill.
ALTER TABLE users ADD COLUMN dashboard_widgets TEXT[];
