import { pool } from "./db";

/**
 * Assigns a ticket to the next technician in round-robin order for a team.
 * Simple, deliberately dumb: no workload/skill/availability weighting yet
 * (see phase-2+ notes in the data model doc).
 */
export async function assignRoundRobin(teamId: string): Promise<string | null> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const membersResult = await client.query(
      `SELECT u.id
       FROM team_members tm
       JOIN users u ON u.id = tm.user_id
       WHERE tm.team_id = $1 AND u.is_active = true
       ORDER BY u.id`,
      [teamId]
    );
    const memberIds: string[] = membersResult.rows.map((r) => r.id);

    if (memberIds.length === 0) {
      await client.query("ROLLBACK");
      return null;
    }

    const stateResult = await client.query(
      `SELECT last_assigned_user_id FROM assignment_state WHERE team_id = $1`,
      [teamId]
    );

    let nextIndex = 0;
    if (stateResult.rows.length > 0 && stateResult.rows[0].last_assigned_user_id) {
      const lastId = stateResult.rows[0].last_assigned_user_id;
      const lastIndex = memberIds.indexOf(lastId);
      nextIndex = lastIndex === -1 ? 0 : (lastIndex + 1) % memberIds.length;
    }

    const nextUserId = memberIds[nextIndex];

    await client.query(
      `INSERT INTO assignment_state (team_id, last_assigned_user_id, updated_at)
       VALUES ($1, $2, now())
       ON CONFLICT (team_id)
       DO UPDATE SET last_assigned_user_id = $2, updated_at = now()`,
      [teamId, nextUserId]
    );

    await client.query("COMMIT");
    return nextUserId;
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}
