import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * The Release Intelligence flow in a real browser against the real API, worker and pinned OpenMHS engine
 * (scripts/dev_stack.py). Every step goes through the web app.
 */
const DEMO = path.resolve(__dirname, "../../../examples/manipulation-demo");
const run = Date.now().toString(36);
const org = `e2e-${run}`;
const user = `alice-${run}`;

test("register releases, upload evidence, evaluate, compare, export, drill down", async ({ page }) => {
  // Everything through the web app, from signing in to creating the organization and project.
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Projects" }).click();
  await expect(page.getByText("You are not a member of any organization yet.")).toBeVisible();
  await page.getByLabel("Organization name").fill("E2E");
  await page.getByLabel("Organization slug").fill(org);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.getByLabel("Project name").fill("Picking cell");
  await page.getByLabel("Project slug").fill("picking");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByRole("link", { name: "Picking cell" }).click();
  await expect(page.getByRole("heading", { name: `${org} / picking` })).toBeVisible();

  for (const label of ["2.14.0", "2.15.0-rc1"]) {
    await page.getByLabel("Release label").fill(label);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByRole("listitem").filter({ hasText: label })).toBeVisible();
  }
  for (const file of ["baseline.csv", "candidate.csv"]) {
    await page.getByLabel("Evidence file").setInputFiles(path.join(DEMO, "data", file));
    await page.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByRole("listitem").filter({ hasText: file })).toBeVisible();
  }
  await page.getByLabel("Mapping (pap.mapping/1 JSON)").fill(readFileSync(path.join(DEMO, "mapping.json"), "utf-8"));
  await page.getByRole("button", { name: "Add version" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "warehouse-pick-csv" })).toBeVisible();

  await page.getByLabel("Baseline release").selectOption({ label: "2.14.0" });
  await page.getByLabel("Candidate release").selectOption({ label: "2.15.0-rc1" });
  await page.getByLabel("Mapping", { exact: true }).selectOption({ label: "warehouse-pick-csv v1" });
  await page.getByLabel("Baseline evidence").selectOption({ index: (await optionIndex(page, "Baseline evidence", "baseline.csv")) });
  await page.getByLabel("Candidate evidence").selectOption({ index: (await optionIndex(page, "Candidate evidence", "candidate.csv")) });
  await page.getByLabel("Task type").fill("pick_place");
  await page.getByLabel("Also pair by scenario").check();
  await page.getByRole("button", { name: "Start evaluation" }).click();

  // The worker runs the pinned engine; the page polls until the comparison is there.
  const reported = page.getByRole("heading", { name: "Reported by the robot" }).locator("..");
  const verified = page.getByRole("heading", { name: "Independently verified" }).locator("..");
  await expect(reported.getByText("Improvement")).toBeVisible({ timeout: 120_000 });
  await expect(verified.getByText("Insufficient evidence")).toBeVisible();
  await expect(page.getByText("SYNTHETIC EVIDENCE")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Paired by scenario/ })).toBeVisible();
  await expect(page.getByText(/commit e9ef873b42/)).toBeVisible();
  await page.screenshot({ path: "test-results/comparison.png", fullPage: true });
  await page.getByText("Investigate with Engineering Agent", { exact: true }).click();
  const question = page.getByLabel("Question", { exact: true });
  await expect(question).toHaveValue(/Investigate release evaluation .+ in project/);
  await question.fill("list experiments");
  const started = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/agent/sessions"));
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await started).postDataJSON().focus).toBe("release");
  await expect(page.getByText("Answered by a fixed tool call and a template: no model.")).toBeVisible({ timeout: 60000 });
  await page.getByText("Investigate with Engineering Agent", { exact: true }).click();


  // Export: the HTML report is rendered from the JSON report, and says what kind of evidence it rests on.
  const [html] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download HTML report" }).click()]);
  expect(html.suggestedFilename()).toMatch(/^evaluation-.+\.html$/);
  const htmlText = readFileSync(await html.path(), "utf-8");
  expect(htmlText).toContain("SYNTHETIC EVIDENCE");
  expect(htmlText).not.toContain("<script");
  const [json] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download JSON report" }).click()]);
  const report = JSON.parse(readFileSync(await json.path(), "utf-8"));
  expect(report.schema).toBe("pap.report/1");
  expect(report.evidence_class).toEqual(["synthetic"]);
  expect(htmlText).toContain(report.provenance.input_sha256);

  await page.getByRole("link", { name: "Contradiction" }).click();
  await expect(page.getByText(/of 32$/)).toBeVisible();
  await page.locator("tbody button").first().click();
  await expect(page.getByRole("heading", { name: "Conditions" })).toBeVisible();
  await expect(page.getByText("The robot's report and the independent evidence disagree.")).toBeVisible();
  await page.screenshot({ path: "test-results/episode.png", fullPage: true });
});

async function optionIndex(page: import("@playwright/test").Page, label: string, text: string): Promise<number> {
  const options = await page.getByLabel(label).locator("option").allTextContents();
  const i = options.findIndex((o) => o.startsWith(text));
  expect(i).toBeGreaterThanOrEqual(0);
  return i;
}
