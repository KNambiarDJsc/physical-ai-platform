import { expect, test, type APIResponse, type Page } from "@playwright/test";

/**
 * AGT-002: the Agent page, end to end on the real stack. The question is a fixed one ("list experiments"), which the
 * real harness answers by a tool call and a template, so the whole path (page, API, subprocess, harness, platform
 * tools as the caller, trace) runs without a model and without cost. What a model adds is verified by a real run, never
 * by this test.
 */
const run = Date.now().toString(36);
const org = `agent-${run}`;
const eng = `eng-${run}`;
const view = `view-${run}`;
let runner = true; // whether this deployment can run the agent (the Compose image cannot: no uv, no harness)

test.beforeAll(async ({ playwright, baseURL }) => {
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${eng}` } });
  const ok = async (p: Promise<APIResponse>) => {
    const r = await p;
    expect(r.status(), await r.text()).toBeLessThan(300);
  };
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Agent" } }));
  await ok(api.put(`/api/v1/orgs/${org}/members`, { data: { issuer: "dev", subject: view, role: "viewer" } }));
  runner = (await (await api.get(`/api/v1/orgs/${org}/agent/status`)).json()).runner_available;
});

async function signIn(page: Page, subject: string) {
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(subject);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("a viewer can read the Agent page but cannot ask", async ({ page }) => {
  await signIn(page, view);
  await page.goto(`/agent?org=${org}`);
  await expect(page.getByRole("heading", { name: "Agent", level: 1 })).toBeVisible();
  await expect(page.getByText("Asking costs model spend, so it needs the engineer role.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeDisabled();
  await expect(page.getByText("No session yet.")).toBeVisible();
  await expect(page.getByText("Read-only: the agent cannot request, approve or run anything from this page.")).toBeVisible();
});

test("an engineer asks a fixed question and gets an answer, its cost and its trace", async ({ page }) => {
  test.skip(!runner, "this deployment has no agent runner; the next test covers that state");
  test.setTimeout(180_000); // the first start of the harness environment can be slow
  await signIn(page, eng);
  await page.goto(`/agent?org=${org}`);
  await expect(page.getByRole("heading", { name: "Agent", level: 1 })).toBeVisible();
  await expect(page.getByText("No session yet.")).toBeVisible();
  await page.getByLabel("Question").fill("list experiments");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({ timeout: 150_000 });
  await expect(page.getByText("Answered by a fixed tool call and a template: no model.")).toBeVisible();
  await expect(page.getByText("no model used")).toBeVisible();
  await page.getByText(/^Trace \(\d+ steps\)$/).click();
  await expect(page.getByText(/1\. list_experiments/)).toBeVisible();
  await expect(page.getByRole("button", { name: /list experiments/ }).first()).toBeVisible(); // in the session list
});

test("where the agent cannot run, the page says so and nothing can be asked", async ({ page }) => {
  test.skip(runner, "this deployment has an agent runner; the tests above cover asking");
  await signIn(page, eng);
  await page.goto(`/agent?org=${org}`);
  await expect(page.getByRole("heading", { name: "Agent", level: 1 })).toBeVisible();
  await expect(page.getByText("The agent is not available on this server")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeDisabled();
  await expect(page.getByText("No session yet.")).toBeVisible();
});
