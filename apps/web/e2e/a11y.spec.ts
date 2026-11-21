import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Accessibility gate (DESIGN.md §11): axe-core's WCAG 2.0/2.1/2.2 A and AA rules on every page, in the dark and the
 * light theme, against real data (one MuJoCo evaluation run through the API, worker and pinned engine). Plus the
 * keyboard behaviour of the command palette.
 */
const ROOT = path.resolve(__dirname, "../../..");
const MJ = path.join(ROOT, "examples/mujoco-regression");
const run = Date.now().toString(36);
const org = `a11y-${run}`;
const user = `a11y-${run}`;
const P = `/api/v1/orgs/${org}/projects/reach`;
let evaluation = "";

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ playwright, baseURL }) => {
  test.setTimeout(240_000);
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  const ok = async (p: Promise<APIResponse>, status = 201) => {
    const r = await p;
    expect(r.status(), await r.text()).toBe(status);
    return r.json();
  };
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Accessibility" } }));
  await ok(api.post(`/api/v1/orgs/${org}/projects`, { data: { slug: "reach", name: "Reaching arm" } }));
  const rel: Record<string, string> = {};
  const art: Record<string, string> = {};
  for (const [g, label] of [["A", "latency-10ms"], ["D", "latency-20ms"]]) {
    const comp = [{ kind: "software", name: "reach-controller", version: label }];
    rel[g] = (await ok(api.post(`${P}/releases`, { data: { label, kind: "software", components: comp } }))).id;
    art[g] = (
      await ok(api.post(`${P}/artifacts`, { multipart: { file: { name: `${g}.csv`, mimeType: "text/csv", buffer: readFileSync(path.join(MJ, "data", `${g}.csv`)) } } }))
    ).id;
  }
  const mapping = (await ok(api.post(`${P}/mappings`, { data: JSON.parse(readFileSync(path.join(MJ, "mapping.json"), "utf-8")) }))).id;
  let job = await ok(
    api.post(`${P}/evaluations`, {
      data: {
        baseline_release_id: rel.A, candidate_release_id: rel.D, mapping_id: mapping,
        baseline_artifact_ids: [art.A], candidate_artifact_ids: [art.D],
        config: { task_type: "reach", paired: true, min_known: 30, margin: 0.01, stratify_by_site: false },
      },
    }),
  );
  for (let i = 0; i < 240 && ["queued", "running"].includes(job.state); i++) {
    await new Promise((r) => setTimeout(r, 500));
    job = await (await api.get(`${P}/evaluations/${job.id}`)).json();
  }
  expect(job.state).toBe("succeeded");
  evaluation = job.id;
  // Lab automation: an environment, its devices, a workflow and one finished run.
  const O = `/api/v1/orgs/${org}`;
  await ok(api.post(`${O}/environments`, { data: { config_key: "virtual-lab" } }));
  await ok(api.post(`${O}/environments/virtual-lab/discover`), 200);
  const wf = { slug: "dispense", name: "Dispense and verify", environment: "virtual-lab", template: "dispense-and-verify", parameters: {} };
  await ok(api.post(`${O}/workflows`, { data: wf }));
  let r = await ok(api.post(`${O}/workflows/dispense/runs`));
  for (let i = 0; i < 240 && ["queued", "running"].includes(r.state); i++) {
    await new Promise((res) => setTimeout(res, 500));
    r = await (await api.get(`${O}/workflow-runs/${r.id}`)).json();
  }
  expect(r.state).toBe("succeeded");
});

async function signIn(page: Page, theme: "dark" | "light") {
  const url = test.info().project.use.baseURL ?? "http://127.0.0.1:3000";
  await page.context().addCookies([{ name: "pap_theme", value: theme, url }]);
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
}

const pages = () => [
  ["/", "Projects you can access"],
  ["/releases", "Reaching arm"],
  ["/verification", "latency-10ms"],
  ["/incidents", "INC-"],
  ["/evidence", "A.csv"],
  ["/fleet", "sim/planar-arm"],
  ["/integrations", "Not integrated yet"],
  ["/settings", "Signed in as"],
  [`/o/${org}/p/reach`, "New evaluation"],
  [`/o/${org}/p/reach/e/${evaluation}`, "Independently verified"],
  [`/o/${org}/p/reach/e/${evaluation}/episodes`, "Episodes"],
  [`/onboarding?org=${org}`, "Every step is done"],
  [`/workbench?org=${org}`, "Independently verified (OpenMHS engine)"],
  [`/hardware?org=${org}`, "Discover devices"],
  [`/workflows?org=${org}`, "Recent runs"],
];

for (const theme of ["dark", "light"] as const) {
  test(`no WCAG A/AA violations on any page (${theme} theme)`, async ({ page }) => {
    test.setTimeout(180_000);
    await signIn(page, theme);
    const failures: string[] = [];
    for (const [url, ready] of pages()) {
      await page.goto(url);
      await page.getByText(ready).first().waitFor({ timeout: 30_000 });
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      for (const v of result.violations) {
        failures.push(`${url} [${v.impact}] ${v.id}: ${v.help}\n    ${v.nodes.slice(0, 4).map((n) => n.target.join(" ")).join("\n    ")}`);
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
  });
}

test("command palette: opens with Ctrl K, keeps focus inside, Escape returns focus", async ({ page }) => {
  await signIn(page, "dark");
  await page.goto("/verification");
  const trigger = page.getByRole("button", { name: /^Go to/ });
  await trigger.focus();
  await page.keyboard.press("Control+k");
  const box = page.getByRole("combobox", { name: "Go to page" });
  await expect(box).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(box).toBeFocused();
  await box.fill("evid");
  await expect(page.getByRole("option")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: "Go to page" }).fill("fleet");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/fleet$/);
});
