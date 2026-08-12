// New ticket form — the actual "Report a problem" experience. Creates the
// ticket via a server action; requester/opener are the session user.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { createTicket as createTicketRecord, getDefaultTeamId } from "@/lib/tickets";
import { getSessionUserId } from "@/lib/auth";

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

export default async function NewTicketPage() {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }
  const categories = await getCategories();

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 480 }}>
      <h1>Report a problem</h1>
      <form action={createTicket}>
        <div style={{ marginBottom: 12 }}>
          <label htmlFor="subject">Subject</label>
          <br />
          <input id="subject" name="subject" required style={{ width: "100%" }} />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="description">Description</label>
          <br />
          <textarea
            id="description"
            name="description"
            required
            rows={5}
            style={{ width: "100%" }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="categoryId">Category</label>
          <br />
          <select id="categoryId" name="categoryId">
            {categories.map((c: any) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="impact">Impact</label>
          <br />
          <select id="impact" name="impact">
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="urgency">Urgency</label>
          <br />
          <select id="urgency" name="urgency">
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <button type="submit">Submit</button>
      </form>
    </main>
  );
}
