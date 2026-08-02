// Running CSV of every donation — downloadable straight from Aperture.
//
//   GET /api/export            -> CSV (opens/downloads in Safari on the iPad)
//   GET /api/export?format=json -> the same rows as JSON
//   GET /api/export?since=2026-08-01 -> only rows on/after that date
//
// Source of truth is one small JSON blob per donation, written by /api/donate
// after n8n returns. One file per donation (never an append to a shared file)
// so concurrent taps can never clobber each other's rows.
//
// Columns are derived from the union of keys actually present, so when we add a
// field (container_count, ground truth, a new model) it shows up in the CSV
// automatically — no schema to keep in sync.

import { NextRequest, NextResponse } from "next/server";
import { list } from "@vercel/blob";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

// Stable leading columns; everything else is appended alphabetically after these.
const LEAD = [
  "triggered_at",
  "donation_id",
  "item_type",
  "weight_lbs",
  "true_weight_lbs",
  "container_type",
  "container_count",
  "container_fill_fraction",
  "confidence",
  "description",
  "location",
];

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = typeof value === "object" ? JSON.stringify(value) : String(value);
  // Quote if the value could break the row; double any embedded quotes.
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function GET(req: NextRequest) {
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return NextResponse.json({ error: "storage not configured" }, { status: 500 });
  }

  const since = req.nextUrl.searchParams.get("since");
  const wantJson = req.nextUrl.searchParams.get("format") === "json";

  try {
    // Page through every record blob.
    const blobs: { url: string; pathname: string }[] = [];
    let cursor: string | undefined;
    do {
      const page = await list({ prefix: "records/", cursor, limit: 1000 });
      blobs.push(...page.blobs.map((b) => ({ url: b.url, pathname: b.pathname })));
      cursor = page.hasMore ? page.cursor : undefined;
    } while (cursor);

    const wanted = since
      ? blobs.filter((b) => (b.pathname.split("/")[1] ?? "") >= since)
      : blobs;

    // Fetch in bounded batches so a large history can't exhaust the function.
    const rows: Record<string, unknown>[] = [];
    const readErrors: string[] = [];
    const BATCH = 25;
    for (let i = 0; i < wanted.length; i += BATCH) {
      const chunk = wanted.slice(i, i + BATCH);
      // The store is PRIVATE, so blob URLs are not publicly readable — the
      // read-write token must be presented explicitly. [fixed 2026-08-02]
      const settled = await Promise.allSettled(
        chunk.map((b) =>
          fetch(b.url, {
            headers: { authorization: `Bearer ${process.env.BLOB_READ_WRITE_TOKEN}` },
          }).then((r) => {
            if (!r.ok) throw new Error(`blob ${b.pathname} -> HTTP ${r.status}`);
            return r.json() as Promise<Record<string, unknown>>;
          })
        )
      );
      for (const s of settled) {
        if (s.status === "fulfilled") rows.push(s.value);
        else readErrors.push(String(s.reason).slice(0, 120));
      }
    }

    rows.sort((a, b) => String(a.triggered_at ?? "").localeCompare(String(b.triggered_at ?? "")));

    if (wantJson) {
      return NextResponse.json({
        count: rows.length,
        blobs_found: wanted.length,
        read_errors: readErrors.slice(0, 5),
        rows,
      });
    }
    // Never hand back a silently-empty CSV when records exist but could not be read.
    if (rows.length === 0 && wanted.length > 0) {
      return NextResponse.json(
        { error: "records exist but none could be read", blobs_found: wanted.length, read_errors: readErrors.slice(0, 5) },
        { status: 500 }
      );
    }

    const extra = [...new Set(rows.flatMap((r) => Object.keys(r)))]
      .filter((k) => !LEAD.includes(k))
      .sort();
    const headers = [...LEAD, ...extra];

    const csv = [
      headers.join(","),
      ...rows.map((r) => headers.map((h) => csvCell(r[h])).join(",")),
    ].join("\n");

    const stamp = new Date().toISOString().slice(0, 10);
    return new NextResponse(csv, {
      status: 200,
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": `attachment; filename="aperture-donations-${stamp}.csv"`,
        "cache-control": "no-store",
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "export failed";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
