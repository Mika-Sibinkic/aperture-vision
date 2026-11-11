// Void a logged donation — the "undo" behind the iPad's history list.
//
// A dock is a place where people mis-tap: the wrong item typed, a photo taken
// before the load was fully staged, a duplicate. Without an undo the only fix is
// asking someone to hand-edit a spreadsheet and a Farmbrite order later, which
// nobody does. So voiding has to be one tap, from the same screen.
//
//   POST /api/void  { donation_id, reason? }
//
// Voiding is reversible bookkeeping, not deletion:
//   * the Farmbrite draft order is deleted first, because that one is real inventory
//   * then the record is REWRITTEN with voided:true (photo + original values kept, so
//     the training corpus and any audit question survive). If the delete failed, the
//     record keeps farmbrite_void_error instead and the next void retries.
//   * /api/export drops voided rows from the running CSV
//
// The Google Sheet row is left in place — n8n owns that credential, not this route.
// The CSV is the authoritative export, and it excludes voided rows.

import { NextRequest, NextResponse } from "next/server";
import { list, put } from "@vercel/blob";
import { deviceAuth } from "../../lib/deviceAuth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const FARMBRITE = "https://api.farmbrite.com/v1";

function farmbriteHeaders() {
  const token = process.env.FARMBRITE_API_KEY;
  if (!token) throw new Error("FARMBRITE_API_KEY not configured");
  return { Authorization: `Bearer ${token}`, Accept: "application/json" };
}

/**
 * Find the draft order Aperture created for a donation.
 *
 * The record normally carries farmbrite_order_id; this is the fallback for older
 * records and for a tap whose order POST failed. The order note ends with "ref <first 8 chars of donation_id>". Plain
 * GET /orders excludes drafts, so list with status=Draft. Page ordering does not
 * reliably put newest last, so scan every page (bounded). Throws when Farmbrite
 * cannot be read, so "not found" always means "no order exists".
 */
async function findFarmbriteOrderId(donationId: string): Promise<string | null> {
  const ref = donationId.slice(0, 8);
  const headers = farmbriteHeaders();
  const fetchPage = async (page: number) => {
    const r = await fetch(`${FARMBRITE}/orders?status=Draft&limit=100&page=${page}`, { headers });
    if (!r.ok) throw new Error(`Farmbrite order lookup returned HTTP ${r.status}`);
    return (await r.json()) as { data?: { note?: string; id?: string }[]; total_pages?: number };
  };
  const findIn = (data: { data?: { note?: string; id?: string }[] }) =>
    (data.data || []).find((o) => o.note?.match(/ref (\S+)$/)?.[1] === ref)?.id ?? null;

  const first = await fetchPage(1);
  const lastPage = Math.min(Number(first.total_pages || 1), 20);   // bound the scan
  let hit = findIn(first);
  for (let page = lastPage; !hit && page >= 2; page--) hit = findIn(await fetchPage(page));
  return hit;
}

async function deleteFarmbriteOrder(orderId: string): Promise<void> {
  const r = await fetch(`${FARMBRITE}/orders/${orderId}`, { method: "DELETE", headers: farmbriteHeaders() });
  // 404: already gone, e.g. an earlier void deleted it but could not save the record.
  if (!r.ok && r.status !== 404) throw new Error(`Farmbrite returned HTTP ${r.status}`);
}

export async function POST(req: NextRequest) {
  const denied = deviceAuth(req);
  if (denied) return denied;
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return NextResponse.json({ error: "storage not configured" }, { status: 500 });
  }

  let body: { donation_id?: string; reason?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be JSON" }, { status: 400 });
  }
  const id = typeof body.donation_id === "string" ? body.donation_id.trim() : "";
  // The id is matched by path suffix below, so anything but a full UUID could hit the wrong record.
  if (!UUID.test(id)) return NextResponse.json({ error: "donation_id must be a UUID" }, { status: 400 });

  try {
    // Find the record blob for this donation (path is records/<date>/<id>.json).
    let match: { url: string; pathname: string } | undefined;
    let cursor: string | undefined;
    do {
      const page = await list({ prefix: "records/", cursor, limit: 1000 });
      match = page.blobs.find((b) => b.pathname.endsWith(`/${id}.json`));
      cursor = !match && page.hasMore ? page.cursor : undefined;
    } while (cursor && !match);

    if (!match) return NextResponse.json({ error: "no logged donation with that id" }, { status: 404 });

    const r = await fetch(match.url, {
      headers: { authorization: `Bearer ${process.env.BLOB_READ_WRITE_TOKEN}` },
    });
    if (!r.ok) throw new Error(`could not read the record (HTTP ${r.status})`);
    const record = (await r.json()) as Record<string, unknown>;

    if (record.voided === true) {
      return NextResponse.json({ ok: true, already_voided: true, donation_id: id });
    }

    // Remove the Farmbrite draft order first. The record is marked voided only once
    // that worked or there is no order, so a failed delete is retried by the next
    // void instead of leaving inventory in Farmbrite that the CSV no longer shows.
    let orderId: string | null = null;
    let farmbriteError: string | null = null;
    // No scan when the record says n8n never posted an order (it skipped Farmbrite, or
    // there was no positive weight), or when this deployment has no Farmbrite key.
    const w = record.weight_lbs;
    const noOrderToFind =
      typeof record.farmbrite_skipped_reason === "string" ||
      w === null ||
      (typeof w === "number" && w <= 0) ||
      !process.env.FARMBRITE_API_KEY;
    try {
      orderId =
        (typeof record.farmbrite_order_id === "string" && record.farmbrite_order_id) ||
        (noOrderToFind ? null : await findFarmbriteOrderId(id));
      if (orderId) await deleteFarmbriteOrder(orderId);
    } catch (e) {
      farmbriteError = e instanceof Error ? e.message : "Farmbrite delete failed";
    }

    const updated = farmbriteError
      ? { ...record, farmbrite_void_error: farmbriteError }
      : {
          ...record,
          voided: true,
          voided_at: new Date().toISOString(),
          void_reason: body.reason ?? null,
          farmbrite_void_error: null,
        };
    await put(match.pathname, JSON.stringify(updated), {
      access: "private",
      contentType: "application/json",
      addRandomSuffix: false,
      allowOverwrite: true,
    });

    if (farmbriteError) {
      return NextResponse.json(
        {
          ok: false,
          donation_id: id,
          farmbrite_order_removed: false,
          farmbrite_error: farmbriteError,
          error: "Farmbrite did not remove the order, so the donation is still logged. Try Undo again.",
        },
        { status: 502 }
      );
    }
    return NextResponse.json({
      ok: true,
      donation_id: id,
      farmbrite_order_removed: Boolean(orderId),
      farmbrite_error: null,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "void failed" },
      { status: 500 }
    );
  }
}
