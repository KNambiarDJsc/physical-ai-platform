import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse, type Page } from "@playwright/test";
import { seedModel } from "./support/twin-seed";

/**
 * SIM-005: the Experiment Studio, in a real browser against the real API, worker, engine and a real simulation host
 * (the self-test catalog: a kinematic base model that writes a real MCAP; not a simulator and not Gazebo).
 *
 * One journey across three people: ada configures and asks, bob (another engineer) reviews and approves, vic (a
 * viewer) can read but not decide. The verdicts are the engine's; the test asserts the relation between each trial's
 * measurement and its verdict rather than a hard-coded outcome.
 */
const run = Date.now().toString(36);
const org = `exp-${run}`;
const ADA = `ada-${run}`;
const BOB = `bob-${run}`;
const VIC = `vic-${run}`;
const LIMIT = 0.15; // the pass rule typed into the form below
let simOffered = false;
let requestUrl = "";

test.describe.configure({ mode: "serial" });

const ok = async (p: Promise<APIResponse>, status = 201) => {
  const r = await p;
  expect(r.status(), await r.text()).toBe(status);
  return r.json();
};

test.beforeAll(async ({ playwright, baseURL }) => {
  test.setTimeout(300_000);
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${ADA}` } });
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Experiments" } }));
  for (const [subject, role] of [[BOB, "engineer"], [VIC, "viewer"]] as const) {
    await ok(api.put(`/api/v1/orgs/${org}/members`, { data: { issuer: "dev", subject, role } }), 200);
  }
  const catalog = (await ok(api.get("/api/v1/environment-catalog"), 200)) as { key: string }[];
  simOffered = catalog.some((e) => e.key === "selftest-sim");
  if (!simOffered) return;
  await ok(api.post(`/api/v1/orgs/${org}/environments`, { data: { config_key: "selftest-sim" } }));
  await ok(api.post(`/api/v1/orgs/${org}/environments/selftest-sim/discover`), 200);
  await ok(api.post(`/api/v1/orgs/${org}/projects`, { data: { slug: "robots", name: "Robots" } }));
  await seedModel(api, `/api/v1/orgs/${org}/projects/robots`);
});

async function signAs(page: Page, subject: string, theme: "dark" | "light" = "dark") {
  const url = test.info().project.use.baseURL ?? "http://127.0.0.1:3000";
  await page.context().addCookies([{ name: "pap_theme", value: theme, url }]);
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(subject);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(`Signed in as`)).toBeVisible();
}

const rows = async (page: Page, table: string) => {
  const t = page.getByRole("table", { name: table });
  await expect(t).toBeVisible();
  return t.locator("tbody tr");
};

test.describe("the journey: configure, approve, run, inspect, investigate, review, compare", () => {
  test("an engineer configures an experiment from the host's own scenario, and bad values are refused in words first", async ({ page }) => {
    test.skip(!simOffered, "the stack was started without the self-test simulation host (--sim-port)");
    await signAs(page, ADA);
    await page.goto(`/experiments?org=${org}`);
    await expect(page.getByText("No experiments yet.")).toBeVisible();
    await page.getByRole("link", { name: "Set up the first experiment" }).click();

    // the scenario list is what the host listed, not something the page made up
    await expect(page.getByText("Self-test simulation host")).toBeVisible();
    await expect(page.getByText("Ready", { exact: true })).toBeVisible();
    await page.getByRole("radio", { name: /Self-test: base stop on command loss/ }).check();
    await expect(page.getByText("A small kinematic model that exercises the pipeline").or(page.getByText(/not a simulator/i)).first()).toBeVisible();

    // nothing is sent while the form is incomplete: every problem is said in words, next to its field
    await page.getByRole("button", { name: "Save experiment" }).click();
    await expect(page.getByText("Give the experiment a name.")).toBeVisible();
    await expect(page.getByText("Give its revision (a commit, tag or version).")).toBeVisible();
    await expect(page.getByText("Enter a number.").first()).toBeVisible();
    await page.getByLabel("Name", { exact: true }).fill("Stop on command loss");

    // a value outside the scenario's schema is refused before submission
    await page.getByLabel("Speed (m/s), Baseline").fill("9");
    await page.getByRole("button", { name: "Save experiment" }).click();
    await expect(page.getByText("At most 1.")).toBeVisible();
    await page.getByLabel("Speed (m/s), Baseline").fill("0.3");

    await page.getByLabel("Stop on command loss, Candidate").selectOption("Yes");
    await page.getByLabel("Repetitions per setup").fill("2");
    await page.getByLabel("Value for rule 1").fill(String(LIMIT));
    await page.getByLabel(/Show the recording in the Digital twin/).selectOption({ index: 1 });
    await page.getByLabel("Software under test").fill("controller");
    await page.getByLabel("Revision", { exact: true }).fill("505d17a");
    await expect(page.getByText(/Each run will be 4 trials/)).toBeVisible();
    await page.getByRole("button", { name: "Save experiment" }).click();

    await expect(page.getByText("Version 1 is saved.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Stop on command loss" })).toBeVisible();
    // only the parameter that differs is marked as differing
    const setup = page.getByRole("table", { name: "Setups and their parameters" });
    await expect(setup.getByRole("row", { name: /Stop on command loss.*differs/ })).toBeVisible();
    await expect(setup.getByRole("row", { name: /Speed \(m\/s\)/ }).getByText("differs")).toHaveCount(0);
  });

  test("the requester cannot approve their own run; another engineer reviews exactly that version and approves", async ({ page }) => {
    test.skip(!simOffered, "no self-test simulation host");
    await signAs(page, ADA);
    await page.goto(`/experiments?org=${org}&exp=stop-on-command-loss`);
    await page.getByLabel("Note for the approver (optional)").fill("first run");
    await page.getByRole("button", { name: "Ask to run version 1" }).click();
    await expect(page.getByRole("heading", { name: "Stop on command loss, version 1" })).toBeVisible();
    requestUrl = page.url().replace(/^https?:\/\/[^/]+/, "");
    await expect(page.getByText("Review before approving")).toBeVisible();
    await expect(page.getByText("You asked for this run, and this experiment needs someone else to approve it.")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Approve/ })).toHaveCount(0); // no control that cannot work

    await signAs(page, BOB);
    await page.goto(requestUrl);
    await expect(page.getByText("An approval applies to exactly this version")).toBeVisible();
    await expect(page.getByText(/queues\s*4 trials/)).toBeVisible();
    await page.getByRole("button", { name: "Approve and run 4 trials" }).click();
    await expect(page.getByRole("progressbar", { name: "Trials finished" })).toBeVisible();
    await expect(page.getByText("Every trial has finished.")).toBeVisible({ timeout: 150_000 });
  });

  test("results: each trial's verdict is the engine's over its measurement, side by side per setup, with downloadable files", async ({ page }) => {
    test.skip(!simOffered, "no self-test simulation host");
    await signAs(page, BOB);
    await page.goto(requestUrl);
    await expect(page.getByText("Every trial has finished.")).toBeVisible({ timeout: 30_000 });
    const side = await rows(page, "Setups side by side");
    await expect(side).toHaveCount(2);
    await expect(page.getByText(/not a statistical comparison/)).toBeVisible();
    // a contract violation is never presented as a release regression
    await expect(page.getByTestId("violation-vs-regression")).toContainText("It is not a release regression");
    await expect(page.getByTestId("violation-vs-regression")).toContainText("2 trials per setup, so no regression is claimed");

    const trials = await rows(page, "Every trial");
    await expect(trials).toHaveCount(4);
    let violated = 0;
    for (let i = 0; i < 4; i++) {
      const cells = await trials.nth(i).locator("td").allTextContents();
      const travel = Number(/^([\d.]+) m$/.exec(cells[5] ?? "")?.[1]);
      expect(Number.isFinite(travel), cells.join(" | ")).toBe(true);
      const verdict = (cells[4] ?? "").trim();
      expect(verdict).toBe(travel <= LIMIT ? "satisfied" : "violated"); // the relation, not a fixed outcome
      if (verdict === "violated") violated++;
    }
    expect(violated).toBeGreaterThan(0); // the baseline setup does not stop its base: this scenario is built to show it

    const [download] = await Promise.all([page.waitForEvent("download"), trials.first().getByRole("button", { name: "Download recording" }).click()]);
    expect(download.suggestedFilename()).toMatch(/\.mcap$/);
  });

  test("a failed trial opens in the Digital twin on the robot model, with the trial's verdict, and the assistant explains it from the run's evidence", async ({ page }) => {
    test.skip(!simOffered, "no self-test simulation host");
    await signAs(page, BOB);
    await page.goto(requestUrl);
    const trials = await rows(page, "Every trial");
    const bad = trials.filter({ hasText: "violated" }).first();
    await bad.getByRole("link", { name: "Investigate in Digital twin" }).click();
    await expect(page.getByTestId("scene-ready")).toHaveAttribute("data-meshes", "18", { timeout: 60_000 });
    await expect(page.getByTestId("mode")).toHaveAttribute("data-mode", "recorded");
    const link = page.getByTestId("trial-link");
    await expect(link).toContainText("Engine verdict");
    await expect(link).toContainText("violated");
    await expect(link).toContainText("SIMULATED EVIDENCE");

    await page.getByRole("button", { name: /^problem: Base still moving after the last command at [\d.]+ s$/ }).first().click();
    await page.getByRole("button", { name: "Explain this event" }).click();
    const ex = page.getByTestId("explanation");
    await expect(ex).toBeVisible({ timeout: 30_000 });
    await expect(ex).toContainText(/OpenMHS engine judged trial baseline/i);
    await expect(ex).toContainText("Stop on command loss v1");
    await expect(ex).toContainText("verification:");
    await expect(ex).toContainText("workflow-run:");
    await expect(ex).toContainText("Evidence class: simulated");

    await page.getByRole("link", { name: "Stop on command loss v1: all trials" }).click();
    await expect(page.getByRole("heading", { name: "Stop on command loss, version 1" })).toBeVisible();
  });

  test("a viewer reads everything and can ask for a run, but is never offered a decision or a form", async ({ page, playwright, baseURL }) => {
    test.skip(!simOffered, "no self-test simulation host");
    const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${VIC}` } });
    await ok(api.post(`/api/v1/orgs/${org}/experiments/stop-on-command-loss/versions/1/requests`, { data: { note: "from the viewer" } }));
    await signAs(page, VIC);
    await page.goto(`/experiments?org=${org}`);
    await expect(page.getByRole("link", { name: "New experiment" })).toHaveCount(0);
    await expect(page.getByText("Waiting for a decision (1)")).toBeVisible();
    await page.getByRole("link", { name: "Review Stop on command loss" }).click();
    await expect(page.getByText("Only an engineer can approve.")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Approve/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
    await page.goto(`/experiments?org=${org}&new=1`);
    await expect(page.getByText("Only engineers can configure experiments.")).toBeVisible();
  });
});

for (const theme of ["dark", "light"] as const) {
  test(`every Studio view passes WCAG A/AA (${theme} theme)`, async ({ page }) => {
    test.skip(!simOffered, "no self-test simulation host");
    test.setTimeout(180_000);
    await signAs(page, BOB, theme);
    const views: [string, string][] = [
      [`/experiments?org=${org}`, "All experiments"],
      [`/experiments?org=${org}&new=1`, "Setups to compare"],
      [`/experiments?org=${org}&exp=stop-on-command-loss`, "Runs"],
      [`/experiments?org=${org}&exp=stop-on-command-loss&edit=1`, "Save as a new version"],
      [requestUrl, "Setups side by side"],
    ];
    const failures: string[] = [];
    for (const [url, ready] of views) {
      await page.goto(url);
      await page.getByText(ready).first().waitFor({ timeout: 30_000 });
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      for (const v of result.violations) failures.push(`${url}: ${v.id} (${v.impact}): ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join("; ")}`);
    }
    // the waiting request (the viewer's) too: the review panel with its decision controls
    await page.goto(`/experiments?org=${org}`);
    await page.getByRole("link", { name: "Review Stop on command loss" }).click();
    await page.getByText("Review before approving").waitFor();
    const review = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    for (const v of review.violations) failures.push(`review: ${v.id} (${v.impact}): ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join("; ")}`);
    expect(failures, failures.join("\n")).toEqual([]);
  });
}
