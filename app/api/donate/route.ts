import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// The tap posts a camera frame (~0.5 MB base64) and waits on a NIM vision call
// (~13 s typical, one retry on a transient 5xx). Budget generously so a slow
// call surfaces as a real result rather than a client-side timeout.
export const maxDuration = 120;

type IncomingBody = {
  description?: string;
  triggered_at?: string;
  location?: string;
  // Optional base64 JPEG captured on-device (iPad LAN pull of the mounted
  // Hikvision, or the iPad's own camera). When present, n8n uses this frame
  // instead of fetching from a bridge. Absent for the legacy PWA path.
  image_b64?: string;
  source?: string;
};

export async function POST(req: NextRequest) {
  const webhook = process.env.N8N_WEBHOOK_URL;
  const token = process.env.APERTURE_SHARED_TOKEN;

  if (!webhook) {
    return NextResponse.json(
      { error: "Server not configured: N8N_WEBHOOK_URL missing" },
      { status: 500 }
    );
  }

  let body: IncomingBody;
  try {
    body = (await req.json()) as IncomingBody;
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const payload = {
    description: (body.description ?? "").slice(0, 2000),
    triggered_at: body.triggered_at ?? new Date().toISOString(),
    location: body.location ?? null,
    image_b64: body.image_b64 ?? null,
    source: body.source ?? "aperture-pwa"
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 100_000);

  try {
    const resp = await fetch(webhook, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Aperture-Token": token } : {})
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    const text = await resp.text();
    if (!resp.ok) {
      return NextResponse.json(
        { error: `n8n ${resp.status}: ${text.slice(0, 500)}` },
        { status: 502 }
      );
    }

    try {
      const parsed = JSON.parse(text);
      return NextResponse.json(parsed);
    } catch {
      // An empty body here means the workflow ended without hitting a Respond node
      // (usually a node threw). Say so plainly instead of showing a bare blank.
      const detail = text.trim().length
        ? text.slice(0, 500)
        : "n8n closed the request without a response — a workflow node failed. Check the n8n execution log.";
      return NextResponse.json({ error: detail }, { status: 502 });
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "unknown";
    return NextResponse.json({ error: `fetch failed: ${msg}` }, { status: 504 });
  } finally {
    clearTimeout(timeout);
  }
}
