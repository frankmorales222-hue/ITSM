import { SkeletonNav, SkeletonTable } from "@/components/Skeleton";

export default function Loading() {
  return (
    <main>
      <SkeletonNav />
      <SkeletonTable rows={4} />
    </main>
  );
}
