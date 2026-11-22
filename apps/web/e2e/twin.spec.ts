import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { EXP, seedModel, seedRecording } from "./support/twin-seed";

/**
 * TWN-003/004/005: the digital twin in the Workbench, in a real browser against the real API, worker and engine.
 *
 * The milestone is the first test group: watch an actual recorded OpenAMRobot experiment (a real Gazebo run of the
 * pre-fix wiring) through an interactive 3D robot, select the failure on the timeline, and have the engineering

 * assistant explain the evidence behind it. The robot model is upstream's own URDF and meshes; the recordings are two
 * real MCAP bags; the verdicts are the engine's.
 */
const run = Date.now().toString(36);
const org = `twin-${run}`;
const user = `twin-${run}`;
const P = `/api/v1/orgs/${org}/projects/cmd`;
const MAIN = "main_20261122T053012Z";
const FIX = "fix_20261121T185851Z";
const LABEL = { main: "openamr-platform-sw-69847ab-main", fix: "openamr-platform-sw-505d17a-fix79" };
let replayOffered = false;
let liveOffered = false;

test.describe.configure({ mode: "serial" });

const ok = async (p: Promise<APIResponse>, status = 201) => {
  const r = await p;
  expect(r.status(), await r.text()).toBe(status);
  return r.json();
};

test.beforeAll(async ({ playwright, baseURL }) => {
  test.setTimeout(300_000);
  const api = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer dev:${user}` } });
  await ok(api.post("/api/v1/orgs", { data: { slug: org, name: "Digital twin" } }));
  await ok(api.post(`/api/v1/orgs/${org}/projects`, { data: { slug: "cmd", name: "Command timeout" } }));
  // The evaluation of the command-timeout runs through the real worker and engine.
  const rel: Record<string, string> = {};
  const art: Record<string, string> = {};
  for (const arm of ["main", "fix"] as const) {
    const components =
      arm === "main"
        ? [{ kind: "software", name: "openamr-platform-sw", version: "69847ab" }, { kind: "config", name: "gz_simulator wiring", version: "origin/main" }]
        : [{ kind: "software", name: "openamr-platform-sw", version: "505d17a" }, { kind: "config", name: "sim_cmd_vel_timeout", version: "0.2 s simulation time, non-latching" }];
    rel[arm] = (await ok(api.post(`${P}/releases`, { data: { label: LABEL[arm], kind: "software", components } }))).id;
    art[arm] = (await ok(api.post(`${P}/artifacts`, { multipart: { file: { name: `${arm}.csv`, mimeType: "text/csv", buffer: readFileSync(path.join(EXP, "data", `${arm}.csv`)) } } }))).id;
  }
  const mapping = (await ok(api.post(`${P}/mappings`, { data: JSON.parse(readFileSync(path.join(EXP, "mapping.json"), "utf-8")) }))).id;
  let job = await ok(
    api.post(`${P}/evaluations`, {
      data: {
        baseline_release_id: rel.main, candidate_release_id: rel.fix, mapping_id: mapping,
        baseline_artifact_ids: [art.main], candidate_artifact_ids: [art.fix],
        config: { task_type: "command_loss_stop", paired: false, min_known: 30, stratify_by_site: false },
      },
    }),
  );
  for (let i = 0; i < 240 && ["queued", "running"].includes(job.state); i++) {
    await new Promise((r) => setTimeout(r, 500));
    job = await (await api.get(`${P}/evaluations/${job.id}`)).json();
  }
  expect(job.state).toBe("succeeded");
  const eps = (await ok(api.get(`${P}/evaluations/${job.id}/episodes?limit=50`), 200)).items as { id: string; episode_key: string }[];
  const epId = (k: string) => eps.find((e) => e.episode_key === k)!.id;
  await seedModel(api, P);
  await seedRecording(api, P, FIX, { model_slug: "openamrobot-platform", model_version: "1", episode_id: epId(FIX) });
  await seedRecording(api, P, MAIN, { model_slug: "openamrobot-platform", model_version: "1", episode_id: epId(MAIN) });
  // Observed robots, when the installation offers them (the replay always does in CI; the live graph only locally).
  const catalog = (await ok(api.get("/api/v1/environment-catalog"), 200)) as { key: string }[];
  replayOffered = catalog.some((c) => c.key === "openamr-recorded");
  liveOffered = catalog.some((c) => c.key === "openamr-sim");
  for (const key of ["openamr-recorded", "openamr-sim"].filter((k) => catalog.some((c) => c.key === k))) {
    await ok(api.post(`/api/v1/orgs/${org}/environments`, { data: { config_key: key } }));
    await ok(api.post(`/api/v1/orgs/${org}/environments/${key}/discover`), 200);
  }
});

async function signIn(page: Page, theme: "dark" | "light" = "dark") {
  const url = test.info().project.use.baseURL ?? "http://127.0.0.1:3000";
  await page.context().addCookies([{ name: "pap_theme", value: theme, url }]);
  await page.goto("/settings");
  await page.getByLabel("Subject").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function openTwin(page: Page, recording: string) {
  await signIn(page);
  await page.goto(`/twin?org=${org}&project=cmd`);
  await page.getByRole("button", { name: new RegExp(`^${recording}`) }).click();
  await expect(page.getByTestId("scene-ready")).toHaveAttribute("data-meshes", "18", { timeout: 60_000 });
}

const robotXy = async (page: Page) => {
  const v = await page.locator("canvas[data-robot-xy]").getAttribute("data-robot-xy");
  const [x, y] = (v ?? "0,0").split(",").map(Number);
  return { x: x ?? 0, y: y ?? 0 };
};

test.describe("the milestone: a real recorded failure, in 3D, explained", () => {
  test("the recording opens on the upstream robot model, labelled as a recording, with the engine's verdict beside it", async ({ page }) => {
    await openTwin(page, MAIN);
    await expect(page.getByTestId("mode")).toHaveAttribute("data-mode", "recorded");
    await expect(page.getByTestId("mode-reason")).toContainText("Playing a recording");
    await expect(page.getByText(/openamrobot-platform|OpenAMRobot platform base/).first()).toBeVisible();
    await expect(page.getByText(/CERN-OHL-P-2\.0/)).toBeVisible();
    await expect(page.getByText("modified tree")).toBeVisible(); // the run identity says the tree was not the commit
    await expect(page.getByText("Engine verdict")).toBeVisible();
    await expect(page.getByRole("link", { name: `Episode ${MAIN}` })).toBeVisible();
    await expect(page.locator("canvas")).toBeVisible();
  });

  test("playing and scrubbing move the 3D model, the readout and the telemetry together", async ({ page }) => {
    await openTwin(page, MAIN);
    const start = await robotXy(page);
    expect(Math.abs(start.x)).toBeLessThan(0.05);
    await expect(page.getByTestId("pose")).toContainText("x 0.");
    const slider = page.getByRole("slider", { name: "Playback position" });
    await slider.focus();
    await page.keyboard.press("End");
    await expect.poll(async () => (await robotXy(page)).x, { timeout: 15_000 }).toBeGreaterThan(1.3); // it drove on
    const poseText = (await page.getByTestId("pose").textContent()) ?? "";
    expect(Number(/x (-?[\d.]+) m/.exec(poseText)?.[1])).toBeCloseTo((await robotXy(page)).x, 2); // the text and the scene agree
    await page.keyboard.press("Home");
    await expect.poll(async () => (await robotXy(page)).x, { timeout: 15_000 }).toBeLessThan(0.05);
    // Play advances time and the model by itself, and pausing stops it.
    await page.getByRole("button", { name: "Play" }).click();
    await expect.poll(async () => (await robotXy(page)).x, { timeout: 20_000 }).toBeGreaterThan(0.1);
    await page.getByRole("button", { name: "Pause" }).click();
    const paused = await robotXy(page);
    await page.waitForTimeout(500);
    expect((await robotXy(page)).x).toBe(paused.x);
  });

  test("selecting the failure on the timeline seeks to it, and the assistant explains the evidence behind it", async ({ page }) => {
    await openTwin(page, MAIN);
    const failure = page.getByRole("button", { name: /^problem: Base still moving after the last command at [\d.]+ s$/ }).first();
    await failure.click();
    await expect(failure).toHaveAttribute("aria-pressed", "true");
    const t = /at ([\d.]+) s$/.exec((await failure.getAttribute("aria-label")) ?? "")?.[1];
    await expect(page.getByTestId("readout")).toContainText(`${t} s on the simulation clock`);
    expect((await robotXy(page)).x).toBeGreaterThan(0.5); // the model is where the base was at that moment
    await expect(page.getByText("Select an event on the timeline to ask about it.")).toHaveCount(0);
    await page.getByRole("button", { name: "Explain this event" }).click();
    const ex = page.getByTestId("explanation");
    await expect(ex).toBeVisible({ timeout: 30_000 });
    // what the recording shows, with its rule
    await expect(ex).toContainText("Base still moving after the last command");
    await expect(ex).toContainText("Rule:");
    // the run identity as reported, including the pre-fix wiring files
    await expect(ex).toContainText("a modified tree");
    await expect(ex).toContainText("gz_bridge.yaml");
    // the engine's verdict, contract and observation, kept apart from the recording's own measurement
    await expect(ex).toContainText("violated");
    await expect(ex).toContainText("stops-after-command-loss");
    await expect(ex).toContainText("1.003 m");
    await expect(ex).toContainText("different measurements");
    // the data-quality problem in this recording and what is not known
    await expect(ex).toContainText("moved backwards");
    await expect(ex).toContainText("Not known");
    await expect(ex).toContainText("why it happened");
    // the evidence it cites, as ids
    await expect(ex.getByText(/^verification:/).first()).toBeVisible();
    await expect(ex.getByText(/^contract:[0-9a-f]{12}$/).first()).toBeVisible();
    await expect(ex.getByText(new RegExp(`^event:.+/ev-\\d+$`)).first()).toBeVisible();
    if (process.env.PAP_E2E_SHOTS) await page.screenshot({ path: path.join(process.env.PAP_E2E_SHOTS, "twin-failure-explained.png") }); // evidence for reviewers, off by default
    // the tool call is shown: a read-only tool, as the signed-in user
    await page.getByText("Tool call").click();
    await expect(page.getByText("explain_recording_event")).toBeVisible();
    await expect(page.getByText(/read-only: true/)).toBeVisible();
    // from the event to the Release Intelligence page of the same episode, and back
    await page.getByRole("link", { name: `Episode ${MAIN}` }).click();
    await expect(page).toHaveURL(/\/episodes\?episode=/);
    await expect(page.getByRole("heading", { name: `Episode ${MAIN}` })).toBeVisible();
    await page.getByRole("link", { name: "Open in Workbench" }).click();
    await expect(page).toHaveURL(/\/twin\?/);
    await expect(page.getByTestId("scene-ready")).toBeVisible({ timeout: 60_000 });
  });

  test("the fixed arm's recording stops promptly and the assistant says so without raising a problem", async ({ page }) => {
    await openTwin(page, FIX);
    await expect(page.getByRole("button", { name: /^problem:/ })).toHaveCount(0);
    await page.getByRole("button", { name: /^info: Base stopped after the last command at/ }).click();
    await page.getByRole("button", { name: "Explain this event" }).click();
    const ex = page.getByTestId("explanation");
    await expect(ex).toContainText("Base stopped after the last command", { timeout: 30_000 });
    await expect(ex).toContainText("satisfied");
    await expect(ex).toContainText("a clean checkout");
  });
});

test.describe("baseline versus candidate", () => {
  test("the fix recording is drawn as a ghost beside the pre-fix one, aligned at command loss, with both verdicts", async ({ page }) => {
    await openTwin(page, MAIN);
    await page.getByLabel("Compare with (drawn as a ghost)").selectOption({ label: FIX });
    const strip = page.getByTestId("comparison");
    await expect(strip).toContainText(`Solid: ${MAIN}`);
    await expect(strip).toContainText(`Ghost: ${FIX}`);
    await expect(strip).toContainText("aligned at the last command");
    const canvas = page.locator("canvas");
    await expect(canvas).toHaveAttribute("data-ghost-xy", /.+/, { timeout: 60_000 }); // the second robot is drawn
    const slider = page.getByRole("slider", { name: "Playback position" });
    await slider.focus();
    await page.keyboard.press("End");
    const gapText = async () => Number(/bases ([\d.]+) m apart/.exec((await page.getByTestId("base-gap").textContent()) ?? "")?.[1] ?? "NaN");
    await expect.poll(gapText, { timeout: 15_000 }).toBeGreaterThan(0.5); // pre-fix drove on, the fix stopped
    const xy = async (attr: string) => Number(((await canvas.getAttribute(attr)) ?? "0,0").split(",")[0]);
    expect(Math.abs((await xy("data-robot-xy")) - (await xy("data-ghost-xy")))).toBeGreaterThan(0.5); // the scene agrees
    await page.getByLabel("Align the two recordings at").selectOption({ label: "their starts" });
    await expect(strip).toContainText("aligned at their starts");
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    expect(axe.violations.map((v) => v.id)).toEqual([]);
    await page.getByRole("button", { name: "Stop comparing" }).click();
    await expect(strip).toHaveCount(0);
  });
});

test.describe("inspection", () => {
  test("a link shows its joint, the controller that drives it, and that the recording holds its wheel angle constant", async ({ page }) => {
    await openTwin(page, FIX);
    await page.getByRole("button", { name: "left_wheel_link", exact: true }).click();
    const d = page.getByTestId("link-detail");
    await expect(d).toContainText("left_wheel_joint (continuous)");
    await expect(d).toContainText("0 1 0");
    await expect(d).toContainText("gz::sim::systems::DiffDrive");
    await expect(d).toContainText("0.0000 rad (constant in this recording)");
    await page.getByRole("tab", { name: "Sensors" }).click();
    await expect(page.getByRole("row", { name: /lidar_sensor gpu_lidar/ })).toBeVisible();
    await page.getByRole("tab", { name: "Controllers" }).click();
    await expect(page.getByText("gz-sim-diff-drive-system")).toBeVisible();
    await page.getByRole("tab", { name: "Joints" }).click();
    await expect(page.getByRole("row", { name: /left_wheel_joint continuous/ })).toBeVisible();
    // the data-quality events are on the timeline, not hidden
    await expect(page.getByRole("button", { name: /^warning: left_wheel_joint reports a constant position/ })).toBeVisible();
  });

  test("clicking the robot in the 3D view selects the link under the pointer", async ({ page }) => {
    await openTwin(page, FIX);
    await page.getByRole("slider", { name: "Playback position" }).focus();
    await page.keyboard.press("Home");
    await page.getByRole("button", { name: "Reset view" }).click();
    const box = (await page.locator("canvas").boundingBox())!;
    let hit = false;
    // The model is small in a frame sized for its path: look for it on a coarse grid rather than at one fixed point.
    for (let fy = 0.35; fy <= 0.7 && !hit; fy += 0.05)
      for (let fx = 0.2; fx <= 0.8 && !hit; fx += 0.05) {
        await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
        hit = (await page.getByTestId("link-detail").count()) > 0;
      }
    expect(hit).toBe(true);
    await expect(page.getByTestId("link-detail")).toContainText("Parent joint");
  });
});

test.describe("modes", () => {
  test("an observed replay is Recorded, not Simulated or Live, whatever kind of environment it sits in", async ({ page }) => {
    test.skip(!replayOffered, "openamr-recorded is not offered by this installation");
    await signIn(page);
    await page.goto(`/twin?org=${org}&project=cmd`);
    await page.getByRole("button", { name: /^openamr-recorded/ }).click();
    await expect(page.getByTestId("mode")).toHaveAttribute("data-mode", "recorded");
    await expect(page.getByTestId("mode-reason")).toContainText("recorded snapshot replayed by the observer");
    await expect(page.getByText(/0 of 17 reported joints exist in this model/)).toBeVisible(); // the upper-body robot is not this model
    await expect(page.getByText(/An observed graph is not a recording/)).toBeVisible();
  });

  test("an observer that stops answering is Disconnected and the model does not move", async ({ page }) => {
    test.skip(!replayOffered, "openamr-recorded is not offered by this installation");
    await signIn(page);
    await page.goto(`/twin?org=${org}&project=cmd`);
    await page.getByRole("button", { name: /^openamr-recorded/ }).click();
    await expect(page.getByTestId("mode")).toHaveAttribute("data-mode", "recorded");
    await page.route("**/properties/**", (r) => r.abort());
    await expect(page.getByTestId("mode")).toHaveAttribute("data-mode", "disconnected", { timeout: 15_000 });
    await expect(page.getByText(/Disconnected: nothing is being received/)).toBeVisible();
    await expect(page.getByTestId("pose")).toContainText("no pose");
  });

  test("a live graph through the observer is Simulated (local only: scripts/ros_stack.sh start)", async ({ page }) => {
    test.skip(!liveOffered, "openamr-sim is not offered by this installation");
    await signIn(page);
    await page.goto(`/twin?org=${org}&project=cmd`);
    await page.getByRole("button", { name: /^openamr-sim/ }).click();
    await expect(page.getByTestId("mode")).toHaveAttribute("data-mode", "simulated", { timeout: 20_000 });
  });
});

for (const theme of ["dark", "light"] as const) {
  test(`no WCAG A/AA violations with a recording and the assistant's explanation open (${theme} theme)`, async ({ page }) => {
    await signIn(page, theme);
    await page.goto(`/twin?org=${org}&project=cmd`);
    await page.getByRole("button", { name: new RegExp(`^${MAIN}`) }).click();
    await expect(page.getByTestId("scene-ready")).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /^problem: Base still moving/ }).first().click();
    await page.getByRole("button", { name: "Explain this event" }).click();
    await expect(page.getByTestId("explanation")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "left_wheel_link", exact: true }).click();
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    const failures = result.violations.map((v) => `[${v.impact}] ${v.id}: ${v.help}\n    ${v.nodes.slice(0, 4).map((n) => n.target.join(" ")).join("\n    ")}`);
    expect(failures, failures.join("\n")).toEqual([]);
  });
}
