/** Signs out: clears the session cookie. POST only, so a link or an image cannot sign anyone out. */
import { NextResponse } from "next/server";
import { authSettings, cookieOptions, SESSION_COOKIE } from "@/lib/server/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST() {
  const s = authSettings();
  const res = NextResponse.redirect(s.mode === "oidc" ? `${s.origin}/settings` : "/settings", 303);
  res.cookies.set(SESSION_COOKIE, "", cookieOptions(0));
  return res;
}
