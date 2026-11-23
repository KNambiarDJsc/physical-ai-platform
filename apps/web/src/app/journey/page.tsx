import { Suspense } from "react";
import { JourneyView } from "@/components/Journey";

export default function Page() {
  return (
    <Suspense>
      <JourneyView />
    </Suspense>
  );
}
