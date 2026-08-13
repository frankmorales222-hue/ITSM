// New ticket form — the actual "Report a problem" experience. Creates the
// ticket via a server action; requester/opener are the session user.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { createTicket as createTicketRecord, getDefaultTeamId } from "@/lib/tickets";
import { getSessionUserId } from "@/lib/auth";
import { isTicketCreationRateLimited } from "@/lib/rate-limit";
import Nav from "@/components/Nav";

async function getCategories() {
  const result = await pool.query(
    `SELECT id, name FROM categories WHERE is_active = true ORDER BY sort_order`
  );
  return result.rows;
}

async function createTicket(formData: FormData) {
  "use server";

  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  if (await isTicketCreationRateLimited(userId)) {
    redirect("/tickets/new?error=rate_limited");
  }

  const teamId = await getDefaultTeamId();
  if (!teamId) {
    throw new Error("No default team found");
  }

  await createTicketRecord({
    requesterId: userId,
    openedById: userId,
    subject: String(formData.get("subject") ?? ""),
    description: String(formData.get("description") ?? ""),
    categoryId: (formData.get("categoryId") as string) || null,
    impact: (formData.get("impact") as "high" | "medium" | "low") || null,
    urgency: (formData.get("urgency") as "high" | "medium" | "low") || null,
    submissionChannel: "web",
    teamId,
  });

  redirect("/tickets");
}

export default async function NewTicketPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }
  const { error } = await searchParams;
  const categories = await getCategories();

  return (
    <main>
      <Nav userId={userId} />
      <div className="card" style={{ maxWidth: 480 }}>
        <h1>Report a problem</h1>
        {error === "rate_limited" && (
          <p className="error">Too many tickets created recently. Try again in a few minutes.</p>
        )}
        <form action={createTicket}>
          <div className="field">
            <label htmlFor="subject">Subject</label>
            <input id="subject" name="subject" required />
          </div>

          <div className="field">
            <label htmlFor="description">Description</label>
            <textarea id="description" name="description" required rows={5} />
          </div>

          <div className="field">
            <label htmlFor="categoryId">Category</label>
            <select id="categoryId" name="categoryId">
              {categories.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="impact">Impact</label>
            <select id="impact" name="impact">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="urgency">Urgency</label>
            <select id="urgency" name="urgency">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>

          <button type="submit">Submit</button>
        </form>
      </div>
    </main>
  );
}
