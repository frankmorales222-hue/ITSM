// Integration-test-only helpers. Not imported by any app code — safe to
// ship (nothing routes to it), but exists purely so *.integration.test.ts
// files have a consistent way to set up/tear down rows in itsm_test.
import crypto from "crypto";
import { pool } from "./db";

export async function resetTestDb() {
  await pool.query(`
    TRUNCATE
      ticket_notifications, inbound_email_log, ticket_status_history,
      ticket_attachments, ticket_notes, ticket_replies, tickets,
      assignment_state, team_members, teams, users, admin_settings
    RESTART IDENTITY CASCADE
  `);
}

export async function createTestTeam(name = `Team ${crypto.randomUUID()}`): Promise<string> {
  const result = await pool.query(`INSERT INTO teams (name) VALUES ($1) RETURNING id`, [name]);
  return result.rows[0].id;
}

export async function createTestUser(opts: { isTechnician?: boolean } = {}): Promise<string> {
  const email = `test-${crypto.randomUUID()}@example.com`;
  const result = await pool.query(
    `INSERT INTO users (display_name, email, is_technician) VALUES ($1, $2, $3) RETURNING id`,
    ["Test User", email, opts.isTechnician ?? false]
  );
  return result.rows[0].id;
}

export async function addToTeam(teamId: string, userId: string): Promise<void> {
  await pool.query(`INSERT INTO team_members (team_id, user_id) VALUES ($1, $2)`, [teamId, userId]);
}

export async function getDefaultCategoryId(): Promise<string> {
  const result = await pool.query(`SELECT id FROM categories ORDER BY sort_order LIMIT 1`);
  return result.rows[0].id;
}
