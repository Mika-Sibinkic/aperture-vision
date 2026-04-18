// Manual ground-truth correction endpoint.
//
// Called when the client contact/Joshua hits "Edit weight" on the iPad after a donation
// logs incorrectly. Forwards to a dedicated n8n webhook that updates the
// Google Sheet row and appends to the learning loop's ground-truth log.
//
// Request:  POST /api/correct  { donation_id, true_weight_lbs, note? }
// Response: { ok: true, sheet_row_updated: true } | { error, status }

import { NextRequest, NextResponse } from "next/server";

const N8N_CORRECTION_URL = process.env.N8N_CORRECTION_URL;       // different path from /donate
const APERTURE_SHARED_TOKEN = process.env.APERTURE_SHARED_TOKEN;

export async function POST(req: NextRequest) {
  if (!N8N_CORRECTION_URL || !APERTURE_SHARED_TOKEN) {
    return NextResponse.json(
      { error: "server not configured. N8N_CORRECTION_URL or APERTURE_SHARED_TOKEN missing." },
      { status: 500 },
    );
  }

  let payload: { donation_id?: string; true_weight_lbs?: number; note?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be JSON" }, { status: 400 });
  }

  if (!payload.donation_id || typeof payload.true_weight_lbs !== "number") {
    return NextResponse.json(
      { error: "donation_id + true_weight_lbs (number) required" },
      { status: 400 },
    );
  }
  if (payload.true_weight_lbs < 0 || payload.true_weight_lbs > 2000) {
    return NextResponse.json(
      { error: "true_weight_lbs out of plausible range (0-2000 lbs)" },
      { status: 400 },
    );
  }

  const ac = new AbortController();
  const to = setTimeout(() => ac.abort(), 30_000);
  try {
    const r = await fetch(N8N_CORRECTION_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-aperture-token": APERTURE_SHARED_TOKEN,
      },
      body: JSON.stringify({
        donation_id: payload.donation_id,
        true_weight_lbs: payload.true_weight_lbs,
        ground_truth_source: "manual",
        note: payload.note ?? null,
        corrected_at: new Date().toISOString(),
      }),
      signal: ac.signal,
    });
    clearTimeout(to);
    const body = await r.text();
    return new NextResponse(body, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
    });
  } catch (e: unknown) {
    clearTimeout(to);
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: "upstream timeout or network failure", detail: msg }, { status: 504 });
  }
}
