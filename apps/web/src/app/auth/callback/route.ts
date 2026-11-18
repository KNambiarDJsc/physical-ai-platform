/** Finishes sign-in: checks state, nonce and PKCE through openid-client, then keeps the tokens server-side only. */
import { NextResponse, type NextRequest } from "next/server";
import {
  authSettings,
  cookieOptions,
  nowS,
  oidc,
  oidcConfiguration,
  seal,
  sessionMaxAge,
  SESSION_COOKIE,
  TX_COOKIE,
  unseal,
  type Session,
  type Transaction,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const s = authSettings();
  if (s.mode !== "oidc") return NextResponse.json({ detail: { code: "auth.not_oidc" } }, { status: 404 });
  const fail = (code: string) => {
    const res = NextResponse.redirect(`${s.origin}/settings?auth_error=${encodeURIComponent(code)}`);
    res.cookies.set(TX_COOKIE, "", cookieOptions(0, "/auth"));
    return res;
  };
  const tx = unseal<Transaction>(req.cookies.get(TX_COOKIE)?.value, s.secret, "tx");
  if (!tx || nowS() - tx.created > 600) return fail("sign_in_expired");
  let session: Session;
  let expiresIn: number | undefined;
  try {
    const config = await oidcConfiguration(s);
    // The URL the provider redirected to, rebuilt on the configured public origin (not the Host header).
    const current = new URL(`${req.nextUrl.pathname}${req.nextUrl.search}`, s.origin);
    const tokens = await oidc.authorizationCodeGrant(
      config,
      current,
      { pkceCodeVerifier: tx.verifier, expectedState: tx.state, expectedNonce: tx.nonce, idTokenExpected: true },
      s.resource ? { resource: s.resource } : undefined,
    );
    const claims = tokens.claims();
    if (!claims?.sub) return fail("no_subject");
    expiresIn = tokens.expiresIn();
    const name = [claims.name, claims.preferred_username, claims.email].find((v): v is string => typeof v === "string") ?? claims.sub;
    session = { sub: claims.sub, name, access_token: tokens.access_token, expires_at: nowS() + sessionMaxAge(expiresIn) };
  } catch (e) {
    const code = e instanceof oidc.AuthorizationResponseError ? `idp_${e.error}` : "sign_in_failed";
    console.error(`sign-in failed: ${code}: ${e instanceof Error ? e.message : String(e)}`);
    return fail(code);
  }
  const res = NextResponse.redirect(`${s.origin}${tx.return_to}`);
  res.cookies.set(SESSION_COOKIE, seal(session, s.secret, "session"), cookieOptions(sessionMaxAge(expiresIn)));
  res.cookies.set(TX_COOKIE, "", cookieOptions(0, "/auth"));
  res.headers.set("Cache-Control", "no-store");
  return res;
}
