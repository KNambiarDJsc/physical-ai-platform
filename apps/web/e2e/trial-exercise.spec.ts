import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

/**
 * The trial exercise (trial/EXERCISE.md), done exactly as written, through the web UI only, against a stack started
 * from a clean checkout (scripts/smoke.sh --compose --trial). Checks every answer against trial/expected.json and
 * records how long each task took. This is our own dry run of the instructions, not an external user's result.
 */
test.skip(!process.env.PAP_E2E_TRIAL, "runs only as the trial dry run (bash scripts/smoke.sh --compose --trial)");

const ROOT = path.resolve(__dirname, "../../..");
const EXPECTED = JSON.parse(readFileSync(path.join(ROOT, "trial/expected.json"), "utf-8"));
const run = Date.now().toString(36);
const timings: Record<string, number> = {};
let t = Date.now();
const lap = (task: string) => {
  timings[task] = Math.round((Date.now() - t) / 1000);
  t = Date.now();
};

async function addRelease(page: Page, label: string) {
  await page.getByLabel("Release label").fill(label);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: label })).toBeVisible();
}

async function upload(page: Page, file: string) {
  await page.getByLabel("Evidence file").setInputFiles(path.join(ROOT, file));
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: path.basename(file) }).first()).toBeVisible();
}

async function addMapping(page: Page, file: string, name: string) {
  await page.getByLabel("Mapping (pap.mapping/1 JSON)").fill(readFileSync(path.join(ROOT, file), "utf-8"));
  await page.getByRole("button", { name: "Add version" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: name })).toBeVisible();
}

async function pick(page: Page, label: string, file: string) {
  const options = await page.getByLabel(label).locator("option").allTextContents();
  const index = options.findIndex((o) => o.startsWith(file));
  expect(index, `${file} in ${label}`).toBeGreaterThanOrEqual(0);
  await page.getByLabel(label).selectOption({ index });
}

async function evaluate(
  page: Page,
  o: { baseline: string; candidate: string; mapping: string; baseFile: string; candFile: string; task: string; paired: boolean },
) {
  await page.getByLabel("Baseline release").selectOption({ label: o.baseline });
  await page.getByLabel("Candidate release").selectOption({ label: o.candidate });
  await page.getByLabel("Mapping", { exact: true }).selectOption({ label: o.mapping });
  await pick(page, "Baseline evidence", o.baseFile);
  await pick(page, "Candidate evidence", o.candFile);
  await page.getByLabel("Task type").fill(o.task);
  await page.getByLabel("Minimum known units per release").fill("30");
  const box = page.getByLabel("Also pair by scenario");
  if (o.paired) await box.check();
  else await box.uncheck();
  await page.getByRole("button", { name: "Start evaluation" }).click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({ timeout: 120_000 });
  // The comparison loads after the state turns to succeeded: wait for it before reading anything.
  await expect(page.getByRole("heading", { name: "Independently verified" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("row").filter({ hasText: "Class" }).first()).toBeVisible();
}

async function verdicts(page: Page) {
  const panel = (name: string) => page.getByRole("heading", { name }).locator("..");
  const read = async (name: string) => {
    for (const v of ["Regression", "Improvement", "No change", "Insufficient evidence"]) {
      if (await panel(name).getByText(v, { exact: true }).count()) return v;
    }
    return "?";
  };
  return { reported: await read("Reported by the robot"), verified: await read("Independently verified") };
}

async function classCount(page: Page, cls: string, release: string) {
  const row = page.getByRole("row").filter({ hasText: cls });
  const header = await page.getByRole("row").filter({ hasText: "Class" }).first().locator("th").allTextContents();
  const col = header.findIndex((h) => h.trim() === release);
  expect(col, `column ${release}`).toBeGreaterThan(0);
  return Number((await row.first().locator("td").nth(col).textContent())?.trim() || "0");
}

test("the trial exercise, as written, from a clean install", async ({ page }) => {
  test.setTimeout(900_000);
  const E = EXPECTED;

  // T1: sign in, organization, project
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(`trial-${run}`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Overview" }).click();
  await page.getByLabel("Organization name").fill("Trial");
  await page.getByLabel("Organization slug").fill(`trial-${run}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.getByLabel("Project name").fill("Reaching arm");
  await page.getByLabel("Project slug").fill("reach");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name: "Reaching arm" }).click();
  lap("T1");

  // T2: MuJoCo baseline vs 20 ms latency
  for (const r of ["latency-10ms", "latency-20ms", "latency-10ms-rerun"]) await addRelease(page, r);
  for (const g of ["A", "C", "D"]) await upload(page, `examples/mujoco-regression/data/${g}.csv`);
  await addMapping(page, "examples/mujoco-regression/mapping.json", "mujoco-reach-ground-truth");
  const projectUrl = page.url();
  await evaluate(page, { baseline: "latency-10ms", candidate: "latency-20ms", mapping: "mujoco-reach-ground-truth v1",
    baseFile: "A.csv", candFile: "D.csv", task: "reach", paired: true });
  const t2 = await verdicts(page);
  expect(t2).toEqual(E.T2.verdicts);
  expect(await classCount(page, "Verified failure", "latency-20ms")).toBe(E.T2.verified_failures_candidate);
  expect(await classCount(page, "Contradiction", "latency-20ms")).toBe(E.T2.contradictions_candidate);
  const evaluationUrl = page.url();
  lap("T2");

  // T3: explain one verified failure
  await page.getByRole("link", { name: "Verified failure" }).first().click();
  await page.locator("tbody button").first().click();
  await expect(page.getByRole("heading", { name: "Conditions" })).toBeVisible();
  await expect(page.getByText(E.T3.why_text)).toBeVisible();
  const observed = await page.getByRole("row").filter({ hasText: E.T3.condition }).locator("td").nth(3).textContent();
  const metres = Number((observed ?? "").replace(/[^0-9.]/g, ""));
  expect(metres).toBeGreaterThan(E.T3.threshold_m);
  await expect(page.getByRole("row").filter({ hasText: E.T3.condition }).getByText("false")).toBeVisible();
  lap("T3");

  // T4: no-change control
  await page.goto(projectUrl);
  await evaluate(page, { baseline: "latency-10ms", candidate: "latency-10ms-rerun", mapping: "mujoco-reach-ground-truth v1",
    baseFile: "A.csv", candFile: "C.csv", task: "reach", paired: false });
  expect(await verdicts(page)).toEqual(E.T4.verdicts);
  await expect(page.getByText(E.T4.reason)).toBeVisible();
  lap("T4");

  // T5: real flights (physical evidence)
  await page.getByRole("link", { name: "Overview" }).click();
  await page.getByLabel(`Project name`).first().fill("Drone flights");
  await page.getByLabel(`Project slug`).first().fill("drones");
  await page.getByRole("button", { name: "Create project" }).first().click();
  await page.getByRole("link", { name: "Drone flights" }).click();
  for (const r of ["condition-no_failure", "condition-panel_failure"]) await addRelease(page, r);
  for (const f of ["no_failure.csv", "panel_failure.csv"]) await upload(page, `examples/coresense/data/${f}`);
  await addMapping(page, "examples/coresense/mapping.json", "coresense-goto-mocap");
  await evaluate(page, { baseline: "condition-no_failure", candidate: "condition-panel_failure",
    mapping: "coresense-goto-mocap v1", baseFile: "no_failure.csv", candFile: "panel_failure.csv", task: "goto", paired: true });
  expect(await verdicts(page)).toEqual(E.T5.verdicts);
  await expect(page.getByText(E.T5.evidence_label).first()).toBeVisible();
  expect(await classCount(page, "Contradiction", "condition-no_failure")).toBe(E.T5.contradictions_baseline);
  lap("T5");

  // T6: the report is reproducible
  await page.goto(evaluationUrl);
  const digests: string[] = [];
  for (let i = 0; i < 2; i++) {
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download JSON report" }).click()]);
    digests.push(createHash("sha256").update(readFileSync(await dl.path())).digest("hex"));
  }
  expect(digests[0]).toBe(digests[1]);
  lap("T6");

  const dest = process.env.PAP_TRIAL_OUT ?? test.info().outputDir;
  mkdirSync(dest, { recursive: true });
  writeFileSync(path.join(dest, "part-a-timings.json"), JSON.stringify({ timings_s: timings, report_sha256: digests[0] }, null, 2));
  console.log(`trial timings (s): ${JSON.stringify(timings)}`);
});
