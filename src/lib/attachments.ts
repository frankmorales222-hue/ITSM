import crypto from "crypto";
import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  CreateBucketCommand,
  HeadBucketCommand,
} from "@aws-sdk/client-s3";
import { pool } from "./db";

// S3-compatible storage (MinIO locally — see docker run command in the
// README). storage_path holds a random object key, never the original
// filename, so nothing user-controlled ends up in a storage path.
const BUCKET = process.env.S3_BUCKET ?? "itsm-attachments";

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
