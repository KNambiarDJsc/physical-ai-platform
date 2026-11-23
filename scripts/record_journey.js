// Record the Laboratory experiment journey from the real application (a real browser on a running stack).
//
//   uv run python scripts/journey_seed.py --org lab-journey-rec        # a clean workspace, nothing run yet
//   NODE_PATH=apps/web/node_modules node scripts/record_journey.js lab-journey-rec docs/demo/recording
//
// It clicks through the same steps as docs/demo/RUNBOOK.md at a readable pace: request, the refused self-approval, a
// second person's approval, a successful run, a failing run, the agent's investigation with the model the server has
// configured (drafting a follow-up, which the person files), and the evidence export. Nothing is faked: the page is the
// application, the numbers are the stack's. Playwright's own video capture writes the .webm.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const org = process.argv[2] || "lab-journey-rec";
const out = path.resolve(process.argv[3] || "docs/demo/recording");
const base = process.env.PAP_WEB_URL || "http://127.0.0.1:3000";
const OK_PROC = "dispense-50ul";
const FAULT_PROC = "dispense-50ul-blocked-line";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: out, size: { width: 1280, height: 720 } } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(180000);

  const signIn = async (who) => {
    await page.goto(`${base}/settings`);
    await page.getByLabel("Subject").fill(who);
    await page.getByRole("button", { name: "Sign in" }).click();
    await wait(1200);
  };
  const stepHeading = async (name) => {
    const h = page.getByRole("heading", { name });
    await h.scrollIntoViewIfNeeded();
    await wait(1500);
  };
  const request = async (proc, why) => {
    await page.goto(`${base}/journey?org=${org}`);
    await wait(2500);
    await page.getByLabel("Procedure").selectOption(proc);
    await page.getByLabel(/^Why run it/).pressSequentially(why, { delay: 28 });
    await wait(600);
    await page.getByRole("button", { name: "Request run" }).click();
    await page.getByText("awaiting approval").first().waitFor();
    await wait(1800);
  };
  const approveAs = async (who, proc) => {
    await signIn(who);
    await page.goto(`${base}/workflows?org=${org}`);
    await wait(2000);
    await page.getByRole("button", { name: `Approve proposal for ${proc}`, exact: true }).first().click();
    await wait(1500);
    const row = page.getByRole("row").filter({ hasText: new RegExp(`${proc}(?![-a-z0-9])`) });
    await row.getByRole("link", { name: "Open the run" }).click();
  };

  // 1 and 2: instruments and procedures
  await signIn("ada");
  await page.goto(`${base}/journey?org=${org}`);
  await wait(3500);
  await stepHeading("Configure the procedure and its tolerance");
  await wait(3500);

  // 3: ada requests; her own approval is refused
  await request(OK_PROC, "Baseline: confirm the healthy bench meets the tolerance.");
  await page.goto(`${base}/workflows?org=${org}`);
  await wait(2000);
  await page.getByRole("button", { name: `Approve proposal for ${OK_PROC}`, exact: true }).click();
  await page.getByText("must be approved by someone other than whoever proposed it").waitFor();
  await wait(3500);

  // a second person approves; the run is judged by the engine
  await approveAs("bob", OK_PROC);
  await page.getByText("Supported success").first().waitFor();
  await wait(5000);

  // a genuine failing run (a simulated partial blockage injected by a journaled step)
  await signIn("ada");
  await request(FAULT_PROC, "Reproduce a blocked line and see how the evidence shows it.");
  await approveAs("bob", FAULT_PROC);
  await page.getByText("Contradiction").first().waitFor();
  await wait(6000);

  // the agent (the configured language model), drafting a follow-up that a person files
  await signIn("ada");
  await page.goto(`${base}/journey?org=${org}`);
  await wait(2000);
  await stepHeading("Investigate the failure with the agent");
  await page.getByRole("link", { name: "Ask the agent (language model)" }).click();
  await wait(3500);
  // The model provider can be briefly unavailable (the session then says so and costs nothing): ask again, up to 3 times.
  for (let attempt = 1; ; attempt++) {
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const outcome = await Promise.race([
      page.getByRole("heading", { name: "Answer" }).waitFor().then(() => "answer"),
      page.getByText("The model provider could not answer").waitFor().then(() => "unavailable"),
    ]);
    if (outcome === "answer") break;
    if (attempt >= 3) throw new Error("the model provider stayed unavailable");
    await wait(4000);
    await page.getByLabel("Question").fill(`Investigate workflow run ${(await page.getByText(/Investigate workflow run [0-9a-f-]{36}/).first().textContent()).match(/[0-9a-f-]{36}/)[0]}. The pump reported a result; what did the independent measurement show, what is the evidence, and what follow-up experiment would you draft? Cite ids.`);
  }
  await wait(7000);
  await page.getByText(/^Trace \(\d+ steps\)$/).click();
  await wait(5000);
  const draft = page.getByRole("button", { name: "File as a proposal" });
  if (await draft.count()) {
    await draft.scrollIntoViewIfNeeded();
    await wait(2500);
    await draft.click();
    await page.getByText("It is waiting for someone other than whoever filed it.").waitFor();
    await wait(3500);
  }

  // the exported evidence
  await page.goto(`${base}/journey?org=${org}`);
  await wait(1500);
  await stepHeading("Export the evidence");
  await wait(5000);

  const video = page.video();
  await ctx.close();
  const file = await video.path();
  const dest = path.join(out, "laboratory-experiment-journey.webm");
  fs.copyFileSync(file, dest);
  fs.unlinkSync(file);
  await browser.close();
  console.log("recorded", dest, (fs.statSync(dest).size / 1e6).toFixed(1) + " MB");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
