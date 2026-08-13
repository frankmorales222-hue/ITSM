import nodemailer from "nodemailer";
import { getSmtpConfig } from "./admin-settings";

// No-ops (returns false) when SMTP isn't configured yet, so notification
// call sites don't need to special-case "email isn't set up" themselves.
export async function sendMail({
  to,
  subject,
  text,
}: {
  to: string;
  subject: string;
  text: string;
}): Promise<boolean> {
  const config = await getSmtpConfig();
  if (!config) {
    return false;
  }

  const transporter = nodemailer.createTransport({
    host: config.host,
    port: config.port,
    secure: config.secure,
    auth: config.user ? { user: config.user, pass: config.password } : undefined,
  });

  await transporter.sendMail({
    from: config.fromAddress,
    to,
    subject,
    text,
  });

  return true;
}
