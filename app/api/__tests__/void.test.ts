import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const { put, list } = vi.hoisted(() => ({ put: vi.fn(), list: vi.fn() }));
vi.mock("@vercel/blob", () => ({ put, list }));

import { POST as voidRoute } from "../void/route";

const ID = "0b8e1c52-6f0a-4c1e-9d2b-3a4f5e6d7c8b";

const post = (body: unknown) =>
  voidRoute(new NextRequest("http://relay.test/api/void", { method: "POST", body: JSON.stringify(body) }));

beforeEach(() => {
  process.env.BLOB_READ_WRITE_TOKEN = "blob-test";
  vi.spyOn(console, "warn").mockImplementation(() => {});
  put.mockReset();
  list.mockReset();
});

afterEach(() => {
  delete process.env.BLOB_READ_WRITE_TOKEN;
  delete process.env.FARMBRITE_API_KEY;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("void input validation", () => {
  it("rejects a non-UUID id with 400 before touching storage", async () => {
    const res = await post({ donation_id: "0b8e1c52" });   // a prefix would match by endsWith
    expect(res.status).toBe(400);
    expect(list).not.toHaveBeenCalled();
  });
});

// Synthetic Farmbrite + blob fakes. `orders` is the Draft listing, `deletes` the DELETE status.
function fakeUpstream(opts: { record: Record<string, unknown>; recordStatus?: number; orders?: { id: string; note: string }[]; deleteStatus?: number }) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const u = String(url);
    calls.push(`${init?.method ?? "GET"} ${u}`);
    if (u.startsWith("https://blob.test/")) {
      return new Response(JSON.stringify(opts.record), { status: opts.recordStatus ?? 200 });
    }
    if (init?.method === "DELETE") return new Response("{}", { status: opts.deleteStatus ?? 200 });
    return new Response(JSON.stringify({ data: opts.orders ?? [], total_pages: 1 }));
  });
  vi.stubGlobal("fetch", fetchMock);
  list.mockResolvedValue({ blobs: [{ url: "https://blob.test/r", pathname: `records/2026-08-02/${ID}.json` }], hasMore: false });
  return calls;
}

const lastPut = () => JSON.parse(put.mock.calls.at(-1)![1] as string);

describe("void is honest about Farmbrite", () => {
  beforeEach(() => {
    process.env.FARMBRITE_API_KEY = "fb-test";
  });

  it("a failed delete leaves the record live with the error, and a repeat void retries", async () => {
    fakeUpstream({ record: { donation_id: ID, farmbrite_order_id: "ord-1" }, deleteStatus: 500 });
    const first = await post({ donation_id: ID });
    expect(first.status).toBe(502);
    expect(await first.json()).toMatchObject({ ok: false, farmbrite_order_removed: false });
    expect(lastPut().voided).toBeUndefined();
    expect(lastPut().farmbrite_void_error).toContain("500");

    const calls = fakeUpstream({ record: lastPut(), deleteStatus: 200 });
    const second = await post({ donation_id: ID });
    expect(await second.json()).toMatchObject({ ok: true, farmbrite_order_removed: true });
    expect(calls).toContain("DELETE https://api.farmbrite.com/v1/orders/ord-1");
    expect(lastPut().voided).toBe(true);
  });

  it("the fallback lookup lists drafts and matches the ref exactly", async () => {
    const calls = fakeUpstream({
      record: { donation_id: ID },
      orders: [
        { id: "decoy", note: `Merged from ref ${ID.slice(0, 8)} - Dock intake - Kale - ref 99999999` },
        { id: "real", note: `Dock intake - Kale - ref ${ID.slice(0, 8)}` },
      ],
    });
    const res = await post({ donation_id: ID });
    expect(await res.json()).toMatchObject({ ok: true, farmbrite_order_removed: true });
    expect(calls.some((c) => c.startsWith("GET https://api.farmbrite.com/v1/orders?status=Draft"))).toBe(true);
    expect(calls).toContain("DELETE https://api.farmbrite.com/v1/orders/real");
    expect(calls).not.toContain("DELETE https://api.farmbrite.com/v1/orders/decoy");
  });

  it("no matching order still voids", async () => {
    fakeUpstream({ record: { donation_id: ID }, orders: [] });
    const res = await post({ donation_id: ID });
    expect(await res.json()).toMatchObject({ ok: true, farmbrite_order_removed: false });
    expect(lastPut().voided).toBe(true);
  });

  it("a non-ok record fetch fails without overwriting the record", async () => {
    fakeUpstream({ record: { error: "rate limited" }, recordStatus: 429 });
    const res = await post({ donation_id: ID });
    expect(res.status).toBe(500);
    expect(put).not.toHaveBeenCalled();
  });
});
