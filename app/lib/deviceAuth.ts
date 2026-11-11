import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";

// Returns a 401 response unless the caller sends the device token, or null to let it through.
export function deviceAuth(req: Request): NextResponse | null {
  const want = process.env.APERTURE_DEVICE_TOKEN;
  if (!want) {
    // shortcut: open when unset so the live iPad keeps working until Mika's rollout; make fail-closed after rollout
    console.warn("APERTURE_DEVICE_TOKEN is unset: relay routes accept any caller");
    return null;
  }
  const got = Buffer.from(req.headers.get("x-aperture-token") ?? "");
  const exp = Buffer.from(want);
  if (got.length === exp.length && timingSafeEqual(got, exp)) return null;
  return NextResponse.json({ error: "unauthorized" }, { status: 401 });
}
