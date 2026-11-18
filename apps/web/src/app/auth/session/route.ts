/** Who is signed in, for the UI. Never returns a token. */
import { NextResponse, type NextRequest } from "next/server";
import { AuthConfigError, authSettings, readSession, SESSION_COOKIE } from "@/lib/server/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  try {
    const s = authSettings();
    if (s.mode === "dev") return NextResponse.json({ mode: "dev", user: null });
    const session = readSession(req.cookies.get(SESSION_COOKIE)?.value, s);
    const user = session ? { subject: session.sub, name: session.name, expires_at: session.expires_at } : null;
    return NextResponse.json({ mode: "oidc", user }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    const message = e instanceof AuthConfigError ? e.message : "authentication is misconfigured";
    return NextResponse.json({ mode: "misconfigured", user: null, message }, { status: 500 });
  }
}
