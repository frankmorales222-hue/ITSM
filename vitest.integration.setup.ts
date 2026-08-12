// Must run before any test file imports src/lib/db.ts, which reads
// DATABASE_URL at module load time to build its connection pool. Points
// at a separate database so these tests never touch dev data.
process.env.DATABASE_URL =
  process.env.TEST_DATABASE_URL ?? "postgresql://postgres:dev@localhost:5432/itsm_test";
process.env.SESSION_SECRET ??= "test-session-secret-do-not-use-in-prod";
process.env.REDIS_URL ??= "redis://localhost:6379";
process.env.S3_ENDPOINT ??= "http://localhost:9000";
process.env.S3_BUCKET ??= "itsm-attachments-test";
process.env.S3_ACCESS_KEY ??= "minioadmin";
process.env.S3_SECRET_KEY ??= "minioadmin";
