import { SkeletonNav, SkeletonBar } from "@/components/Skeleton";

export default function Loading() {
  return (
    <main>
      <SkeletonNav />
      <SkeletonBar width={140} height={24} style={{ marginBottom: 16 }} />
      <div className="widget-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card" style={{ minHeight: 100 }}>
            <SkeletonBar height={14} style={{ marginBottom: 12 }} />
            <SkeletonBar height={28} />
          </div>
        ))}
      </div>
    </main>
  );
}
