import { Suspense } from "react";
import { HardwareView } from "@/components/Hardware";

export default function Page() {
  return (
    <Suspense>
      <HardwareView />
    </Suspense>
  );
}
