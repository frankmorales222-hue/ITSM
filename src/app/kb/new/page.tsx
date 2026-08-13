import { redirect, notFound } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import { createArticle } from "@/lib/kb";
import { getActiveCategories } from "@/lib/ticket-filters";
import Nav from "@/components/Nav";

async function submitCreate(formData: FormData) {
  "use server";
  const authorId = await getSessionUserId();
  if (!authorId || !(await isTechnician(authorId))) {
    redirect("/login");
  }

  const title = String(formData.get("title") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const categoryId = (formData.get("categoryId") as string) || null;
  const isPublished = formData.get("isPublished") === "on";

  if (!title || !body) {
    redirect("/kb/new?error=missing_fields");
  }

  const article = await createArticle({ title, body, categoryId, isPublished, authorId });
  redirect(`/kb/${article.id}`);
}

export default async function NewArticlePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }
  if (!(await isTechnician(userId))) {
    notFound();
  }

  const { error } = await searchParams;
  const categories = await getActiveCategories();

  return (
    <main>
      <Nav userId={userId} />

      <div className="card" style={{ maxWidth: 640 }}>
        <h1>New article</h1>
        {error === "missing_fields" && <p className="error">Title and body are required.</p>}
        <form action={submitCreate}>
          <div className="field">
            <label htmlFor="title">Title</label>
            <input id="title" name="title" required />
          </div>
          <div className="field">
            <label htmlFor="body">Body</label>
            <textarea id="body" name="body" rows={10} required />
          </div>
          <div className="field" style={{ maxWidth: 240 }}>
            <label htmlFor="categoryId">Category (optional)</label>
            <select id="categoryId" name="categoryId" defaultValue="">
              <option value="">None</option>
              {categories.map((c: any) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="isPublished">
              <input id="isPublished" name="isPublished" type="checkbox" style={{ width: "auto" }} />{" "}
              Publish immediately
            </label>
          </div>
          <button type="submit">Create</button>
        </form>
      </div>
    </main>
  );
}
