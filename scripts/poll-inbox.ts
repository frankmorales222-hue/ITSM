// Reads unseen messages from the mailbox configured via /admin and POSTs
// each to the email intake webhook (src/app/api/email/inbound). Meant to
// run on a schedule (cron, Task Scheduler) — see README's Email intake
// section for why this exists as a poller rather than a long-running
// Next.js process.
import "dotenv/config";
import { ImapFlow } from "imapflow";
import { simpleParser } from "mailparser";
import { getImapConfig } from "../src/lib/admin-settings";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

async function main() {
  const webhookSecret = process.env.EMAIL_WEBHOOK_SECRET;
  if (!webhookSecret) {
    console.error("EMAIL_WEBHOOK_SECRET is not set.");
    process.exit(1);
  }

  const config = await getImapConfig();
  if (!config) {
    console.log("IMAP is not configured (see /admin) — nothing to poll.");
    return;
  }

  const client = new ImapFlow({
    host: config.host,
    port: config.port,
    secure: config.port === 993,
    auth: { user: config.user, pass: config.password },
    logger: false,
  });

  await client.connect();
  try {
    const lock = await client.getMailboxLock("INBOX");
    try {
      const uids = await client.search({ seen: false }, { uid: true });
      if (!uids || uids.length === 0) {
        console.log("No new messages.");
        return;
      }

      for (const uid of uids) {
        const message = await client.fetchOne(uid, { source: true }, { uid: true });
        if (!message || !message.source) continue;

        const parsed = await simpleParser(message.source);
        const messageId = parsed.messageId;
        const from = Array.isArray(parsed.from?.value) ? parsed.from.value[0]?.address : undefined;

        if (!messageId || !from) {
          console.warn(`Skipping uid=${uid}: missing Message-ID or From address.`);
          await client.messageFlagsAdd(uid, ["\\Seen"], { uid: true });
          continue;
        }

        const res = await fetch(`${APP_URL}/api/email/inbound`, {
          method: "POST",
          headers: { "content-type": "application/json", "x-webhook-secret": webhookSecret },
          body: JSON.stringify({
            messageId,
            inReplyTo: parsed.inReplyTo,
            from,
            subject: parsed.subject ?? "(no subject)",
            body: parsed.text ?? "",
          }),
        });
        const result = await res.json();
        console.log(`uid=${uid} message-id=${messageId} -> ${res.status}`, result);

        // Mark seen regardless of outcome — a message the webhook rejects
        // (unknown sender, duplicate) isn't going to succeed on a later
        // poll either, and leaving it unseen would just retry it forever.
        await client.messageFlagsAdd(uid, ["\\Seen"], { uid: true });
      }
    } finally {
      lock.release();
    }
  } finally {
    await client.logout();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
