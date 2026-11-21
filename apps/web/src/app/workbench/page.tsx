import { Suspense } from "react";
import { WorkbenchView } from "@/components/Workbench";

export default function Page() {
  return (
    <Suspense>
      <WorkbenchView />
    </Suspense>
  );
}
