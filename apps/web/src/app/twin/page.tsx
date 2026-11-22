import { Suspense } from "react";
import { TwinView } from "@/components/twin/Twin";

export default function Page() {
  return (
    <Suspense>
      <TwinView />
    </Suspense>
  );
}
