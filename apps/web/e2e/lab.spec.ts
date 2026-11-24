import { expect, test, type APIResponse } from "@playwright/test";

/**
 * The lab-automation milestone, against the real stack (API, worker, LabThings virtual laboratory, pinned engine).
 *
 * ONB-001: a new user registers a simulated instrument, discovers its capabilities, executes a workflow and receives an
 * engine-verified result through the interface only. WB-001: the Workbench starts and follows a run; an injected fault
 * shows as a contradiction; panels resize by keyboard.
 *
 * One serial file: every test shares the one virtual laboratory, and the fault test must not overlap another run.
 */
const run = Date.now().toString(36);
const user = `bench-${run}`;
const newcomer = `newcomer-${run}`;
const org = `bench-${run}`;
const O = `/api/v1/orgs/${org}`;
let lab = "";

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ playwright, baseURL }) => {
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  const ok = async (p: Promise<APIResponse>, status = 200) => {
    const r = await p;
    expect(r.status(), await r.text()).toBe(status);
    return r.json();
  };
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Bench" } }), 201);
  await ok(api.post(`${O}/environments`, { data: { config_key: "virtual-lab" } }), 201);
  await ok(api.post(`${O}/environments/virtual-lab/discover`));
  const body = { slug: "dispense", name: "Dispense 100 µL", environment: "virtual-lab", template: "dispense-and-verify", parameters: { volume_ul: 100 } };
  await ok(api.post(`${O}/workflows`, { data: body }), 201);
  // The API reaches the lab at its catalog endpoint; under Compose that name resolves only inside the network.
  lab = process.env.PAP_LAB_URL ?? (await ok(api.get("/api/v1/environment-catalog"))).find((c: { key: string }) => c.key === "virtual-lab").endpoint;
});

async function labAction(request: import("@playwright/test").APIRequestContext, thing: string, action: string, data: object = {}) {
  const r = await request.post(`${lab}/${thing}/${action}`, { data });
  expect(r.status()).toBe(201);
  let inv = await r.json();
  for (let i = 0; i < 100 && !["completed", "error", "cancelled"].includes(inv.status); i++) {
    await new Promise((res) => setTimeout(res, 100));
    inv = await (await request.get(inv.href)).json();
  }
  expect(inv.status).toBe("completed");
}

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("a new user goes from sign-in to an engine-verified result through the interface only", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(newcomer);
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.getByRole("button", { name: /Go to/ }).click();
  const pageFinder = page.getByRole("dialog", { name: "Command palette" });
  await pageFinder.getByRole("combobox", { name: "Go to page" }).fill("get started");
  await pageFinder.getByRole("option", { name: /Get started/ }).click();
  await expect(page.getByRole("heading", { name: "Get started", level: 1 })).toBeVisible();

  // 1. Workspace
  await page.getByLabel("Workspace name").fill(`Lab ${run}`);
  await expect(page.getByLabel("Workspace slug")).toHaveValue(`lab-${run}`);
  await page.getByRole("button", { name: "Create workspace" }).click();

  // 2. Environment, from the operator's catalog only
  await expect(page.getByRole("group", { name: "Environments offered by this installation" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Virtual laboratory/ })).toBeChecked();
  await expect(page.getByText("SIMULATED").first()).toBeVisible();
  await page.getByRole("button", { name: "Connect environment" }).click();

  // 3. Discovery
  await page.getByRole("button", { name: /Discover devices in virtual-lab/ }).click();

  // 4. Workflow from the template; its form is generated from the template's parameter schema
  await expect(page.getByText("Dispense and verify.")).toBeVisible();
  await expect(page.getByLabel("Volume to dispense, in µL.")).toHaveValue("50");
  await page.getByLabel("Accepted deviation of the delivered volume, ±%.").fill("2");
  await page.getByRole("button", { name: "Create workflow" }).click();

  // 5. Run: the worker executes it, the engine verifies it
  await page.getByRole("button", { name: /^Run Dispense and verify/ }).click();
  const result = page.getByRole("status").filter({ hasText: "Verified by the engine" });
  await expect(result).toBeVisible({ timeout: 90_000 });
  await expect(result.getByText("succeeded")).toBeVisible();
  await expect(result.getByText("satisfied")).toBeVisible();
  await expect(result.getByText("Supported success")).toBeVisible();
  for (const n of [1, 2, 3, 4, 5]) await expect(page.getByRole("listitem").filter({ hasText: "Done" }).nth(n - 1)).toBeVisible();

  // The same run, in the Workbench: steps, the instrument's claim, the engine's verdict and its provenance.
  await result.getByRole("link", { name: "Open in the Workbench" }).click();
  await expect(page.getByRole("heading", { name: "Workbench", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reported by the instrument" })).toBeVisible();
  await expect(page.getByText("reported_dispensed_ul = 50")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Verification" })).toBeVisible();
  await expect(page.getByText(/^openmhs 0\.1\.0 · [0-9a-f]{9} · [0-9a-f]{12}$/)).toBeVisible();
  // The engine's observed value for the balance reading, in grams, and whether the condition was met.
  await expect(page.getByText(/delivered_mass between: met, observed 0\.0(49|50)\d g/)).toBeVisible();
  await page.getByRole("button", { name: /pump\.dispense/ }).click();
  await expect(page.getByText("Yes: the device ignores a repeated request id")).toBeVisible();
  await expect(page.getByText(/"reported_dispensed_ul": 50/)).toBeVisible();

  // Discovered capabilities are inspectable in the Hardware Hub, with live reads.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Integrations" }).click();
  await page.getByRole("navigation", { name: "Devices" }).getByRole("button", { name: "balance" }).click();
  await page.getByRole("button", { name: "Read readability_g" }).click();
  await expect(page.getByRole("row").filter({ hasText: "readability_g" })).toContainText("0.0001");
  await expect(page.getByText("idempotent · request_id")).toHaveCount(0); // the balance has none; the pump's dispense does
});

test("a run started from the Workbench is executed, followed live and verified", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page);
  await page.goto(`/workbench?org=${org}`);
  await expect(page.getByRole("heading", { name: /Instruments/ })).toBeVisible();
  await expect(page.getByText("mass_g")).toBeVisible();
  await page.getByRole("button", { name: "Run workflow" }).click();
  await expect(page.getByRole("heading", { name: "Independently verified (OpenMHS engine)" })).toBeVisible();
  await expect(page.getByText("Supported success")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("img", { name: "Step timeline" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "balance.weigh" }).getByText("Completed")).toBeVisible();
});

test("an injected blockage is a contradiction: reported success, verdict violated", async ({ page, request }) => {
  test.setTimeout(120_000);
  await labAction(request, "simulation", "set_fault", { fault: "partial_blockage" });
  try {
    await signIn(page);
    await page.goto(`/workbench?org=${org}`);
    await page.getByRole("button", { name: "Run workflow" }).click();
    await expect(page.getByText("Contradiction").first()).toBeVisible({ timeout: 60_000 });
    const reported = page.getByRole("region", { name: "Reported by the instrument" });
    await expect(reported.getByText("succeeded")).toBeVisible();
    await page.getByText("Investigate with Engineering Agent", { exact: true }).click();
    await expect(page.getByLabel("Question", { exact: true })).toHaveValue(/Investigate workflow run .*verification result/);
    await expect(reported.getByText("reported_dispensed_ul = 100")).toBeVisible();
    await expect(page.getByRole("region", { name: "Independently verified (OpenMHS engine)" }).getByText("violated")).toBeVisible();
    const runId = new URL(page.url()).searchParams.get("run");
    expect(runId).toBeTruthy();
    await page.goto(`/runs?org=${org}`);
    await page.getByLabel("Find a run").fill(runId!);
    await page.getByRole("link").filter({ hasText: runId! }).click();
    await expect(page).toHaveURL(new RegExp(runId!));
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Independently verified (OpenMHS engine)" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    if (process.env.PAP_DESIGN_CAPTURE === "after") {
      await page.screenshot({ path: "../../docs/design/screenshots/lab-mobile.png" });
    }
  } finally {
    await labAction(request, "simulation", "reset");
  }
});

test("panels resize by keyboard", async ({ page }) => {
  await signIn(page);
  await page.goto(`/workbench?org=${org}`);
  const sep = page.getByRole("separator", { name: "Resize the evidence panel" });
  await expect(sep).toHaveAttribute("aria-valuenow", "320");
  await sep.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(sep).toHaveAttribute("aria-valuenow", "336");
  await page.keyboard.press("Home");
  await expect(sep).toHaveAttribute("aria-valuenow", "260");
});

test("an assistant's proposal waits for an engineer, who approves it in the interface; the run executes and is verified", async ({
  page,
  playwright,
  baseURL,
}) => {
  test.setTimeout(150_000);
  const admin = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  const viewer = `viewer-${run}`;
  expect((await admin.put(`${O}/members`, { data: { issuer: "dev", subject: viewer, role: "viewer" } })).status()).toBe(200);
  // What the assistant tools do: a viewer credential and the agent-tools channel header. Viewers cannot approve.
  const assistant = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { Authorization: `Bearer dev:${viewer}`, "X-PAP-Channel": "agent-tools" },
  });
  const made = await assistant.post(`${O}/experiment-proposals`, {
    data: { workflow: "dispense", rationale: "Repeat the dispense to check whether the shortfall repeats.", evidence_ids: ["run:example"] },
  });
  expect(made.status()).toBe(201);
  expect((await assistant.post(`${O}/experiment-proposals/${(await made.json()).id}/approve`, { data: {} })).status()).toBe(403);

  const signAs = async (who: string) => {
    await page.goto("/settings");
    await page.getByLabel("Subject").fill(who);
    await page.getByRole("button", { name: "Sign in" }).click();
  };
  await signAs(viewer);
  await page.goto(`/workflows?org=${org}`);
  const row = page.getByRole("row").filter({ hasText: "Repeat the dispense to check" });
  await expect(row).toContainText("via assistant tools");
  await expect(row).toContainText("awaiting an engineer");
  await expect(row.getByRole("button", { name: /Approve/ })).toHaveCount(0);

  await signAs(user);
  await page.goto(`/workflows?org=${org}`);
  await row.getByRole("button", { name: "Approve proposal for dispense" }).click();
  await expect(row).toContainText("approved");
  await row.getByRole("link", { name: "Open the run" }).click();
  await expect(page.getByRole("heading", { name: "Independently verified (OpenMHS engine)" })).toBeVisible();
  await expect(page.getByText("Supported success")).toBeVisible({ timeout: 90_000 });
});
