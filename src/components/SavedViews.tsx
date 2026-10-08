import AjaxForm, { type AjaxAction } from "./AjaxForm";
import { buildFilterQueryString, type TicketFilters } from "@/lib/ticket-filters";

export default function SavedViews({
  views,
  currentFilters,
  basePath,
  onSave,
  onDelete,
}: {
  views: { id: string; name: string; filters: TicketFilters }[];
  currentFilters: TicketFilters;
  basePath: string;
  onSave: AjaxAction;
  onDelete: AjaxAction;
}) {
  const hasActiveFilters = Boolean(currentFilters.status || currentFilters.category || currentFilters.q);

  if (views.length === 0 && !hasActiveFilters) {
    return null;
  }

  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", margin: "4px 0 20px" }}>
      {views.map((v) => {
        const qs = buildFilterQueryString(v.filters);
        const href = qs ? `${basePath}?${qs.slice(1)}` : basePath;
        return (
          <div key={v.id} style={{ display: "flex", alignItems: "center", gap: 2 }}>
            <a className="status-group" href={href}>
              {v.name}
            </a>
            <AjaxForm action={onDelete} successMessage="View deleted." className="form-inline">
              <input type="hidden" name="viewId" value={v.id} />
              <button
                type="submit"
                className="secondary"
                style={{ padding: "4px 8px", fontSize: 12 }}
                aria-label={`Delete saved view ${v.name}`}
              >
                &times;
              </button>
            </AjaxForm>
          </div>
        );
      })}
      {hasActiveFilters && (
        <AjaxForm
          action={onSave}
          successMessage="View saved."
          style={{ display: "flex", gap: 6, alignItems: "center" }}
        >
          <input type="hidden" name="status" value={currentFilters.status ?? ""} />
          <input type="hidden" name="category" value={currentFilters.category ?? ""} />
          <input type="hidden" name="q" value={currentFilters.q ?? ""} />
          <input type="text" name="name" placeholder="Save current filters as…" required style={{ width: 200 }} />
          <button type="submit" className="secondary">
            Save view
          </button>
        </AjaxForm>
      )}
    </div>
  );
}
