import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@vercel/blob", () => ({ list, put: vi.fn() }));

import { GET as exportRoute } from "../export/route";

// Synthetic records; `status` lets one blob read fail.
function fakeRecords(records: { row: Record<string, unknown>; status?: number }[]) {
  list.mockResolvedValue({
    blobs: records.map((_, i) => ({ url: `https://blob.test/${i}`, pathname: `records/2026-08-02/r${i}.json` })),
    hasMore: false,
  });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const r = records[Number(String(url).split("/").pop())];
    return new Response(JSON.stringify(r.row), { status: r.status ?? 200 });
  }));
}

const csv = () => exportRoute(new NextRequest("http://relay.test/api/export"));

beforeEach(() => {
  process.env.BLOB_READ_WRITE_TOKEN = "blob-test";
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  delete process.env.BLOB_READ_WRITE_TOKEN;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("export CSV", () => {
  it("neutralises cells a spreadsheet would run as a formula", async () => {
    fakeRecords([{ row: { triggered_at: "2026-08-02T10:00:00Z", description: "=1+1", item_type: "@SUM(A1)", weight_lbs: -2 } }]);
    const body = await (await csv()).text();
    const [, line] = body.split("\n");
    expect(line).toContain(",'=1+1,");
    expect(line).toContain(",'@SUM(A1),");
    expect(line).toContain(",-2,");                 // numbers are data, not formulas
  });

  it("one unreadable record out of 3 is a 500, not a 200 with 2 rows", async () => {
    fakeRecords([
      { row: { triggered_at: "2026-08-02T10:00:00Z", weight_lbs: 1 } },
      { row: { error: "rate limited" }, status: 429 },
      { row: { triggered_at: "2026-08-02T11:00:00Z", weight_lbs: 2 } },
    ]);
    const res = await csv();
    expect(res.status).toBe(500);
    expect((await res.json()).error).toMatch(/could not be read/);
  });
});
