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
//   * the record is REWRITTEN with voided:true (photo + original values kept, so
//     the training corpus and any audit question survive)
//   * the Farmbrite draft order is deleted, because that one is real inventory
//   * /api/export drops voided rows from the running CSV
//
// The Google Sheet row is left in place — n8n owns that credential, not this route.
// The CSV is the authoritative export, and it excludes voided rows.

import { NextRequest, NextResponse } from "next/server";
import { list, put } from "@vercel/blob";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

/**
 * Find the draft order Aperture created for a donation.
 *
 * The order id is deliberately NOT threaded back through n8n: the Farmbrite write
 * runs in parallel with the response so a volunteer never waits on it. Instead the
 * order note carries "ref <first 8 chars of donation_id>", which is enough to find
 * it here. The API's page ordering does not reliably put newest last, so scan every
 * page (bounded) rather than guessing which end is recent. At their volume that is a
 * handful of requests.
 */
async function findFarmbriteOrderId(donationId: string): Promise<string | null> {
  const token = process.env.FARMBRITE_API_KEY;
  if (!token) return null;
  const ref = donationId.slice(0, 8);
  const headers = { Authorization: `Bearer ${token}`, Accept: "application/json" };
  try {
    const first = await (
      await fetch("https://api.farmbrite.com/v1/orders?limit=100&page=1", { headers })
    ).json();
    const findIn = (data: { data?: { note?: string; id?: string }[] }) =>
      (data.data || []).find((o) => typeof o.note === "string" && o.note.includes(ref))?.id;

    const onPageOne = findIn(first);
    if (onPageOne) return onPageOne;

    const lastPage = Math.min(Number(first.total_pages || 1), 20);   // bound the scan
    for (let page = lastPage; page >= 2; page--) {
      const data = await (
        await fetch(`https://api.farmbrite.com/v1/orders?limit=100&page=${page}`, { headers })
      ).json();
      const hit = findIn(data);
      if (hit) return hit;
    }
  } catch {
    /* fall through — a missing order must not block the void */
  }
  return null;
}

async function deleteFarmbriteOrder(orderId: string): Promise<string | null> {
  const token = process.env.FARMBRITE_API_KEY;
  if (!token) return "FARMBRITE_API_KEY not configured";
  try {
    const r = await fetch(`https://api.farmbrite.com/v1/orders/${orderId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
    return r.ok ? null : `Farmbrite returned HTTP ${r.status}`;
  } catch (e) {
    return e instanceof Error ? e.message : "Farmbrite delete failed";
  }
}

export async function POST(req: NextRequest) {
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return NextResponse.json({ error: "storage not configured" }, { status: 500 });
  }

  let body: { donation_id?: string; reason?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be JSON" }, { status: 400 });
  }
  const id = (body.donation_id ?? "").trim();
  if (!id) return NextResponse.json({ error: "donation_id required" }, { status: 400 });

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

    const record = (await (
      await fetch(match.url, {
        headers: { authorization: `Bearer ${process.env.BLOB_READ_WRITE_TOKEN}` },
      })
    ).json()) as Record<string, unknown>;

    if (record.voided === true) {
      return NextResponse.json({ ok: true, already_voided: true, donation_id: id });
    }

    // Remove the Farmbrite draft order if one was created for this donation.
    let farmbriteError: string | null = null;
    const orderId =
      (typeof record.farmbrite_order_id === "string" && record.farmbrite_order_id) ||
      (await findFarmbriteOrderId(id));
    if (orderId) farmbriteError = await deleteFarmbriteOrder(orderId);

    const voided = {
      ...record,
      voided: true,
      voided_at: new Date().toISOString(),
      void_reason: body.reason ?? null,
      farmbrite_void_error: farmbriteError,
    };
    await put(match.pathname, JSON.stringify(voided), {
      access: "private",
      contentType: "application/json",
      addRandomSuffix: false,
      allowOverwrite: true,
    });

    return NextResponse.json({
      ok: true,
      donation_id: id,
      farmbrite_order_removed: Boolean(orderId) && !farmbriteError,
      farmbrite_error: farmbriteError,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "void failed" },
      { status: 500 }
    );
  }
}
