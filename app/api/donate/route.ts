import { NextRequest, NextResponse } from "next/server";
import { createHash, randomUUID } from "node:crypto";
import { del, put } from "@vercel/blob";
import { deviceAuth } from "../../lib/deviceAuth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// The tap posts a camera frame (~0.5 MB base64) and waits on a NIM vision call
// (~13 s typical, one retry on a transient 5xx). Budget generously so a slow
// call surfaces as a real result rather than a client-side timeout.
export const maxDuration = 120;

// Fields checked below are typed unknown: the body is whatever the client sent.
type IncomingBody = {
  description?: unknown;
  triggered_at?: unknown;
  location?: string;
  // Optional base64 JPEG captured on-device (iPad LAN pull of the mounted
  // Hikvision, or the iPad's own camera). When present, n8n uses this frame
  // instead of fetching from a bridge. Absent for the legacy PWA path.
  image_b64?: string;
  source?: string;
  donation_id?: unknown;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type ArchiveResult = {
  url: string | null;
  sha256: string | null;
  bytes: number | null;
  error: string | null;
  duplicate?: true;   // a photo for this donation_id already exists
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
    const error = e instanceof Error ? e.message : "archive failed";
    // The SDK has no error class for this, only the API message. The path is keyed by
    // donation_id, so it means an earlier attempt of the same tap already got this far.
    if (/already exists/i.test(error)) return { ...empty, error, duplicate: true };
    return { ...empty, error };
  }
}

/**
 * Delete the archived photo when n8n produced no record, so the iPad's retry with the
 * same donation_id is not turned away as a duplicate. Best effort, like the archive.
 */
async function releasePhoto(archive: ArchiveResult) {
  if (!archive.url) return;
  try {
    await del(archive.url);
  } catch {
    /* the retry then gets a 409, which is the old behaviour */
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
  const denied = deviceAuth(req);
  if (denied) return denied;
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

  // Re-serialised from the parsed Date, so the blob day prefix is always a real
  // YYYY-MM-DD and never a slice of whatever string the client sent.
  const tappedAt = typeof body.triggered_at === "string" ? Date.parse(body.triggered_at) : NaN;
  const triggeredAt = new Date(Number.isNaN(tappedAt) ? Date.now() : tappedAt).toISOString();
  // One id shared by the archived photo, the n8n execution, and the Sheet row.
  // It is the join key that later lets a real weight be matched to this
  // prediction, which is the whole point of archiving. Only a UUID is kept: the id
  // lands in blob paths, the Sheet and the iPad's HTML.
  const donationId =
    typeof body.donation_id === "string" && UUID.test(body.donation_id) ? body.donation_id : randomUUID();
  const description = typeof body.description === "string" ? body.description.slice(0, 2000) : "";

  const archive = await archivePhoto(body.image_b64, donationId, triggeredAt);
  // A retry of a tap whose first attempt is still running (or already logged) must not
  // reach n8n again, or the same donation lands twice in the Sheet and Farmbrite.
  if (archive.duplicate) {
    return NextResponse.json({ error: "already logged or in progress" }, { status: 409 });
  }

  const payload = {
    description,
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
      await releasePhoto(archive);
      return NextResponse.json(
        { error: `n8n ${resp.status}: ${text.slice(0, 500)}` },
        { status: 502 }
      );
    }

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(text);
    } catch {
      // An empty body here means the workflow ended without hitting a Respond node
      // (usually a node threw). Say so plainly instead of showing a bare blank.
      const detail = text.trim().length
        ? text.slice(0, 500)
        : "n8n closed the request without a response — a workflow node failed. Check the n8n execution log.";
      await releasePhoto(archive);
      return NextResponse.json({ error: detail }, { status: 502 });
    }
    // n8n's Respond node answers 200 unless told otherwise, so a refused shared token
    // arrives here as {"error": ...}. That is not a donation: log nothing.
    if (parsed && typeof parsed.error === "string") {
      await releasePhoto(archive);
      return NextResponse.json({ error: `n8n: ${parsed.error.slice(0, 500)}` }, { status: 502 });
    }
    await writeRecord(
      {
        ...parsed,
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
  } catch (e) {
    // On our own timeout n8n may still finish and log the tap, so keep the photo and
    // let the retry get a 409. Any other fetch error means n8n never answered.
    if (!controller.signal.aborted) await releasePhoto(archive);
    const msg = e instanceof Error ? e.message : "unknown";
    return NextResponse.json({ error: `fetch failed: ${msg}` }, { status: 504 });
  } finally {
    clearTimeout(timeout);
  }
}
