import { Suspense } from "react";
import { OnboardingView } from "@/components/Onboarding";

export default function Page() {
  return (
    <Suspense>
      <OnboardingView />
    </Suspense>
  );
}
