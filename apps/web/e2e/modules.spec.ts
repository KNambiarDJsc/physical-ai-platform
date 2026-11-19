import { expect, test, type APIResponse } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Fleet, Incidents, Verification, Evidence and Integrations, in a real browser against the real API, worker and
 * pinned engine. One MuJoCo regression is evaluated through the API; every page is then checked for the numbers the
 * engine produced (the answer key is trial/expected.json), and a signed-out visitor is checked to see no data.
 */
const ROOT = path.resolve(__dirname, "../../..");
const MJ = path.join(ROOT, "examples/mujoco-regression");
const EXPECTED = JSON.parse(readFileSync(path.join(ROOT, "trial/expected.json"), "utf-8"));
const run = Date.now().toString(36);
const org = `modules-${run}`;
const user = `modules-${run}`;
const P = `/api/v1/orgs/${org}/projects/reach`;

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ playwright, baseURL }) => {
  test.setTimeout(240_000);
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  const ok = async (p: Promise<APIResponse>, status = 201) => {
    const r = await p;
    expect(r.status(), await r.text()).toBe(status);
    return r.json();
  };
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Modules" } }));
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
});

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("a signed-out visitor sees no data on any module page", async ({ page }) => {
  for (const p of ["fleet", "incidents", "verification", "evidence", "integrations"]) {
    await page.goto(`/${p}`);
    await expect(page.getByText("Not signed in")).toBeVisible();
    await expect(page.getByText("Reaching arm")).toHaveCount(0);
  }
});

test("no module is marked as coming soon", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("navigation", { name: "Main" })).not.toContainText("Soon");
});

test("Verification: the engine's verdicts and the contradiction count", async ({ page }) => {
  await signIn(page);
  await page.goto("/verification");
  const row = page.getByRole("row").filter({ hasText: "latency-10ms → latency-20ms" });
  await expect(row).toBeVisible();
  await expect(row.getByText("Regression")).toHaveCount(2);
  await expect(row.getByText("simulated")).toBeVisible();
  await expect(row.getByRole("cell", { name: String(EXPECTED.T2.contradictions_candidate + 5) })).toBeVisible();
});

test("Fleet: the robot and its outcome counts", async ({ page }) => {
  await signIn(page);
  await page.goto("/fleet");
  await expect(page.getByRole("heading", { name: /Reaching arm · 1 robot, 300 episodes/ })).toBeVisible();
  const cand = page.getByRole("row").filter({ hasText: "sim/planar-arm" }).filter({ hasText: "latency-20ms" });
  await expect(cand.getByRole("cell").nth(6)).toHaveText(String(EXPECTED.T2.verified_failures_candidate));
  await expect(cand.getByRole("cell").nth(7)).toHaveText(String(EXPECTED.T2.contradictions_candidate));
});

test("Incidents: engine incidents with their explanation", async ({ page }) => {
  await signIn(page);
  await page.goto("/incidents");
  await expect(page.getByText(/INC-[0-9a-f]{12}/).first()).toBeVisible();
  await expect(page.getByText(/fingertip within 0.02 m of the target/).first()).toBeVisible();
});

test("Evidence: uploaded files with digests and where they were used", async ({ page }) => {
  await signIn(page);
  await page.goto("/evidence");
  const a = page.getByRole("row").filter({ hasText: "A.csv" });
  await expect(a).toContainText("source");
  await expect(a).toContainText("1 evaluation");
  await expect(a.getByRole("cell").nth(3)).toHaveText(/^[0-9a-f]{12}$/);
  await expect(page.getByRole("row").filter({ hasText: "events.jsonl" })).toContainText("engine output");
});

test("Integrations: the pinned engine and the API surface", async ({ page }) => {
  await signIn(page);
  await page.goto("/integrations");
  await expect(page.getByText("openmhs 0.1.0")).toBeVisible();
  await expect(page.getByText(`POST ${P}/evaluations`)).toBeVisible();
  await expect(page.getByText(/Not integrated yet/)).toBeVisible();
});
