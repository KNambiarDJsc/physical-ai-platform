import { Suspense } from "react";
import { AgentView } from "@/components/Agent";

export default function Page() {
  return (
    <Suspense>
      <AgentView />
    </Suspense>
  );
}
