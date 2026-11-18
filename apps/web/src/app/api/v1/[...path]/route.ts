/**
 * Same-origin proxy to the API. The browser only ever talks to the web origin; this forwards /api/v1/* to
 * PAP_API_URL, read on every request, so one web build works against any API address (a next.config rewrite
 * would fix the address at build time). Bodies are streamed in both directions; nothing is inspected or stored.
 *
 * With browser sign-in (PAP_WEB_AUTH=oidc) the caller's Authorization header is discarded and the access token from
 * the sealed session cookie is attached instead, so a script in the page can neither read the token nor choose
 * another identity. Browser cookies are never forwarded to the API.
 */
import type { NextRequest } from "next/server";
import { AuthConfigError, authSettings, readSession, SESSION_COOKIE } from "@/lib/server/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOP = new Set(["connection", "keep-alive", "transfer-encoding", "upgrade", "proxy-connection", "te", "trailer", "host", "cookie"]);
// The API's own response headers worth passing on; content-length/encoding are recomputed by the runtime.
const DROP_RESPONSE = new Set([...HOP, "content-length", "content-encoding"]);

function apiBase(): string {
  return (process.env.PAP_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params;
  const target = `${apiBase()}/api/v1/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!HOP.has(k.toLowerCase())) headers.set(k, v);
  });
  let auth;
  try {
    auth = authSettings();
  } catch (e) {
    const message = e instanceof AuthConfigError ? e.message : "authentication is misconfigured";
    return Response.json({ detail: { code: "auth.misconfigured", message } }, { status: 500 });
  }
  if (auth.mode === "oidc") {
    headers.delete("authorization");
    const session = readSession(req.cookies.get(SESSION_COOKIE)?.value, auth);
    if (!session) return Response.json({ detail: { code: "auth.required", message: "sign in to continue" } }, { status: 401 });
    headers.set("authorization", `Bearer ${session.access_token}`);
  }
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let res: Response;
  try {
    res = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      redirect: "manual",
      cache: "no-store",
      // Node's fetch needs this to stream a request body.
      ...(hasBody ? ({ duplex: "half" } as Record<string, unknown>) : {}),
    });
  } catch {
    return Response.json({ detail: { code: "api.unreachable", message: "the API is not reachable" } }, { status: 502 });
  }
  const out = new Headers();
  res.headers.forEach((v, k) => {
    if (!DROP_RESPONSE.has(k.toLowerCase())) out.set(k, v);
  });
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
