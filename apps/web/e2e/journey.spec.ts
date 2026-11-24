import { expect, test, type APIResponse, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * The Laboratory experiment journey, end to end in a real browser against the real stack: API, durable worker, the
 * LabThings virtual laboratory (pump, balance, simulation controls), the pinned OpenMHS engine and the real harness
 * (its rule-based fallback: no model is used, so no cost).
 *
 *   discover -> configure a procedure with an explicit tolerance -> request -> approval by a second person (the
 *   requester's own approval is refused) -> a successful run -> a genuine failing run (a simulated partial blockage,
 *   injected by a journaled step of the workflow, nothing edited afterwards) -> investigation citing stored evidence ->
 *   a drafted follow-up that a person files and a different person must still approve -> exported evidence.
 *
 * Runs after the other specs (see playwright.config.ts): it injects faults into the one shared virtual laboratory.
 */
const run = Date.now().toString(36);
const org = `journey-${run}`;
const ada = `ada-${run}`; // admin: the researcher
const bob = `bob-${run}`; // engineer: the second person
const vic = `vic-${run}`; // viewer
const O = `/api/v1/orgs/${org}`;
const OK_PROC = "dispense-50ul";
const FAULT_PROC = "dispense-50ul-blocked-line";

test.describe.configure({ mode: "serial" });
let runner = true; // a deployment without an agent runner (the Compose image) cannot do the agent steps

test.beforeAll(async ({ playwright, baseURL }) => {
  test.setTimeout(120_000);
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${ada}` } });
  const ok = async (p: Promise<APIResponse>, status = 200) => {
    const r = await p;
    expect(r.status(), await r.text()).toBe(status);
    return r.json();
  };
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Journey" } }), 201);
  await ok(api.put(`${O}/members`, { data: { issuer: "dev", subject: bob, role: "engineer" } }));
  await ok(api.put(`${O}/members`, { data: { issuer: "dev", subject: vic, role: "viewer" } }));
  await ok(api.post(`${O}/environments`, { data: { config_key: "virtual-lab" } }), 201);
  await ok(api.post(`${O}/environments/virtual-lab/discover`));
  runner = (await (await api.get(`${O}/agent/status`)).json()).runner_available;
  const base = { environment: "virtual-lab" };
  await ok(api.post(`${O}/workflows`, { data: { ...base, slug: OK_PROC, name: "Dispense 50 µL (normal bench)", template: "dispense-and-verify", parameters: { volume_ul: 50, tolerance_pct: 2 } } }), 201);
  await ok(api.post(`${O}/workflows`, { data: { ...base, slug: FAULT_PROC, name: "Dispense 50 µL (simulated partial blockage)", template: "dispense-with-fault", parameters: { volume_ul: 50, tolerance_pct: 2, fault: "partial_blockage" } } }), 201);
});

async function signIn(page: Page, subject: string) {
  await page.goto("/settings");
  await page.getByLabel("Subject", { exact: true }).fill(subject);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function request(page: Page, procedure: string, why: string) {
  await page.goto(`/journey?org=${org}`);
  await page.getByLabel("Procedure").selectOption(procedure);
  await page.getByLabel(/^Why run it/).fill(why);
  await page.getByRole("button", { name: "Request run" }).click();
  await expect(page.getByText("awaiting approval").first()).toBeVisible();
}

async function approveAs(page: Page, subject: string, procedure: string) {
  await signIn(page, subject);
  await page.goto(`/workflows?org=${org}`);
  await page.getByRole("button", { name: `Approve proposal for ${procedure}`, exact: true }).first().click();
  // the row of THIS procedure (a slug can be a prefix of another's), not whichever run is listed first
  const row = page.getByRole("row").filter({ hasText: new RegExp(`${procedure}(?![-a-z0-9])`) });
  await row.getByRole("link", { name: "Open the run" }).click();
}

test("discover, configure, request, approve, run, fail, investigate, draft, export", async ({ page }) => {
  test.setTimeout(420_000);
  await signIn(page, ada);

  // 1 and 2: the instruments and the procedures with their explicit tolerance
  await page.goto(`/journey?org=${org}`);
  await expect(page.getByRole("heading", { name: "Laboratory experiment", level: 1 })).toBeVisible();
  await expect(page.getByText("simulated bench: no physical hardware")).toBeVisible();
  const step1 = page.getByRole("heading", { name: "Discover the instruments" }).locator("xpath=ancestor::li");
  for (const d of ["pump", "balance", "simulation"]) await expect(step1.getByText(d, { exact: true })).toBeVisible();
  await expect(step1.getByText("SIMULATED").first()).toBeVisible();
  const step2 = page.getByRole("heading", { name: "Configure the procedure and its tolerance" }).locator("xpath=ancestor::li");
  await expect(step2.getByText(OK_PROC, { exact: true })).toBeVisible();
  await expect(step2.getByText("50 µL, accepted within ±2 %")).toHaveCount(2);
  await expect(step2.getByText("simulated fault: partial blockage")).toBeVisible();

  // 3: a request, and the requester cannot approve it
  await request(page, OK_PROC, "Baseline: confirm the healthy bench meets the tolerance.");
  await page.goto(`/workflows?org=${org}`);
  await page.getByRole("button", { name: `Approve proposal for ${OK_PROC}`, exact: true }).click();
  await expect(page.getByText("must be approved by someone other than whoever proposed it")).toBeVisible();

  // a second person approves; the worker runs it; the engine judges it
  await approveAs(page, bob, OK_PROC);
  await expect(page.getByText("Supported success").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("SIMULATED EVIDENCE").first()).toBeVisible();

  // 5 and 6: a genuine failing run, from a fault injected by the workflow's own journaled step
  await signIn(page, ada);
  await request(page, FAULT_PROC, "Reproduce a blocked line and see how the evidence shows it.");
  await approveAs(page, bob, FAULT_PROC);
  await expect(page.getByText("Contradiction").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("simulation.set_fault").first()).toBeVisible(); // the injected fault is a visible step

  // the journey now shows both runs, with the engine's verdicts
  await signIn(page, ada);
  await page.goto(`/journey?org=${org}`);
  const step4 = page.getByRole("heading", { name: "Inspect the runs" }).locator("xpath=ancestor::li");
  await expect(step4.getByRole("link", { name: "Dispense 50 µL (normal bench)" })).toBeVisible();
  await expect(step4.getByRole("link", { name: "Dispense 50 µL (simulated partial blockage)" })).toBeVisible();

  if (runner) {
    // investigation by fixed rules (no model): cites stored ids, says so, and drafts a follow-up
    await page.getByRole("link", { name: "Rule-based investigation (no model)" }).click();
    await expect(page.getByLabel("Question")).toHaveValue(/^Investigate workflow run /);
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({ timeout: 180_000 });
    const answer = page.getByRole("region", { name: "Answer" });
    await expect(answer.getByText(/does not support it/)).toBeVisible();
    await expect(answer.getByText(/not a model/)).toBeVisible();
    await expect(page.getByText("no model used")).toBeVisible();
    await expect(page.getByText("drafted, not filed")).toBeVisible();

    // a person files the draft; it is a proposal like any other and still needs someone else
    await page.getByRole("button", { name: "File as a proposal" }).click();
    await expect(page.getByText("It is waiting for someone other than whoever filed it.")).toBeVisible();
    await page.goto(`/workflows?org=${org}`);
    await expect(page.getByText("via assistant tools")).toBeVisible();
    await expect(page.getByRole("button", { name: `Approve proposal for ${FAULT_PROC}`, exact: true })).toHaveCount(1); // pending, not run
  } else {
    // no agent runner here (the Compose image): the page must say so, and nothing can be asked
    await page.getByRole("link", { name: "Rule-based investigation (no model)" }).click();
    await expect(page.getByText("The agent is not available on this server")).toBeVisible();
    await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeDisabled();
  }

  // 6: the exported evidence, from stored records only
  await page.goto(`/journey?org=${org}`);
  const step6 = page.getByRole("heading", { name: "Export the evidence" }).locator("xpath=ancestor::li");
  const failing = step6.getByRole("listitem").filter({ hasText: "Dispense 50 µL (simulated partial blockage)" });
  const [download] = await Promise.all([page.waitForEvent("download"), failing.getByRole("button", { name: "Download JSON" }).click()]);
  const report = JSON.parse(readFileSync((await download.path())!, "utf-8"));
  expect(report.schema).toBe("pap.lab-run-report/1");
  expect(report.evidence_class).toBe("simulated");
  expect(report.independently_verified.verdict).toBe("VIOLATED");
  expect(report.independently_verified.outcome_class).toBe("contradiction");
  expect(report.reported_by_instrument.value).toBe("succeeded"); // the pump's claim, unedited
  expect(report.execution.map((s: { action: string }) => s.action)).toEqual(["set_fault", "tare", "dispense", "weigh", "set_fault"]);
  // the request that started this run (approved by bob) and the agent's drafted follow-up (filed by ada, still waiting)
  expect(report.follow_up_proposals.map((p: { state: string }) => p.state).sort()).toEqual(runner ? ["approved", "proposed"] : ["approved"]);
  const started = report.follow_up_proposals.find((p: { state: string }) => p.state === "approved");
  expect(started.proposed_by).not.toBe(started.decided_by); // two people
  const [popup] = await Promise.all([page.waitForEvent("popup"), failing.getByRole("button", { name: "Evidence report" }).click()]);
  await expect(popup.getByText("SIMULATED EVIDENCE: produced by a simulated instrument bench")).toBeVisible();
  await expect(popup.getByText("VIOLATED")).toBeVisible();
});

test("a viewer can follow the journey but cannot approve or ask the agent", async ({ page }) => {
  await signIn(page, vic);
  await page.goto(`/workflows?org=${org}`);
  // a viewer sees the agent-filed follow-up as waiting for an engineer (only a deployment with an agent has one)
  if (runner) await expect(page.getByText("awaiting an engineer").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Approve proposal for/ })).toHaveCount(0);
  await page.goto(`/agent?org=${org}`);
  await expect(page.getByText("Asking costs model spend, so it needs the engineer role.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeDisabled();
});
