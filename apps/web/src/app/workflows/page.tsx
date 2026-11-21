import { Suspense } from "react";
import { WorkflowsView } from "@/components/Workflows";

export default function Page() {
  return (
    <Suspense>
      <WorkflowsView />
    </Suspense>
  );
}
