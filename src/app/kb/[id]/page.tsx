import { redirect, notFound } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import { getArticleById, updateArticle } from "@/lib/kb";
import { getActiveCategories } from "@/lib/ticket-filters";
import Nav from "@/components/Nav";

export default async function ArticlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const article = await getArticleById(id);
  if (!article) {
    notFound();
  }

  const isTech = await isTechnician(userId);
  if (!article.is_published && !isTech) {
    notFound();
  }

  const categories = isTech ? await getActiveCategories() : [];

  async function submitEdit(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || !(await isTechnician(actorId))) {
      redirect("/login");
    }

    const title = String(formData.get("title") ?? "").trim();
    const body = String(formData.get("body") ?? "").trim();
    const categoryId = (formData.get("categoryId") as string) || null;
    const isPublished = formData.get("isPublished") === "on";

    if (title && body) {
      await updateArticle({ id, title, body, categoryId, isPublished });
    }
    redirect(`/kb/${id}`);
  }

  return (
    <main>
      <Nav userId={userId} />

      <nav className="nav" style={{ borderBottom: "none", marginBottom: 8 }}>
        <a href="/kb">&larr; Knowledge Base</a>
      </nav>

      <div className="card">
        <h1>{article.title}</h1>
        <p>
          {article.category_name && <span className="badge">{article.category_name}</span>}{" "}
          {!article.is_published && <span className="badge badge-overdue">Draft</span>}
        </p>
        <p style={{ whiteSpace: "pre-wrap" }}>{article.body}</p>
        <p className="muted" style={{ marginTop: 16 }}>
          By {article.author_name} &middot; updated {new Date(article.updated_at).toLocaleString()}
        </p>
      </div>

      {isTech && (
        <div className="card">
          <h2>Edit</h2>
          <form action={submitEdit}>
            <div className="field">
              <label htmlFor="title">Title</label>
              <input id="title" name="title" defaultValue={article.title} required />
            </div>
            <div className="field">
              <label htmlFor="body">Body</label>
              <textarea id="body" name="body" rows={10} defaultValue={article.body} required />
            </div>
            <div className="field" style={{ maxWidth: 240 }}>
              <label htmlFor="categoryId">Category (optional)</label>
              <select id="categoryId" name="categoryId" defaultValue={article.category_id ?? ""}>
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
                <input
                  id="isPublished"
                  name="isPublished"
                  type="checkbox"
                  style={{ width: "auto" }}
                  defaultChecked={article.is_published}
                />{" "}
                Published
              </label>
            </div>
            <button type="submit" className="secondary">
              Save
            </button>
          </form>
        </div>
      )}
    </main>
  );
}
