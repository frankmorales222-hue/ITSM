import type { TimelineEntry } from "@/lib/timeline";

const DOT_CLASS: Record<TimelineEntry["type"], string> = {
  reply: "timeline-dot-comment",
  status_change: "timeline-dot-system",
  note: "timeline-dot-note",
};

export default function Timeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="muted">Nothing here yet.</p>;
  }

  return (
    <div>
      {entries.map((e) => (
        <div key={e.id} className="timeline-item">
          <div className={`timeline-dot ${DOT_CLASS[e.type]}`} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="reply-meta">
              <strong>{e.authorName ?? "System"}</strong>
              {e.type === "status_change" && (
                <>
                  {" "}
                  changed status{e.fromStatus ? ` from ${e.fromStatus.replace(/_/g, " ")}` : ""} to{" "}
                  <strong>{e.toStatus?.replace(/_/g, " ")}</strong>
                </>
              )}
              {e.type === "note" && <> &middot; <span className="muted">internal note</span></>}
              {" "}&middot; {new Date(e.createdAt).toLocaleString()}
            </div>
            {e.body && <p className="reply-body">{e.body}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}
