// Color-coded status/priority chips — the signature visual language of
// Jira/ServiceNow-style tools, so status is scannable across a table at a
// glance instead of every badge rendering identically gray.
export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge status-${status}`}>{status.replace(/_/g, " ")}</span>;
}

export function PriorityBadge({ priority }: { priority: string }) {
  return <span className={`badge priority-${priority}`}>{priority}</span>;
}
