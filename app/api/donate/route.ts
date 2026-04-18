import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

type IncomingBody = {
  description?: string;
  triggered_at?: string;
  location?: string;
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
    source: "aperture-pwa"
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45_000);

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
      return NextResponse.json(
        { error: "n8n returned non-JSON", raw: text.slice(0, 500) },
        { status: 502 }
      );
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "unknown";
    return NextResponse.json({ error: `fetch failed: ${msg}` }, { status: 504 });
  } finally {
    clearTimeout(timeout);
  }
}
