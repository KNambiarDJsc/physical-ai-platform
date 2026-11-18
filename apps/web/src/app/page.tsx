import { PageHeader } from "@/components/AppShell";
import { ProjectList } from "@/components/ProjectList";

export default function Overview() {
  return (
    <>
      <PageHeader title="Overview" subtitle="Projects you can access. Open one to compare releases." />
      <ProjectList />
    </>
  );
}
