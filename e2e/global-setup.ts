// Seeds the isolated itsm_e2e database with one technician user before the
// suite runs. Deliberately not importing src/lib/db — that module builds
// its connection pool from process.env.DATABASE_URL at import time, and
// getting that env var set before the import resolves is exactly the kind
// of ordering footgun this avoids by just using `pg` directly, same as
// every other throwaway seed script in this repo.
import { Client } from "pg";
import { hashPassword } from "../src/lib/password";

const E2E_DATABASE_URL = "postgresql://postgres:dev@localhost:5432/itsm_e2e";

export const E2E_USER_EMAIL = "e2e.tech@example.com";
export const E2E_USER_PASSWORD = "E2ePassword123!";

export default async function globalSetup() {
  const client = new Client({ connectionString: E2E_DATABASE_URL });
  await client.connect();

  try {
    // Full reset so re-runs start clean — categories/teams seeded by the
    // migration itself are recreated by re-running it, so just wipe
    // everything and let the caller re-migrate if the schema changed.
    await client.query(`
      TRUNCATE
        ticket_notifications, inbound_email_log, ticket_status_history,
        ticket_attachments, ticket_notes, ticket_replies, tickets,
        assignment_state, team_members, teams, users
      RESTART IDENTITY CASCADE
    `);

    const teamResult = await client.query(
      `INSERT INTO teams (name) VALUES ('IT Support') RETURNING id`
    );
    const teamId = teamResult.rows[0].id;

    const passwordHash = await hashPassword(E2E_USER_PASSWORD);
    const userResult = await client.query(
      `INSERT INTO users (display_name, email, is_technician, password_hash)
       VALUES ('E2E Technician', $1, true, $2)
       RETURNING id`,
      [E2E_USER_EMAIL, passwordHash]
    );
    const userId = userResult.rows[0].id;

    await client.query(`INSERT INTO team_members (team_id, user_id) VALUES ($1, $2)`, [
      teamId,
      userId,
    ]);

    console.log(`[e2e] seeded ${E2E_USER_EMAIL} on team ${teamId}`);
  } finally {
    await client.end();
  }
}
