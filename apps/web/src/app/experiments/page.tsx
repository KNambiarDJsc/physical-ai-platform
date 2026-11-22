import { Suspense } from "react";
import { StudioView } from "@/components/experiments/Studio";

export default function Page() {
  return (
    <Suspense>
      <StudioView />
    </Suspense>
  );
}
