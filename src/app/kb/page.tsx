import { redirect } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import { getArticles } from "@/lib/kb";
import Nav from "@/components/Nav";

export default async function KnowledgeBasePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const { q } = await searchParams;
  const isTech = await isTechnician(userId);
  const articles = await getArticles({ includeUnpublished: isTech, search: q });

  return (
    <main>
      <Nav userId={userId} />

      <h1>Knowledge Base</h1>

      <form method="GET" style={{ display: "flex", gap: 12, alignItems: "flex-end", marginBottom: 16 }}>
        <div className="field" style={{ maxWidth: 320, marginBottom: 0 }}>
          <label htmlFor="q">Search</label>
          <input id="q" name="q" defaultValue={q ?? ""} placeholder="Title or content" />
        </div>
        <button type="submit" className="secondary">
          Search
        </button>
        {isTech && (
          <a href="/kb/new" style={{ marginLeft: "auto" }}>
            <button type="button">New article</button>
          </a>
        )}
      </form>

      {articles.length === 0 && <p className="muted">No articles found.</p>}
      {articles.map((a: any) => (
        <div key={a.id} className="card">
          <h2 style={{ margin: 0, textTransform: "none", letterSpacing: "normal", fontSize: 17 }}>
            <a href={`/kb/${a.id}`}>{a.title}</a>
          </h2>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            {a.category_name && <span className="badge">{a.category_name}</span>}{" "}
            {!a.is_published && <span className="badge badge-overdue">Draft</span>}
          </p>
        </div>
      ))}
    </main>
  );
}
