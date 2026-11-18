import { PageHeader } from "@/components/AppShell";
import { ProjectList } from "@/components/ProjectList";

export default function Releases() {
  return (
    <>
      <PageHeader title="Releases" subtitle="Choose a project to register releases and compare them." />
      <ProjectList />
    </>
  );
}
