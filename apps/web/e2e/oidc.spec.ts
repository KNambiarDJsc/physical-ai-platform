import { expect, test } from "@playwright/test";

/**
 * AUTH-002: browser sign-in through a real OpenID Connect provider (authorization code + PKCE), against the real
 * API validating the provider's RS256 JWT access tokens. Runs only when the stack is in OIDC mode:
 *   bash scripts/smoke.sh --oidc
 */
test.skip(!process.env.PAP_E2E_OIDC, "needs the stack in OIDC mode (bash scripts/smoke.sh --oidc)");

const run = Date.now().toString(36);
const user = `oidc-${run}`;
const issuer = process.env.PAP_E2E_OIDC_ISSUER ?? "";

test("sign in with the identity provider; tokens stay out of the page; sign out", async ({ page, context, baseURL }) => {
  // Before sign-in: the proxy refuses, and a header chosen by page script does not help.
  expect((await page.request.get("/api/v1/me")).status()).toBe(401);
  expect((await page.request.get("/api/v1/me", { headers: { Authorization: "Bearer dev:mallory" } })).status()).toBe(401);

  await page.goto("/");
  await expect(page.getByText("Not signed in.")).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();

  // The provider's own login and consent pages (any login/password are accepted by its development pages).
  await expect(page).toHaveURL(new RegExp(`^${issuer.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/`));
  await page.locator('input[name="login"]').fill(user);
  await page.locator('input[name="password"]').fill("any-password");
  await page.getByRole("button", { name: /sign-in/i }).click();
  await page.getByRole("button", { name: /continue/i }).click();

  // Back in the app, signed in.
  await page.waitForURL(`${baseURL}/`);
  await expect(page.getByRole("heading", { name: "Start with a workspace." })).toBeVisible();

  // The session cookie: HttpOnly, Secure, SameSite=Lax; the sign-in transaction cookie is gone.
  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === "pap_session");
  expect(session, "session cookie").toBeTruthy();
  expect(session?.httpOnly).toBe(true);
  expect(session?.secure).toBe(true);
  expect(session?.sameSite).toBe("Lax");
  expect(cookies.find((c) => c.name === "pap_oidc_tx" && c.value)).toBeUndefined();

  // Nothing the page's scripts can read holds a token.
  const visible = await page.evaluate(() => ({
    cookie: document.cookie,
    local: JSON.stringify({ ...localStorage }),
    session: JSON.stringify({ ...sessionStorage }),
  }));
  expect(visible.cookie).not.toContain("pap_session");
  for (const v of Object.values(visible)) expect(v).not.toMatch(/eyJ[\w-]+\.[\w-]+/); // no JWT anywhere
  const sessionInfo = await page.evaluate(async () => (await fetch("/auth/session")).text());
  expect(sessionInfo).not.toMatch(/eyJ[\w-]+\.[\w-]+/);

  // The API sees the provider's subject, and a page script cannot swap identities with its own header.
  const me = await page.evaluate(async () => (await fetch("/api/v1/me")).json());
  expect(me.subject).toBe(user);
  expect(me.issuer).toBe(issuer);
  const forged = await page.evaluate(async () => (await fetch("/api/v1/me", { headers: { Authorization: "Bearer dev:mallory" } })).json());
  expect(forged.subject).toBe(user);

  // The signed-in user can work: create an organization and a project through the UI.
  await page.getByRole("button", { name: "Create organization" }).click(); // the form opens on request
  await page.getByLabel("Organization name").fill("OIDC");
  await page.getByLabel("Organization slug").fill(`oidc-${run}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.getByRole("button", { name: "New project" }).first().click(); // the form opens on request
  await page.getByLabel("Project name").fill("Picking cell");
  await page.getByLabel("Project slug").fill("picking");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("link", { name: "Picking cell" })).toBeVisible();

  // Sign out clears the session.
  await page.goto("/settings");
  await expect(page.getByRole("main").getByText(`Test user ${user}`)).toBeVisible();
  await expect(page.getByRole("banner").getByText(`Test user ${user}`)).toBeVisible(); // the top bar names the user too
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  expect((await context.cookies()).find((c) => c.name === "pap_session" && c.value)).toBeUndefined();
  expect((await page.request.get("/api/v1/me")).status()).toBe(401);
});

test("a forged or tampered session cookie is refused", async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: "pap_session", value: "v1.AAAA.BBBB.CCCC", url: baseURL! }]);
  expect((await page.request.get("/api/v1/me")).status()).toBe(401);
  const s = await (await page.request.get("/auth/session")).json();
  expect(s).toEqual({ mode: "oidc", user: null });
});

test("the development sign-in is not offered when the server uses the identity provider", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Subject")).toHaveCount(0);
  await expect(page.getByText("Development identity")).toHaveCount(0);
});
