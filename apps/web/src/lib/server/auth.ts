/**
 * Browser sign-in (AUTH-002), server side only: imported by route handlers, never by client components.
 *
 * The web server is the OIDC client (authorization code + PKCE). Tokens never reach browser JavaScript or
 * browser storage: the access token lives in an AES-256-GCM sealed, HttpOnly, Secure, SameSite=Lax cookie, and the
 * /api/v1 proxy attaches it to API requests. The development identity exists only when PAP_ENV is not
 * "production"; in production the proxy ignores any Authorization header the browser sends.
 */
import { createCipheriv, createDecipheriv, hkdfSync, randomBytes } from "node:crypto";
import * as oidc from "openid-client";

export const SESSION_COOKIE = "pap_session";
export const TX_COOKIE = "pap_oidc_tx";
const MAX_SESSION_S = 8 * 3600;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

export class AuthConfigError extends Error {}

export type OidcSettings = {
  mode: "oidc";
  issuer: string;
  clientId: string;
  clientSecret?: string;
  scope: string;
  resource?: string;
  origin: string;
  secret: string;
};
export type AuthSettings = { mode: "dev" } | OidcSettings;

export function authSettings(env: Record<string, string | undefined> = process.env): AuthSettings {
  const production = env.PAP_ENV === "production";
  const mode = env.PAP_WEB_AUTH?.trim() || (production ? "oidc" : "dev"); // empty counts as unset (Compose)
  if (mode === "dev") {
    if (production) throw new AuthConfigError("the development identity is not available when PAP_ENV=production");
    return { mode: "dev" };
  }
  if (mode !== "oidc") throw new AuthConfigError(`PAP_WEB_AUTH must be "oidc" or "dev", not ${JSON.stringify(mode)}`);
  const need = (k: string) => {
    const v = env[k]?.trim();
    if (!v) throw new AuthConfigError(`${k} is required when PAP_WEB_AUTH=oidc`);
    return v;
  };
  const issuer = need("PAP_OIDC_ISSUER");
  const u = new URL(issuer);
  if (!(u.protocol === "https:" || (u.protocol === "http:" && LOOPBACK.has(u.hostname) && !production))) {
    throw new AuthConfigError("PAP_OIDC_ISSUER must use https (plain http only to this machine, outside production)");
  }
  const secret = need("PAP_SESSION_SECRET");
  if (secret.length < 32) throw new AuthConfigError("PAP_SESSION_SECRET must be at least 32 characters");
  const origin = new URL(need("PAP_WEB_ORIGIN")).origin;
  return {
    mode: "oidc",
    issuer,
    clientId: need("PAP_OIDC_CLIENT_ID"),
    clientSecret: env.PAP_OIDC_CLIENT_SECRET?.trim() || undefined,
    scope: env.PAP_OIDC_SCOPE?.trim() || "openid profile email",
    resource: env.PAP_OIDC_RESOURCE?.trim() || undefined,
    origin,
    secret,
  };
}

// --- sealed cookies -----------------------------------------------------------------------------------------------

function key(secret: string, purpose: string): Buffer {
  return Buffer.from(hkdfSync("sha256", secret, "pap-web-session", purpose, 32));
}

/** Encrypt and authenticate a JSON value. `purpose` separates session and transaction cookies cryptographically. */
export function seal(value: unknown, secret: string, purpose: string): string {
  const iv = randomBytes(12);
  const c = createCipheriv("aes-256-gcm", key(secret, purpose), iv);
  c.setAAD(Buffer.from(purpose));
  const body = Buffer.concat([c.update(JSON.stringify(value), "utf8"), c.final()]);
  return ["v1", iv.toString("base64url"), body.toString("base64url"), c.getAuthTag().toString("base64url")].join(".");
}

/** The sealed value, or null if it is missing, malformed, tampered with, or sealed for another purpose or key. */
export function unseal<T>(sealed: string | undefined, secret: string, purpose: string): T | null {
  if (!sealed) return null;
  const [v, iv, body, tag] = sealed.split(".");
  if (v !== "v1" || !iv || !body || !tag) return null;
  try {
    const d = createDecipheriv("aes-256-gcm", key(secret, purpose), Buffer.from(iv, "base64url"));
    d.setAAD(Buffer.from(purpose));
    d.setAuthTag(Buffer.from(tag, "base64url"));
    const text = Buffer.concat([d.update(Buffer.from(body, "base64url")), d.final()]).toString("utf8");
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export type Session = { sub: string; name: string; access_token: string; expires_at: number };
export type Transaction = { state: string; nonce: string; verifier: string; return_to: string; created: number };

export const nowS = () => Math.floor(Date.now() / 1000);

export function readSession(cookie: string | undefined, s: OidcSettings): Session | null {
  const v = unseal<Session>(cookie, s.secret, "session");
  return v && typeof v.access_token === "string" && v.expires_at > nowS() ? v : null;
}

export function sessionMaxAge(expiresIn: number | undefined): number {
  return Math.max(60, Math.min(expiresIn ?? 300, MAX_SESSION_S));
}

export const cookieOptions = (maxAge: number, path = "/") =>
  ({ httpOnly: true, secure: true, sameSite: "lax", path, maxAge }) as const;

/** Only same-site relative paths, so the return target cannot send the browser to another origin. */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}

// --- OIDC client --------------------------------------------------------------------------------------------------

let discovered: { issuer: string; config: Promise<oidc.Configuration> } | null = null;

export function oidcConfiguration(s: OidcSettings): Promise<oidc.Configuration> {
  if (discovered?.issuer !== s.issuer) {
    const insecure = new URL(s.issuer).protocol === "http:"; // already limited to loopback outside production
    const config = oidc.discovery(
      new URL(s.issuer),
      s.clientId,
      s.clientSecret,
      s.clientSecret ? undefined : oidc.None(),
      insecure ? { execute: [oidc.allowInsecureRequests] } : undefined,
    );
    config.catch(() => {
      discovered = null; // try again on the next request
    });
    discovered = { issuer: s.issuer, config };
  }
  return discovered.config;
}

export { oidc };
