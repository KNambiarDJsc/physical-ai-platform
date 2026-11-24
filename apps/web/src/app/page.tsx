import { PageHeader } from "@/components/AppShell";
import { ProjectList } from "@/components/ProjectList";

export default function ProjectsPage() {
  return (
    <>
      <PageHeader title="Projects" subtitle="Projects you can access. Open a workspace to continue engineering." />
      <ProjectList />
    </>
  );
}
