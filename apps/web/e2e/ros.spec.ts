import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse, type Page } from "@playwright/test";

/**
 * ROS-002: the OpenAMRobot workspace on the existing Hardware Hub and Workbench. Runs once for every ROS environment the
 * installation's operator offers: `openamr-recorded` (a snapshot recorded from a real graph and replayed: CI, no ROS)
 * and `openamr-sim` (a LIVE graph through the observer: scripts/ros_stack.sh start, local only). Only the interface is
 * driven; the setup (workspace, environment, discovery) uses the API as a stand-in for the Get started page.
 */
const run = Date.now().toString(36);
const KEYS = ["openamr-recorded", "openamr-sim"];
let offered: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ playwright, baseURL }) => {
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:ros-${run}` } });
  const ok = async (p: Promise<APIResponse>, status = 200) => {
    const r = await p;
    expect(r.status(), await r.text()).toBe(status);
    return r.json();
  };
  const catalog = (await ok(api.get("/api/v1/environment-catalog"))) as { key: string }[];
  offered = KEYS.filter((k) => catalog.some((c) => c.key === k));
  for (const key of offered) {
    const org = `ros-${key}-${run}`.slice(0, 60);
    await ok(api.post("/api/v1/orgs", { data: { slug: org, name: key } }), 201);
    await ok(api.post(`/api/v1/orgs/${org}/environments`, { data: { config_key: key } }), 201);
    await ok(api.post(`/api/v1/orgs/${org}/environments/${key}/discover`));
  }
});

async function signIn(page: Page) {
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(`ros-${run}`);
  await page.getByRole("button", { name: "Sign in" }).click();
}

const orgOf = (key: string) => `ros-${key}-${run}`.slice(0, 60);

async function openDevice(page: Page, key: string, device: string) {
  await page.goto(`/hardware?org=${orgOf(key)}`);
  await page.getByRole("navigation", { name: "Devices" }).getByRole("button", { name: device }).click();
  await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
}

for (const key of KEYS) {
  test.describe(key, () => {
    test.beforeEach(() => {
      test.skip(!offered.includes(key), `${key} is not offered by this installation`);
    });

    test("the Hardware Hub lists the observer's devices with properties only and no actions", async ({ page }) => {
      await signIn(page);
      await page.goto(`/hardware?org=${orgOf(key)}`);
      await expect(page.getByRole("row").filter({ hasText: key })).toContainText("SIMULATED");
      const nav = page.getByRole("navigation", { name: "Devices" });
      await expect(nav.getByRole("button", { name: "ros-graph" })).toBeVisible();
      await expect(nav.getByRole("button", { name: "ros-robot" })).toBeVisible();
      await nav.getByRole("button", { name: "ros-graph" }).click();
      await expect(page.getByRole("heading", { name: "Properties (6)" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Actions (0)" })).toBeVisible(); // there is no command surface
    });

    test("topics are shown with their freshness state, rate and age; silence is not hidden", async ({ page }) => {
      await signIn(page);
      await openDevice(page, key, "ros-graph");
      await page.getByRole("button", { name: "Read topics" }).click();
      const view = page.getByRole("region", { name: "Value of topics" });
      const table = view.getByRole("table", { name: "topics" });
      await expect(table).toBeVisible();
      const js = table.getByRole("row", { name: /^\/joint_states / });
      await expect(js).toContainText("fresh");
      await expect(js).toContainText(/\d+\.\d Hz/);
      await expect(table.getByRole("row", { name: /^\/tf_static / })).toContainText("latched");
      // Topics with a publisher that never delivered, or none at all, are listed as such, not dropped.
      await expect(table.getByRole("cell", { name: "never", exact: true }).first()).toBeVisible();
      await expect(table.getByRole("cell", { name: "no publishers", exact: true }).first()).toBeVisible();
    });

    test("expected topics: present ones fresh, absent ones 'missing', never invented", async ({ page }) => {
      await signIn(page);
      await openDevice(page, key, "ros-graph");
      await page.getByRole("button", { name: "Read expected_topics" }).click();
      const table = page.getByRole("region", { name: "Value of expected_topics" }).getByRole("table", { name: "expected_topics" });
      await expect(table.getByRole("row", { name: /^\/joint_states / })).toContainText("fresh");
      await expect(table.getByRole("row", { name: /^\/clock / })).toContainText("missing");
      await page.getByRole("button", { name: "Read clock" }).click();
      const clock = page.getByRole("region", { name: "Value of clock" });
      await expect(clock).toContainText("absent");
    });

    test("joint states and controllers come from the robot, with the controller manager's own states", async ({ page }) => {
      await signIn(page);
      await openDevice(page, key, "ros-robot");
      await page.getByRole("button", { name: "Read joint_states" }).click();
      const joints = page.getByRole("region", { name: "Value of joint_states" });
      await expect(joints.getByRole("cell", { name: "lift_joint", exact: true })).toBeVisible();
      await expect(joints.getByRole("row")).toHaveCount(1 + 1 + 1 + 17); // sources header + the source row + joints header + 17 joints
      await page.getByRole("button", { name: "Read controllers" }).click();
      const ctrl = page.getByRole("region", { name: "Value of controllers" });
      for (const c of ["joint_state_broadcaster", "left_arm_controller", "lift_controller"]) {
        await expect(ctrl.getByRole("cell", { name: c, exact: true })).toBeVisible();
      }
      await expect(ctrl.getByText("active", { exact: true })).toHaveCount(6);
    });

    test("auto-refresh re-reads the property every second", async ({ page }) => {
      await signIn(page);
      await openDevice(page, key, "ros-graph");
      await page.getByRole("button", { name: "Read summary" }).click();
      const view = page.getByRole("region", { name: "Value of summary" });
      const first = await view.locator("time").first().getAttribute("datetime");
      await view.getByLabel("Auto-refresh every second").check();
      await expect.poll(async () => view.locator("time").first().getAttribute("datetime"), { timeout: 8000 }).not.toBe(first);
    });

    test("the Workbench shows the observed robot's health without any workflow", async ({ page }) => {
      await signIn(page);
      await page.goto(`/workbench?org=${orgOf(key)}`);
      await expect(page.getByRole("heading", { name: "Observed robots" })).toBeVisible();
      await expect(page.getByText(/\d+ nodes · \d+ topics · clock absent/)).toBeVisible();
      await expect(page.getByText("Every required topic is publishing.")).toBeVisible();
      await expect(page.getByText("No workflow in this workspace yet.")).toBeVisible();
    });

    for (const theme of ["dark", "light"] as const) {
      test(`the observation viewer passes axe (${theme})`, async ({ page, baseURL }) => {
        await page.context().addCookies([{ name: "pap_theme", value: theme, url: baseURL ?? "http://127.0.0.1:3000" }]);
        await signIn(page);
        await openDevice(page, key, "ros-graph");
        for (const prop of ["topics", "expected_topics", "nodes", "connectivity"]) {
          await page.getByRole("button", { name: `Read ${prop}` }).click();
          await expect(page.getByRole("region", { name: `Value of ${prop}` })).toBeVisible();
        }
        const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
        expect(r.violations.map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
        await openDevice(page, key, "ros-robot");
        for (const prop of ["joint_states", "transforms", "controllers", "diagnostics"]) {
          await page.getByRole("button", { name: `Read ${prop}` }).click();
          await expect(page.getByRole("region", { name: `Value of ${prop}` })).toBeVisible();
        }
        const r2 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
        expect(r2.violations.map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
        await page.goto(`/workbench?org=${orgOf(key)}`);
        await expect(page.getByRole("heading", { name: "Observed robots" })).toBeVisible();
        const r3 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
        expect(r3.violations.map((v) => v.id)).toEqual([]);
      });
    }
  });
}
