// @vitest-environment node
import { describe, expect, it } from "vitest";
import { AuthConfigError, authSettings, readSession, safeReturnTo, seal, unseal, type OidcSettings } from "./auth";

const SECRET = "x".repeat(32);
const OIDC = {
  PAP_WEB_AUTH: "oidc",
  PAP_OIDC_ISSUER: "https://idp.example/realms/pap",
  PAP_OIDC_CLIENT_ID: "pap-web",
  PAP_WEB_ORIGIN: "https://pap.example/some/path",
  PAP_SESSION_SECRET: SECRET,
};

describe("sealed cookies", () => {
  it("round-trips and hides the content", () => {
    const sealed = seal({ access_token: "secret-token" }, SECRET, "session");
    expect(sealed).not.toContain("secret-token");
    expect(unseal(sealed, SECRET, "session")).toEqual({ access_token: "secret-token" });
  });
  it("refuses tampering, another key and another purpose", () => {
    const sealed = seal({ a: 1 }, SECRET, "session");
    const [v, iv, body = "", tag] = sealed.split(".");
    const flipped = Buffer.from(body, "base64url");
    flipped.writeUInt8(flipped.readUInt8(0) ^ 1, 0);
    expect(unseal([v, iv, flipped.toString("base64url"), tag].join("."), SECRET, "session")).toBeNull();
    expect(unseal(sealed, "y".repeat(32), "session")).toBeNull();
    expect(unseal(sealed, SECRET, "tx")).toBeNull(); // a transaction cookie cannot be replayed as a session
    expect(unseal("garbage", SECRET, "session")).toBeNull();
    expect(unseal(undefined, SECRET, "session")).toBeNull();
  });
  it("treats an expired session as no session", () => {
    const s = authSettings(OIDC) as OidcSettings;
    const now = Math.floor(Date.now() / 1000);
    const live = seal({ sub: "a", name: "A", access_token: "t", expires_at: now + 60 }, SECRET, "session");
    const dead = seal({ sub: "a", name: "A", access_token: "t", expires_at: now - 1 }, SECRET, "session");
    expect(readSession(live, s)?.sub).toBe("a");
    expect(readSession(dead, s)).toBeNull();
  });
});

describe("auth settings", () => {
  it("defaults to the development identity outside production, and refuses it in production", () => {
    expect(authSettings({})).toEqual({ mode: "dev" });
    expect(() => authSettings({ PAP_ENV: "production", PAP_WEB_AUTH: "dev" })).toThrow(AuthConfigError);
    // production without explicit settings means OIDC, and OIDC needs its settings
    expect(() => authSettings({ PAP_ENV: "production" })).toThrow(/PAP_OIDC_ISSUER/);
  });
  it("reads OIDC settings", () => {
    const s = authSettings(OIDC) as OidcSettings;
    expect(s.mode).toBe("oidc");
    expect(s.origin).toBe("https://pap.example");
    expect(s.scope).toBe("openid profile email");
    expect(s.clientSecret).toBeUndefined();
  });
  it("refuses weak or unsafe settings", () => {
    expect(() => authSettings({ ...OIDC, PAP_SESSION_SECRET: "short" })).toThrow(/32/);
    expect(() => authSettings({ ...OIDC, PAP_OIDC_ISSUER: "http://idp.example" })).toThrow(/https/);
    expect(() => authSettings({ ...OIDC, PAP_OIDC_ISSUER: "http://localhost.evil.example" })).toThrow(/https/);
    expect(() => authSettings({ ...OIDC, PAP_ENV: "production", PAP_OIDC_ISSUER: "http://127.0.0.1:9000" })).toThrow(/https/);
    expect(authSettings({ ...OIDC, PAP_OIDC_ISSUER: "http://127.0.0.1:9000" }).mode).toBe("oidc");
    expect(() => authSettings({ ...OIDC, PAP_WEB_AUTH: "basic" })).toThrow(AuthConfigError);
  });
});

describe("return path", () => {
  it("keeps the user on this site", () => {
    expect(safeReturnTo("/o/acme/p/picking")).toBe("/o/acme/p/picking");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example","", null, undefined, "javascript:alert(1)"]) {
      expect(safeReturnTo(bad)).toBe("/");
    }
  });
});
