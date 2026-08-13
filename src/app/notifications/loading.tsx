import { SkeletonNav, SkeletonTable } from "@/components/Skeleton";

export default function Loading() {
  return (
    <main>
      <SkeletonNav />
      <SkeletonTable rows={3} />
    </main>
  );
}
