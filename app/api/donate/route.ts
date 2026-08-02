import { NextRequest, NextResponse } from "next/server";
import { createHash, randomUUID } from "node:crypto";
import { put } from "@vercel/blob";

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
  donation_id?: string;
};

type ArchiveResult = {
  url: string | null;
  sha256: string | null;
  bytes: number | null;
  error: string | null;
};

/**
 * Archive the captured frame to Vercel Blob (private) so every prediction keeps
 * the exact image it was made from. Without this the photo is discarded after
 * the vision call and the donation can never become training data.
 *
 * Deliberately NON-BLOCKING: a storage outage must never stop a volunteer from
 * logging a donation, so every failure is captured and reported alongside the
 * result instead of thrown.
 */
async function archivePhoto(
  imageB64: string | undefined,
  donationId: string,
  triggeredAt: string
): Promise<ArchiveResult> {
  const empty: ArchiveResult = { url: null, sha256: null, bytes: null, error: null };
  if (!imageB64) return empty;
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return { ...empty, error: "BLOB_READ_WRITE_TOKEN not configured" };
  }

  try {
    const bytes = Buffer.from(imageB64.replace(/^data:image\/[a-zA-Z]+;base64,/, ""), "base64");
    if (bytes.length < 1000) return { ...empty, error: "image too small to archive" };

    const sha256 = createHash("sha256").update(bytes).digest("hex");
    const day = triggeredAt.slice(0, 10);           // YYYY-MM-DD — keeps the store browsable
    const blob = await put(`donations/${day}/${donationId}.jpg`, bytes, {
      access: "private",                            // must match the store's access mode
      contentType: "image/jpeg",
      addRandomSuffix: false,
    });
    return { url: blob.url, sha256, bytes: bytes.length, error: null };
  } catch (e) {
    return { ...empty, error: e instanceof Error ? e.message : "archive failed" };
  }
}

/**
 * Persist one donation record (tap + the parsed result n8n returned) as its own
 * small blob, so /api/export can assemble a running CSV. One file per donation —
 * never an append to a shared file — so concurrent taps cannot clobber each other.
 *
 * Non-blocking, like the photo archive: the volunteer's result must not depend on
 * bookkeeping succeeding.
 */
async function writeRecord(record: Record<string, unknown>, donationId: string, triggeredAt: string) {
  try {
    if (!process.env.BLOB_READ_WRITE_TOKEN) return;
    const day = triggeredAt.slice(0, 10);
    await put(`records/${day}/${donationId}.json`, JSON.stringify(record), {
      access: "private",
      contentType: "application/json",
      addRandomSuffix: false,
    });
  } catch {
    /* bookkeeping must never break a tap */
  }
}

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

  const triggeredAt = body.triggered_at ?? new Date().toISOString();
  // One id shared by the archived photo, the n8n execution, and the Sheet row.
  // It is the join key that later lets a real weight be matched to this
  // prediction, which is the whole point of archiving.
  const donationId = body.donation_id ?? randomUUID();

  const archive = await archivePhoto(body.image_b64, donationId, triggeredAt);

  const payload = {
    description: (body.description ?? "").slice(0, 2000),
    triggered_at: triggeredAt,
    location: body.location ?? null,
    image_b64: body.image_b64 ?? null,
    donation_id: donationId,
    image_url: archive.url,
    image_sha256: archive.sha256,
    image_bytes: archive.bytes,
    archive_error: archive.error,
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
      await writeRecord(
        {
          ...(parsed as Record<string, unknown>),
          donation_id: donationId,
          triggered_at: triggeredAt,
          location: payload.location,
          description: payload.description,
          image_url: archive.url,
          image_sha256: archive.sha256,
          image_bytes: archive.bytes,
          source: payload.source,
          logged_at: new Date().toISOString(),
        },
        donationId,
        triggeredAt
      );
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
