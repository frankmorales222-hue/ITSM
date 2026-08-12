import crypto from "crypto";
import path from "path";
import fs from "fs/promises";
import { pool } from "./db";

// Local-disk-backed storage — there's no MinIO/S3 wired up in this dev
// environment. storage_path holds a random name, never the original
// filename, so nothing user-controlled ends up in a filesystem path.
export const UPLOADS_DIR = path.join(process.cwd(), "uploads");

export interface SaveAttachmentInput {
  ticketId: string;
  uploadedById: string;
  file: File;
  replyId?: string | null;
}

export async function saveAttachment({ ticketId, uploadedById, file, replyId }: SaveAttachmentInput) {
  await fs.mkdir(UPLOADS_DIR, { recursive: true });

  const storageName = crypto.randomUUID();
  const buffer = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(path.join(UPLOADS_DIR, storageName), buffer);

  const result = await pool.query(
    `INSERT INTO ticket_attachments
      (ticket_id, reply_id, uploaded_by_id, file_name, storage_path, content_type, size_bytes)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     RETURNING *`,
    [ticketId, replyId ?? null, uploadedById, file.name, storageName, file.type || "application/octet-stream", buffer.length]
  );
  return result.rows[0];
}

export async function getAttachmentsForTicket(ticketId: string) {
  const result = await pool.query(
    `SELECT a.*, u.display_name AS uploaded_by_name
     FROM ticket_attachments a
     JOIN users u ON u.id = a.uploaded_by_id
     WHERE a.ticket_id = $1
     ORDER BY a.created_at ASC`,
    [ticketId]
  );
  return result.rows;
}

export async function getAttachmentById(id: string) {
  const result = await pool.query(`SELECT * FROM ticket_attachments WHERE id = $1`, [id]);
  return result.rows[0] ?? null;
}
