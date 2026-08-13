import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createArticle, updateArticle, getArticles, getArticleById } from "./kb";
import { pool } from "./db";
import { resetTestDb, createTestUser, getDefaultCategoryId } from "./test-fixtures";

describe("knowledge base", () => {
  beforeEach(resetTestDb);

  it("creates a published article and finds it in the published list", async () => {
    const authorId = await createTestUser({ isTechnician: true });
    const article = await createArticle({
      title: "How to reset your VPN",
      body: "Step 1: turn it off and on again.",
      isPublished: true,
      authorId,
    });

    const published = await getArticles({ includeUnpublished: false });
    expect(published.map((a) => a.id)).toContain(article.id);
  });

  it("hides drafts from the published-only view but shows them to technicians", async () => {
    const authorId = await createTestUser({ isTechnician: true });
    const draft = await createArticle({
      title: "Draft article",
      body: "Not ready yet.",
      isPublished: false,
      authorId,
    });

    const employeeView = await getArticles({ includeUnpublished: false });
    expect(employeeView.map((a) => a.id)).not.toContain(draft.id);

    const technicianView = await getArticles({ includeUnpublished: true });
    expect(technicianView.map((a) => a.id)).toContain(draft.id);
  });

  it("searches title and body with ILIKE", async () => {
    const authorId = await createTestUser({ isTechnician: true });
    await createArticle({
      title: "Printer setup",
      body: "Connect to the printer via the shared network.",
      isPublished: true,
      authorId,
    });
    await createArticle({
      title: "Unrelated article",
      body: "Nothing to do with hardware.",
      isPublished: true,
      authorId,
    });

    const results = await getArticles({ includeUnpublished: false, search: "printer" });
    expect(results).toHaveLength(1);
    expect(results[0].title).toBe("Printer setup");
  });

  it("stores and returns the category", async () => {
    const authorId = await createTestUser({ isTechnician: true });
    const categoryId = await getDefaultCategoryId();
    const article = await createArticle({
      title: "Categorized article",
      body: "...",
      categoryId,
      isPublished: true,
      authorId,
    });

    const fetched = await getArticleById(article.id);
    expect(fetched.category_id).toBe(categoryId);
    expect(fetched.category_name).not.toBeNull();
  });

  it("updates title, body, category, and published state", async () => {
    const authorId = await createTestUser({ isTechnician: true });
    const article = await createArticle({
      title: "Original title",
      body: "Original body",
      isPublished: false,
      authorId,
    });

    await updateArticle({
      id: article.id,
      title: "Updated title",
      body: "Updated body",
      isPublished: true,
    });

    const fetched = await getArticleById(article.id);
    expect(fetched.title).toBe("Updated title");
    expect(fetched.body).toBe("Updated body");
    expect(fetched.is_published).toBe(true);
  });

  it("includes the author's display name", async () => {
    const authorId = await createTestUser({ isTechnician: true });
    const article = await createArticle({
      title: "Attributed article",
      body: "...",
      isPublished: true,
      authorId,
    });

    const fetched = await getArticleById(article.id);
    expect(fetched.author_name).toBe("Test User");
  });
});

afterAll(async () => {
  await pool.end();
});
