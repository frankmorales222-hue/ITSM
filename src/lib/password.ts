import crypto from "crypto";

// scrypt instead of a bcrypt dependency — built into Node, no new package.
// Format: "<saltHex>.<hashHex>".
const KEY_LENGTH = 64;

export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.randomBytes(16).toString("hex");
  const derived = await scrypt(password, salt);
  return `${salt}.${derived.toString("hex")}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [salt, hashHex] = stored.split(".");
  if (!salt || !hashHex) return false;

  const derived = await scrypt(password, salt);
  const storedBuf = Buffer.from(hashHex, "hex");
  if (derived.length !== storedBuf.length) return false;
  return crypto.timingSafeEqual(derived, storedBuf);
}

function scrypt(password: string, salt: string): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    crypto.scrypt(password, salt, KEY_LENGTH, (err, derived) => {
      if (err) reject(err);
      else resolve(derived);
    });
  });
}
