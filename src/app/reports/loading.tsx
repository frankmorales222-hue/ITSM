import { SkeletonNav, SkeletonBar, SkeletonTable } from "@/components/Skeleton";

export default function Loading() {
  return (
    <main>
      <SkeletonNav />
      <SkeletonBar width={140} height={24} style={{ marginBottom: 16 }} />
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="card" style={{ flex: "1 1 160px" }}>
            <SkeletonBar height={14} style={{ marginBottom: 12 }} />
            <SkeletonBar height={28} />
          </div>
        ))}
      </div>
      <SkeletonTable rows={3} />
    </main>
  );
}
