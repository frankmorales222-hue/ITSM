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

export function SkeletonNav() {
  return (
    <div className="nav" style={{ gap: 16 }}>
      <SkeletonBar width={90} height={14} style={{ marginBottom: 0 }} />
      <SkeletonBar width={110} height={14} style={{ marginBottom: 0 }} />
      <SkeletonBar width={80} height={14} style={{ marginBottom: 0 }} />
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
