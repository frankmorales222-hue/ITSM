import crypto from "crypto";
import { pool } from "./db";

// Integration config (Azure AD, IMAP) entered through /admin instead of
// .env, so it can be set after deploy without a restart or shell access.
// Encrypted at rest with AES-256-GCM — these are real credentials
// (a client secret, a mailbox password), not settings that are fine to
// read back in plaintext from the database.
const ALGORITHM = "aes-256-gcm";

function getKey(): Buffer {
  const hex = process.env.ADMIN_SETTINGS_ENCRYPTION_KEY;
  if (!hex) {
    throw new Error("ADMIN_SETTINGS_ENCRYPTION_KEY is not set");
  }
  const key = Buffer.from(hex, "hex");
  if (key.length !== 32) {
    throw new Error("ADMIN_SETTINGS_ENCRYPTION_KEY must be 32 bytes (64 hex chars)");
  }
  return key;
}

function encrypt(plaintext: string): string {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(ALGORITHM, getKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return [iv.toString("hex"), authTag.toString("hex"), ciphertext.toString("hex")].join(":");
}

function decrypt(stored: string): string {
  const [ivHex, authTagHex, ciphertextHex] = stored.split(":");
  const decipher = crypto.createDecipheriv(ALGORITHM, getKey(), Buffer.from(ivHex, "hex"));
  decipher.setAuthTag(Buffer.from(authTagHex, "hex"));
  const plaintext = Buffer.concat([
    decipher.update(Buffer.from(ciphertextHex, "hex")),
    decipher.final(),
  ]);
  return plaintext.toString("utf8");
}

export async function setSetting(key: string, value: string, updatedById: string): Promise<void> {
  await pool.query(
    `INSERT INTO admin_settings (key, value_encrypted, updated_at, updated_by_id)
     VALUES ($1, $2, now(), $3)
     ON CONFLICT (key) DO UPDATE SET
       value_encrypted = EXCLUDED.value_encrypted,
       updated_at = now(),
       updated_by_id = EXCLUDED.updated_by_id`,
    [key, encrypt(value), updatedById]
  );
}

export async function getSetting(key: string): Promise<string | null> {
  const result = await pool.query(`SELECT value_encrypted FROM admin_settings WHERE key = $1`, [
    key,
  ]);
  const row = result.rows[0];
  return row ? decrypt(row.value_encrypted) : null;
}

export async function deleteSetting(key: string): Promise<void> {
  await pool.query(`DELETE FROM admin_settings WHERE key = $1`, [key]);
}

export async function isSettingConfigured(key: string): Promise<boolean> {
  const result = await pool.query(`SELECT 1 FROM admin_settings WHERE key = $1`, [key]);
  return result.rows.length > 0;
}

const AZURE_AD_KEYS = {
  tenantId: "azure_ad_tenant_id",
  clientId: "azure_ad_client_id",
  clientSecret: "azure_ad_client_secret",
} as const;

export interface AzureAdConfig {
  tenantId: string;
  clientId: string;
  clientSecret: string;
}

export async function getAzureAdConfig(): Promise<AzureAdConfig | null> {
  const [tenantId, clientId, clientSecret] = await Promise.all([
    getSetting(AZURE_AD_KEYS.tenantId),
    getSetting(AZURE_AD_KEYS.clientId),
    getSetting(AZURE_AD_KEYS.clientSecret),
  ]);
  if (!tenantId || !clientId || !clientSecret) return null;
  return { tenantId, clientId, clientSecret };
}

export async function setAzureAdConfig(config: AzureAdConfig, updatedById: string): Promise<void> {
  await Promise.all([
    setSetting(AZURE_AD_KEYS.tenantId, config.tenantId, updatedById),
    setSetting(AZURE_AD_KEYS.clientId, config.clientId, updatedById),
    setSetting(AZURE_AD_KEYS.clientSecret, config.clientSecret, updatedById),
  ]);
}

export async function clearAzureAdConfig(): Promise<void> {
  await Promise.all(Object.values(AZURE_AD_KEYS).map(deleteSetting));
}

const IMAP_KEYS = {
  host: "imap_host",
  port: "imap_port",
  user: "imap_user",
  password: "imap_password",
} as const;

export interface ImapConfig {
  host: string;
  port: number;
  user: string;
  password: string;
}

export async function getImapConfig(): Promise<ImapConfig | null> {
  const [host, port, user, password] = await Promise.all([
    getSetting(IMAP_KEYS.host),
    getSetting(IMAP_KEYS.port),
    getSetting(IMAP_KEYS.user),
    getSetting(IMAP_KEYS.password),
  ]);
  if (!host || !port || !user || !password) return null;
  return { host, port: Number(port), user, password };
}

export async function setImapConfig(config: ImapConfig, updatedById: string): Promise<void> {
  await Promise.all([
    setSetting(IMAP_KEYS.host, config.host, updatedById),
    setSetting(IMAP_KEYS.port, String(config.port), updatedById),
    setSetting(IMAP_KEYS.user, config.user, updatedById),
    setSetting(IMAP_KEYS.password, config.password, updatedById),
  ]);
}

export async function clearImapConfig(): Promise<void> {
  await Promise.all(Object.values(IMAP_KEYS).map(deleteSetting));
}
