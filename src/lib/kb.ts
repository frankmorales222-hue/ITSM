import { pool } from "./db";

export interface CreateArticleInput {
  title: string;
  body: string;
  categoryId?: string | null;
  isPublished: boolean;
  authorId: string;
}

export async function createArticle(input: CreateArticleInput) {
  const result = await pool.query(
    `INSERT INTO kb_articles (title, body, category_id, is_published, author_id)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING *`,
    [input.title, input.body, input.categoryId ?? null, input.isPublished, input.authorId]
  );
  return result.rows[0];
}

export interface UpdateArticleInput {
  id: string;
  title: string;
  body: string;
  categoryId?: string | null;
  isPublished: boolean;
}

export async function updateArticle(input: UpdateArticleInput) {
  await pool.query(
    `UPDATE kb_articles
     SET title = $1, body = $2, category_id = $3, is_published = $4, updated_at = now()
     WHERE id = $5`,
    [input.title, input.body, input.categoryId ?? null, input.isPublished, input.id]
  );
}

// Technicians see everything (including drafts) so they can review before
// publishing; everyone else only sees published articles.
export async function getArticles({
  includeUnpublished,
  search,
}: {
  includeUnpublished: boolean;
  search?: string;
}) {
  const params: any[] = [];
  let where = includeUnpublished ? "true" : "is_published = true";

  if (search) {
    params.push(`%${search}%`);
    where += ` AND (title ILIKE $${params.length} OR body ILIKE $${params.length})`;
  }

  const result = await pool.query(
    `SELECT a.*, c.name AS category_name
     FROM kb_articles a
     LEFT JOIN categories c ON c.id = a.category_id
     WHERE ${where}
     ORDER BY a.title ASC`,
    params
  );
  return result.rows;
}

export async function getArticleById(id: string) {
  const result = await pool.query(
    `SELECT a.*, c.name AS category_name, u.display_name AS author_name
     FROM kb_articles a
     LEFT JOIN categories c ON c.id = a.category_id
     JOIN users u ON u.id = a.author_id
     WHERE a.id = $1`,
    [id]
  );
  return result.rows[0] ?? null;
}
