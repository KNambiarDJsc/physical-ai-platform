/** Starts sign-in: authorization code + PKCE (S256), state and nonce kept in a sealed, short-lived cookie. */
import { NextResponse, type NextRequest } from "next/server";
import { authSettings, cookieOptions, nowS, oidc, oidcConfiguration, safeReturnTo, seal, TX_COOKIE, type Transaction } from "@/lib/server/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const s = authSettings();
  if (s.mode !== "oidc") return NextResponse.json({ detail: { code: "auth.not_oidc", message: "sign-in is not configured" } }, { status: 404 });
  let config: oidc.Configuration;
  try {
    config = await oidcConfiguration(s);
  } catch {
    return NextResponse.json({ detail: { code: "auth.idp_unreachable", message: "the identity provider is not reachable" } }, { status: 502 });
  }
  const verifier = oidc.randomPKCECodeVerifier();
  const tx: Transaction = {
    state: oidc.randomState(),
    nonce: oidc.randomNonce(),
    verifier,
    return_to: safeReturnTo(req.nextUrl.searchParams.get("return_to")),
    created: nowS(),
  };
  const params: Record<string, string> = {
    redirect_uri: `${s.origin}/auth/callback`,
    scope: s.scope,
    code_challenge: await oidc.calculatePKCECodeChallenge(verifier),
    code_challenge_method: "S256",
    state: tx.state,
    nonce: tx.nonce,
  };
  if (s.resource) params.resource = s.resource;
  const res = NextResponse.redirect(oidc.buildAuthorizationUrl(config, params));
  res.cookies.set(TX_COOKIE, seal(tx, s.secret, "tx"), cookieOptions(600, "/auth"));
  res.headers.set("Cache-Control", "no-store");
  return res;
}
