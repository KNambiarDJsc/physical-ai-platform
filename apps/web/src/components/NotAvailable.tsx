import { PageHeader, Panel } from "./AppShell";

/** A module that does not exist yet says so. It shows no numbers. */
export function NotAvailable({ title, plan }: { title: string; plan: string }) {
  return (
    <>
      <PageHeader title={title} subtitle="Not available yet" />
      <Panel>
        <p className="max-w-2xl text-[13px] text-muted">{plan}</p>
        <p className="mt-3 text-xs text-faint">
          Release Intelligence is the first module. This one is planned and will be built from validated customer
          requirements; nothing on this page is live data.
        </p>
      </Panel>
    </>
  );
}
