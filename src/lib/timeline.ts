import { pool } from "./db";

export interface TimelineEntry {
  id: string;
  type: "reply" | "status_change" | "note";
  authorName: string | null;
  body: string | null;
  fromStatus: string | null;
  toStatus: string | null;
  createdAt: string;
}

// Merges replies, status history, and (for technicians) internal notes —
// which also carry the reassignment/escalation/approval audit trail, see
// tickets.ts/approval.ts — into one chronological feed. Internal notes are
// only ever fetched when includeInternal is true; the caller is
// responsible for only passing true for technicians, same rule that
// already gates every other internal-notes read in this app.
export async function getTimeline(ticketId: string, includeInternal: boolean): Promise<TimelineEntry[]> {
  const [repliesResult, historyResult, notesResult] = await Promise.all([
    pool.query(
      `SELECT r.id, u.display_name AS author_name, r.body, r.created_at
       FROM ticket_replies r
       JOIN users u ON u.id = r.author_id
       WHERE r.ticket_id = $1`,
      [ticketId]
    ),
    pool.query(
      `SELECT h.id, u.display_name AS author_name, h.from_status, h.to_status, h.note, h.created_at
       FROM ticket_status_history h
       LEFT JOIN users u ON u.id = h.changed_by_id
       WHERE h.ticket_id = $1`,
      [ticketId]
    ),
    includeInternal
      ? pool.query(
          `SELECT n.id, u.display_name AS author_name, n.body, n.created_at
           FROM ticket_notes n
           JOIN users u ON u.id = n.author_id
           WHERE n.ticket_id = $1`,
          [ticketId]
        )
      : Promise.resolve({ rows: [] as any[] }),
  ]);

  const entries: TimelineEntry[] = [
    ...repliesResult.rows.map((r) => ({
      id: `reply-${r.id}`,
      type: "reply" as const,
      authorName: r.author_name as string,
      body: r.body as string,
      fromStatus: null,
      toStatus: null,
      createdAt: r.created_at as string,
    })),
    ...historyResult.rows.map((h) => ({
      id: `status-${h.id}`,
      type: "status_change" as const,
      authorName: (h.author_name as string) ?? null,
      body: h.note as string | null,
      fromStatus: h.from_status as string | null,
      toStatus: h.to_status as string,
      createdAt: h.created_at as string,
    })),
    ...notesResult.rows.map((n) => ({
      id: `note-${n.id}`,
      type: "note" as const,
      authorName: n.author_name as string,
      body: n.body as string,
      fromStatus: null,
      toStatus: null,
      createdAt: n.created_at as string,
    })),
  ];

  entries.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  return entries;
}
