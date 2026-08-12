import crypto from "crypto";
import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  CreateBucketCommand,
  HeadBucketCommand,
} from "@aws-sdk/client-s3";
import { pool } from "./db";

// S3-compatible storage (MinIO locally — see docker-compose.yml).
// storage_path holds a random object key, never the original filename, so
// nothing user-controlled ends up in a storage path.
const BUCKET = process.env.S3_BUCKET ?? "itsm-attachments";

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

// Extensions worth blocking outright: things a browser or OS might
// auto-execute on download/open. Not a malware scanner — just closes off
// the easiest "click the attachment" vector. Checked case-insensitively.
const BLOCKED_EXTENSIONS = new Set([
  "exe", "dll", "msi", "msp", "scr", "com", "bat", "cmd", "ps1", "vbs",
  "vbe", "js", "jse", "wsf", "wsh", "sh", "app", "jar", "apk", "cpl",
]);

const MAX_ATTACHMENTS_PER_TICKET = 20;
const MAX_TOTAL_BYTES_PER_TICKET = 200 * 1024 * 1024; // 200 MB

export class AttachmentValidationError extends Error {}

export function assertValidAttachment(file: File): void {
  if (file.size > MAX_FILE_SIZE_BYTES) {
    throw new AttachmentValidationError(
      `File is too large (max ${MAX_FILE_SIZE_BYTES / (1024 * 1024)} MB).`
    );
  }
  const ext = file.name.split(".").pop()?.toLowerCase();
  if (ext && BLOCKED_EXTENSIONS.has(ext)) {
    throw new AttachmentValidationError(`.${ext} files aren't allowed.`);
  }
}

// Separate from assertValidAttachment because this one needs a DB round
// trip (existing usage for the ticket) — callers that only care about the
// file itself (e.g. showing an error before touching the DB at all) can
// use assertValidAttachment alone first.
export async function assertWithinTicketQuota(ticketId: string, file: File): Promise<void> {
  const result = await pool.query(
    `SELECT count(*)::int AS count, coalesce(sum(size_bytes), 0)::bigint AS total_bytes
     FROM ticket_attachments WHERE ticket_id = $1`,
    [ticketId]
  );
  const { count, total_bytes } = result.rows[0];

  if (count >= MAX_ATTACHMENTS_PER_TICKET) {
    throw new AttachmentValidationError(
      `This ticket already has the maximum of ${MAX_ATTACHMENTS_PER_TICKET} attachments.`
    );
  }
  if (Number(total_bytes) + file.size > MAX_TOTAL_BYTES_PER_TICKET) {
    throw new AttachmentValidationError(
      `This would exceed the ${MAX_TOTAL_BYTES_PER_TICKET / (1024 * 1024)} MB total attachment limit for this ticket.`
    );
  }
}

const s3 = new S3Client({
  endpoint: process.env.S3_ENDPOINT ?? "http://localhost:9000",
  region: process.env.S3_REGION ?? "us-east-1",
  forcePathStyle: true,
  credentials: {
    accessKeyId: process.env.S3_ACCESS_KEY ?? "minioadmin",
    secretAccessKey: process.env.S3_SECRET_KEY ?? "minioadmin",
  },
});

let bucketReady: Promise<void> | null = null;

async function ensureBucket(): Promise<void> {
  if (!bucketReady) {
    bucketReady = (async () => {
      try {
        await s3.send(new HeadBucketCommand({ Bucket: BUCKET }));
      } catch {
        await s3.send(new CreateBucketCommand({ Bucket: BUCKET }));
      }
    })();
  }
  return bucketReady;
}

export interface SaveAttachmentInput {
  ticketId: string;
  uploadedById: string;
  file: File;
  replyId?: string | null;
}

export async function saveAttachment({ ticketId, uploadedById, file, replyId }: SaveAttachmentInput) {
  assertValidAttachment(file);
  await assertWithinTicketQuota(ticketId, file);
  await ensureBucket();

  const objectKey = crypto.randomUUID();
  const buffer = Buffer.from(await file.arrayBuffer());

  await s3.send(
    new PutObjectCommand({
      Bucket: BUCKET,
      Key: objectKey,
      Body: buffer,
      ContentType: file.type || "application/octet-stream",
    })
  );

  const result = await pool.query(
    `INSERT INTO ticket_attachments
      (ticket_id, reply_id, uploaded_by_id, file_name, storage_path, content_type, size_bytes)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     RETURNING *`,
    [ticketId, replyId ?? null, uploadedById, file.name, objectKey, file.type || "application/octet-stream", buffer.length]
  );
  return result.rows[0];
}

export async function getAttachmentBytes(storageKey: string): Promise<Buffer> {
  const result = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: storageKey }));
  const stream = result.Body as NodeJS.ReadableStream;
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
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
