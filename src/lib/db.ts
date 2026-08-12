import { Pool } from "pg";

// Single shared pool. In dev, Next.js hot-reload can create multiple
// instances of this module, so stash the pool on globalThis to avoid
// exhausting Postgres connections.
declare global {
  // eslint-disable-next-line no-var
  var __pgPool: Pool | undefined;
}

export const pool =
  global.__pgPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 10,
  });

if (process.env.NODE_ENV !== "production") {
  global.__pgPool = pool;
}
