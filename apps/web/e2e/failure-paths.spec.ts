import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * E2E-001 failure paths, in a real browser against the real API, worker and pinned engine (scripts/dev_stack.py):
 * unreadable upload, an artifact the mapping rejects, incompatible comparisons, too few samples, a worker killed
 * mid-job, duplicate submission and access from another organization. Releases, uploads and the mapping are set
 * up through the API (the happy path already covers doing that in the UI); every failure is driven and observed
 * through the web app.
 */
const ROOT = path.resolve(__dirname, "../../..");
const DEMO = path.join(ROOT, "examples/manipulation-demo");
const PID_FILE = process.env.PAP_WORKER_PID_FILE ?? path.join(ROOT, "var/dev-stack/worker.pid");
// Under Docker Compose the worker is killed from the host by this command instead (scripts/smoke.sh --compose).
const KILL_CMD = process.env.PAP_WORKER_KILL_CMD;
const run = Date.now().toString(36);
const org = `fail-${run}`;
const owner = `owner-${run}`;
const outsider = `outsider-${run}`;
const P = `/api/v1/orgs/${org}/projects/picking`;
const auth = (u: string) => ({ Authorization: `Bearer dev:${u}` });

test.describe.configure({ mode: "serial" });

let api: APIRequestContext;
const ids: Record<string, string> = {};

test.beforeAll(async ({ playwright, baseURL }) => {
  api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: auth(owner) });
  const ok = async (p: Promise<import("@playwright/test").APIResponse>, status = 201) => {
    const r = await p;
    expect(r.status(), await r.text()).toBe(status);
    return r.json();
  };
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Failure paths" } }));
  await ok(api.post(`/api/v1/orgs/${org}/projects`, { data: { slug: "picking", name: "Picking cell" } }));
  for (const [key, label] of [["baseline", "2.14.0"], ["candidate", "2.15.0-rc1"]]) {
    const comp = [{ kind: "software", name: "pick-stack", version: label }];
    ids[key] = (await ok(api.post(`${P}/releases`, { data: { label, kind: "software", components: comp } }))).id;
    const buffer = readFileSync(path.join(DEMO, "data", `${key}.csv`));
    ids[`${key}_art`] = (await ok(api.post(`${P}/artifacts`, { multipart: { file: { name: `${key}.csv`, mimeType: "text/csv", buffer } } }))).id;
  }
  const mapping = JSON.parse(readFileSync(path.join(DEMO, "mapping.json"), "utf-8"));
  await ok(api.post(`${P}/mappings`, { data: mapping }));
  // The outsider has an organization of their own and no role in this one.
  const other = await api.post("/api/v1/orgs", { headers: auth(outsider), data: { slug: `other-${run}`, name: "Other" } });
  expect(other.status()).toBe(201);
});

test.afterAll(async () => {
  await api?.dispose();
});

/** Kill a process and its children without warning, then check it is gone. */
async function killHard(pid: number) {
  try {
    if (process.platform === "win32") execSync(`taskkill /T /F /PID ${pid}`, { stdio: "ignore" });
    else process.kill(pid, "SIGKILL");
  } catch {
    // taskkill /T exits non-zero when part of the tree has already gone; whether the worker is alive is checked below.
  }
  // On Linux a killed process stays a zombie (still answering signal 0) until its parent reaps it; dev_stack
  // polls every 0.5 s. Wait for it to disappear rather than checking at once (found on CI).
  const gone = () => {
    try {
      process.kill(pid, 0);
      return false;
    } catch {
      return true;
    }
  };
  await expect.poll(gone, { timeout: 10_000, message: `worker ${pid} still running` }).toBe(true);
}

async function signIn(page: Page, user: string) {
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function openProject(page: Page) {
  await page.goto(`/o/${org}/p/picking`);
  await expect(page.getByRole("heading", { name: `${org} / picking` })).toBeVisible();
}

async function pick(page: Page, label: string, file: string) {
  const options = await page.getByLabel(label).locator("option").allTextContents();
  const index = options.findIndex((o) => o.startsWith(file));
  expect(index, `${file} in ${label}`).toBeGreaterThanOrEqual(0);
  await page.getByLabel(label).selectOption({ index });
}

async function fillEvaluation(
  page: Page,
  o: { baseline?: string; candidate?: string; baseFile?: string; taskType?: string; minKnown?: string; paired?: boolean } = {},
) {
  await page.getByLabel("Baseline release").selectOption({ label: o.baseline ?? "2.14.0" });
  await page.getByLabel("Candidate release").selectOption({ label: o.candidate ?? "2.15.0-rc1" });
  await page.getByLabel("Mapping", { exact: true }).selectOption({ label: "warehouse-pick-csv v1" });
  await pick(page, "Baseline evidence", o.baseFile ?? "baseline.csv");
  await pick(page, "Candidate evidence", "candidate.csv");
  await page.getByLabel("Task type").fill(o.taskType ?? "pick_place");
  await page.getByLabel("Minimum known units per release").fill(o.minKnown ?? "30");
  if (o.paired ?? true) await page.getByLabel("Also pair by scenario").check();
}

test.beforeEach(async ({ page }) => {
  await signIn(page, owner);
  await openProject(page);
});

test("an upload that is not text is refused with the reason", async ({ page }) => {
  await page.getByLabel("Evidence file").setInputFiles({ name: "capture.csv", mimeType: "text/csv", buffer: Buffer.from([0x50, 0x4b, 0x00, 0x00, 0xff, 0x00]) });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByText("the file is not text")).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "capture.csv" })).toHaveCount(0);
});

test("an artifact the mapping cannot read fails the evaluation, with the reason", async ({ page }) => {
  await page.getByLabel("Evidence file").setInputFiles({ name: "broken.csv", mimeType: "text/csv", buffer: Buffer.from("episode,episode\n1,2\n") });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "broken.csv" })).toBeVisible();
  await fillEvaluation(page, { baseFile: "broken.csv" });
  await page.getByRole("button", { name: "Start evaluation" }).click();
  await expect(page.getByText(/Evaluation failed: input\.artifact_rejected/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("failed", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download HTML report" })).toHaveCount(0);
});

test("incompatible comparisons are refused", async ({ page }) => {
  // The same release on both sides cannot be submitted at all.
  await fillEvaluation(page, { candidate: "2.14.0" });
  await expect(page.getByRole("button", { name: "Start evaluation" })).toBeDisabled();
  // A task type no episode has: the engine is never asked to compare nothing.
  await fillEvaluation(page, { taskType: "palletize" });
  await page.getByRole("button", { name: "Start evaluation" }).click();
  await expect(page.getByText(/Evaluation failed: input\.task_type/)).toBeVisible({ timeout: 60_000 });
});

test("too few known outcomes give insufficient evidence, not a verdict", async ({ page }) => {
  await fillEvaluation(page, { minKnown: "1000", paired: false });
  await page.getByRole("button", { name: "Start evaluation" }).click();
  const reported = page.getByRole("heading", { name: "Reported by the robot" }).locator("..");
  const verified = page.getByRole("heading", { name: "Independently verified" }).locator("..");
  await expect(reported.getByText("Insufficient evidence")).toBeVisible({ timeout: 120_000 });
  await expect(verified.getByText("Insufficient evidence")).toBeVisible();
  await expect(reported.getByText("Improvement")).toHaveCount(0);
});

test("a worker killed mid-job is replaced and the job finishes; resubmitting returns the same evaluation", async ({ page }) => {
  await fillEvaluation(page);
  await page.getByRole("button", { name: "Start evaluation" }).click();
  await page.waitForURL(/\/e\/[0-9a-f-]{36}$/);
  const url = page.url();
  const id = url.split("/").pop()!;

  // Wait until a worker holds the job, then kill that worker process (and the engine under it) without warning.
  let state = "";
  for (let i = 0; i < 600 && state !== "running"; i++) {
    state = (await (await api.get(`${P}/evaluations/${id}`)).json()).state;
    if (state !== "running") await page.waitForTimeout(100);
  }
  expect(state, "the job never started").toBe("running");
  const pid = KILL_CMD ? null : readFileSync(PID_FILE, "utf-8").trim();
  if (KILL_CMD) execSync(KILL_CMD, { stdio: "inherit", shell: "/bin/bash" });
  else await killHard(Number(pid));

  // The stack starts a new worker; once the lease expires it takes the job over and runs it again from the start.
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({ timeout: 150_000 });
  await expect(page.getByText("attempt 2 of 3")).toBeVisible();
  if (pid) expect(readFileSync(PID_FILE, "utf-8").trim()).not.toBe(pid);
  const reported = page.getByRole("heading", { name: "Reported by the robot" }).locator("..");
  await expect(reported.getByText("Improvement")).toBeVisible();
  await expect(page.getByRole("link", { name: "Contradiction" })).toBeVisible(); // conflicting evidence stays visible

  // Same inputs again: the existing evaluation, not a second run.
  await openProject(page);
  await fillEvaluation(page);
  await page.getByRole("button", { name: "Start evaluation" }).click();
  await page.waitForURL(url);
  await expect(page.getByText("attempt 2 of 3")).toBeVisible();
  ids.evaluation = id;
});

test("another organization's user sees nothing", async ({ browser }) => {
  expect(ids.evaluation).toBeTruthy();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await signIn(page, outsider);
  await page.goto(`/o/${org}/p/picking/e/${ids.evaluation}`);
  await expect(page.getByRole("alert").filter({ hasText: "organization not found" })).toBeVisible(); // not even the organization is confirmed
  await expect(page.getByText("Improvement")).toHaveCount(0);
  await page.goto(`/o/${org}/p/picking/e/${ids.evaluation}/episodes`);
  await expect(page.getByRole("alert").filter({ hasText: "organization not found" })).toBeVisible(); // not even the organization is confirmed
  await expect(page.locator("tbody tr")).toHaveCount(0);
  for (const fmt of ["json", "html"]) {
    const r = await page.request.get(`${P}/evaluations/${ids.evaluation}/report.${fmt}`, { headers: auth(outsider) });
    expect(r.status()).toBe(404);
    expect(await r.text()).not.toContain("pick-stack");
  }
  await ctx.close();
});
