// Bootstraps the very first technician. Everyone after this one gets
// onboarded through /technician/users (see src/lib/password-setup.ts) —
// but that page is technician-only, so something has to create the first
// one out-of-band. This is that something, formalized instead of the
// ad-hoc scripts it replaces.
import "dotenv/config";
import crypto from "crypto";
import { pool } from "../src/lib/db";
import { hashPassword } from "../src/lib/password";

function arg(name: string): string | undefined {
  const prefix = `--${name}=`;
  const found = process.argv.find((a) => a.startsWith(prefix));
  return found?.slice(prefix.length);
}

async function getOrCreateTeam(name: string): Promise<string> {
  const existing = await pool.query(`SELECT id FROM teams WHERE name = $1`, [name]);
  if (existing.rows[0]) {
    return existing.rows[0].id;
  }
  const inserted = await pool.query(`INSERT INTO teams (name) VALUES ($1) RETURNING id`, [name]);
  return inserted.rows[0].id;
}

async function main() {
  const email = arg("email");
  const name = arg("name") ?? "IT Technician";
  const teamName = arg("team") ?? "IT Support";
  const providedPassword = arg("password");

  if (!email) {
    console.error(
      'Usage: npm run seed:technician -- --email=you@example.com [--name="Your Name"] [--team="IT Support"] [--password=...]'
    );
    process.exit(1);
  }

  const password = providedPassword ?? crypto.randomBytes(12).toString("base64url");
  const passwordHash = await hashPassword(password);
  const teamId = await getOrCreateTeam(teamName);

  const userResult = await pool.query(
    `INSERT INTO users (display_name, email, is_technician, password_hash)
     VALUES ($1, $2, true, $3)
     ON CONFLICT (email) DO UPDATE SET
       password_hash = EXCLUDED.password_hash,
       is_technician = true,
       is_active = true
     RETURNING id`,
    [name, email.toLowerCase(), passwordHash]
  );
  const userId = userResult.rows[0].id;

  await pool.query(
    `INSERT INTO team_members (team_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
    [teamId, userId]
  );

  console.log(`Technician ready: ${email} (team: ${teamName})`);
  if (!providedPassword) {
    console.log(`Generated password: ${password}`);
    console.log("Store this somewhere safe — it will not be shown again.");
  }

  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
