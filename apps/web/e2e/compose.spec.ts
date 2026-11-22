import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse } from "@playwright/test";

/**
 * Multi-instrument composition: an engineer composes, in the interface, a workflow across two instruments of the real
 * virtual laboratory (balance and syringe pump) with a verification contract, and the worker runs it with the pinned
 * engine judging. The test asserts the relation between the balance's reading and the engine's verdict.
 */
const run = Date.now().toString(36);
const org = `compose-${run}`;
const user = `comp-${run}`;
const LO = 0.0783;
const HI = 0.0815; // 80 µL of water at 20 °C is 0.0799 g; ± 2 %
let labOffered = false;

const ok = async (p: Promise<APIResponse>, status = 201) => {
  const r = await p;
  expect(r.status(), await r.text()).toBe(status);
  return r.json();
};

test.beforeAll(async ({ playwright, baseURL }) => {
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  const catalog = (await ok(api.get("/api/v1/environment-catalog"), 200)) as { key: string }[];
  labOffered = catalog.some((c) => c.key === "virtual-lab");
  if (!labOffered) return;
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Compose" } }));
  await ok(api.post(`/api/v1/orgs/${org}/environments`, { data: { config_key: "virtual-lab" } }));
  await ok(api.post(`/api/v1/orgs/${org}/environments/virtual-lab/discover`), 200);
});

test("an engineer composes a two-instrument workflow with its contract, and the engine judges the run", async ({ page, playwright, baseURL }) => {
  test.skip(!labOffered, "the stack was started without the virtual laboratory");
  test.setTimeout(180_000);
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.goto(`/workflows?org=${org}`);
  const panel = page.locator("section", { has: page.getByRole("heading", { name: "Compose a workflow from instruments" }) });
  await expect(panel).toBeVisible();

  // nothing is saved while incomplete
  await panel.getByRole("button", { name: "Save workflow" }).click();
  await expect(panel.getByText("Give the workflow a name.")).toBeVisible();
  await expect(panel.getByText("Choose an instrument.")).toBeVisible();

  await panel.getByLabel("Name").fill("Two dispenses then weigh");
  const steps: [string, string, string?][] = [["balance", "tare"], ["pump", "dispense", "50"], ["pump", "dispense", "30"], ["balance", "weigh"]];
  for (let i = 0; i < steps.length; i++) {
    if (i > 0) await panel.getByRole("button", { name: "Add a step" }).click();
    const [dev, action, volume] = steps[i]!;
    const li = panel.getByRole("list", { name: "Steps" }).getByRole("listitem").nth(i);
    await li.getByLabel("Instrument").selectOption(dev);
    await li.getByLabel("Action").selectOption(action);
    if (volume) await li.getByLabel("Volume ul").fill(volume);
  }
  await panel.getByLabel("Whose report is the claim?").selectOption({ index: 2 }); // the second dispense
  await panel.getByRole("button", { name: "Add evidence" }).click();
  await panel.getByLabel("Measured by").selectOption({ index: 3 }); // the weighing
  // the lab's balance returns dict[str, float]: it declares no field names, so the engineer names the field
  await expect(panel.getByText("This action does not declare the names of what it returns.")).toBeVisible();
  await panel.getByLabel("Value").fill("mass_g");
  await panel.getByLabel("Signal").fill("vessel.net_mass");
  await panel.getByLabel("Unit").fill("g");
  await panel.getByRole("button", { name: "Add a condition" }).click();
  await panel.getByLabel("Lower bound for condition 1").fill(String(LO));
  await panel.getByLabel("Upper bound for condition 1").fill(String(HI));
  await expect(panel.getByText(`Passes when mass g is between ${LO} g and ${HI} g.`)).toBeVisible();
  expect((await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations.map((v) => v.id)).toEqual([]);
  await panel.getByRole("button", { name: "Save workflow" }).click();
  await expect(panel.getByRole("status")).toContainText("Saved two-dispenses-then-weigh");

  // the worker runs it on the simulated instruments; the engine judges
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  let r = await ok(api.post(`/api/v1/orgs/${org}/workflows/two-dispenses-then-weigh/runs`));
  for (let i = 0; i < 240 && ["queued", "running"].includes(r.state); i++) {
    await page.waitForTimeout(500);
    r = await ok(api.get(`/api/v1/orgs/${org}/workflow-runs/${r.id}`), 200);
  }
  expect(r.state).toBe("succeeded");
  expect(r.steps.map((s: { device: string; action: string }) => `${s.device}.${s.action}`)).toEqual(["balance.tare", "pump.dispense", "pump.dispense", "balance.weigh"]);
  const mass = r.steps[3].output.mass_g as number;
  expect(r.verification.verdict).toBe(mass >= LO && mass <= HI ? "SATISFIED" : "VIOLATED"); // the relation, not a fixed outcome
});

test("an admin adds a colleague, changes their role and removes them, from Settings", async ({ page }) => {
  test.skip(!labOffered, "the stack was started without the virtual laboratory");
  const colleague = `colleague-${run}`;
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.goto(`/settings?org=${org}`);
  const members = page.getByRole("table", { name: `Members of ${org}` });
  await expect(members.getByText("(you)")).toBeVisible();
  await page.getByLabel("Their sign-in subject").fill(colleague);
  await page.getByLabel("Role for the new member").selectOption("engineer");
  await page.getByRole("button", { name: "Add member" }).click();
  const row = members.getByRole("row", { name: new RegExp(colleague) });
  await expect(row.getByLabel(`Role of ${colleague}`)).toHaveValue("engineer");
  await row.getByLabel(`Role of ${colleague}`).selectOption("viewer");
  await expect(row.getByLabel(`Role of ${colleague}`)).toHaveValue("viewer");
  expect((await new AxeBuilder({ page }).include("main").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations.map((v) => v.id)).toEqual([]);
  await row.getByRole("button", { name: `Remove ${colleague}` }).click();
  await expect(members.getByRole("row", { name: new RegExp(colleague) })).toHaveCount(0);
});
