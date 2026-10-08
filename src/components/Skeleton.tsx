export function SkeletonBar({
  width = "100%",
  height = 16,
  style,
}: {
  width?: string | number;
  height?: number;
  style?: React.CSSProperties;
}) {
  return <div className="skeleton" style={{ width, height, marginBottom: 8, ...style }} />;
}

// Mirrors the real sidebar's shape (see .sidebar in globals.css) so the
// loading state doesn't cause a layout jump when the real <Nav> swaps in.
export function SkeletonNav() {
  return (
    <div className="sidebar">
      <SkeletonBar width={100} height={16} style={{ marginBottom: 20 }} />
      {Array.from({ length: 4 }).map((_, i) => (
        <SkeletonBar key={i} height={13} style={{ marginBottom: 12 }} />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div>
      <SkeletonBar width={140} height={24} style={{ marginBottom: 16 }} />
      <div className="card">
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonBar key={i} height={20} />
        ))}
      </div>
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div>
      <SkeletonBar width={220} height={24} style={{ marginBottom: 16 }} />
      <div className="card">
        <SkeletonBar height={16} />
        <SkeletonBar height={16} />
        <SkeletonBar width="60%" height={16} />
      </div>
    </div>
  );
}
