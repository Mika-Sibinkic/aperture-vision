import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const { put, del } = vi.hoisted(() => ({
  put: vi.fn(async (pathname: string, _body?: unknown, _opts?: unknown) => ({ url: `https://blob.test/${pathname}` })),
  del: vi.fn(async (_url: string) => {}),
}));
vi.mock("@vercel/blob", () => ({ put, del, list: vi.fn() }));

import { POST as donate } from "../donate/route";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PHOTO = Buffer.alloc(2000, 7).toString("base64");   // big enough to pass the archive size check

const post = (body: unknown) =>
  donate(new NextRequest("http://relay.test/api/donate", { method: "POST", body: JSON.stringify(body) }));

let n8n: ReturnType<typeof vi.fn>;

beforeEach(() => {
  process.env.N8N_WEBHOOK_URL = "https://n8n.test/webhook/donate";
  process.env.BLOB_READ_WRITE_TOKEN = "blob-test";
  n8n = vi.fn(async () => new Response(JSON.stringify({ weight_lbs: 12.5, item_type: "kale" })));
  vi.stubGlobal("fetch", n8n);
  vi.spyOn(console, "warn").mockImplementation(() => {});
  put.mockClear();
  del.mockClear();
});

afterEach(() => {
  delete process.env.BLOB_READ_WRITE_TOKEN;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const sentToN8n = () => JSON.parse(n8n.mock.calls[0][1].body as string);

describe("donate input validation", () => {
  it("a non-string description is handled, not an empty-body 500", async () => {
    const res = await post({ description: 12 });
    expect(res.status).toBeLessThan(500);
    expect(await res.json()).toMatchObject({ weight_lbs: 12.5 });
    expect(sentToN8n().description).toBe("");
  });

  it("a quote-bearing donation_id is replaced, never stored as given", async () => {
    const evil = "x');alert(1);//";
    await post({ donation_id: evil, image_b64: PHOTO });
    const id = sentToN8n().donation_id;
    expect(id).toMatch(UUID);
    for (const [pathname] of put.mock.calls) expect(pathname).not.toContain(evil);
  });

  it("keeps a valid client UUID so retries share one id", async () => {
    const id = "0b8e1c52-6f0a-4c1e-9d2b-3a4f5e6d7c8b";
    await post({ donation_id: id });
    expect(sentToN8n().donation_id).toBe(id);
  });

  it("an unparseable triggered_at falls back to now, and the blob day comes from the date", async () => {
    await post({ triggered_at: "../../evil", image_b64: PHOTO });
    const sent = sentToN8n();
    expect(Number.isNaN(Date.parse(sent.triggered_at))).toBe(false);
    const day = new Date().toISOString().slice(0, 10);
    for (const [pathname] of put.mock.calls) expect(pathname).toMatch(new RegExp(`^(donations|records)/${day}/`));
  });

  it("normalises a parseable non-ISO triggered_at before using it as the day", async () => {
    await post({ triggered_at: "2026-08-01T21:59:00-05:00", image_b64: PHOTO });
    expect(sentToN8n().triggered_at).toBe("2026-08-02T02:59:00.000Z");
    expect(put.mock.calls[0][0]).toMatch(/^donations\/2026-08-02\//);
  });
});

describe("duplicate taps", () => {
  it("a photo that already exists for this donation_id returns 409 without calling n8n", async () => {
    // The SDK has no dedicated class for this; it throws a BlobError carrying the API message.
    put.mockRejectedValueOnce(
      new Error("Vercel Blob: This blob already exists, use `allowOverwrite: true` if you want to overwrite it."),
    );
    const res = await post({ donation_id: "0b8e1c52-6f0a-4c1e-9d2b-3a4f5e6d7c8b", image_b64: PHOTO });
    expect(res.status).toBe(409);
    expect((await res.json()).error).toBe("already logged or in progress");
    expect(n8n).toHaveBeenCalledTimes(0);
  });

  it("any other archive failure still logs the donation", async () => {
    put.mockRejectedValueOnce(new Error("Vercel Blob: service unavailable"));
    const res = await post({ donation_id: "0b8e1c52-6f0a-4c1e-9d2b-3a4f5e6d7c8b", image_b64: PHOTO });
    expect(res.status).toBe(200);
    expect(n8n).toHaveBeenCalledTimes(1);
  });
});

describe("a failed n8n call does not block the retry", () => {
  const ID = "0b8e1c52-6f0a-4c1e-9d2b-3a4f5e6d7c8b";

  // A Blob fake that refuses a second write to a path, like the real store, until it is deleted.
  beforeEach(() => {
    const stored = new Set<string>();
    put.mockImplementation(async (pathname: string) => {
      if (stored.has(pathname)) throw new Error("Vercel Blob: This blob already exists");
      stored.add(pathname);
      return { url: `https://blob.test/${pathname}` };
    });
    del.mockImplementation(async (url: string) => {
      stored.delete(url.replace("https://blob.test/", ""));
    });
  });

  it.each([
    ["n8n 500", () => new Response("node threw", { status: 500 })],
    ["empty n8n body", () => new Response("")],
    ["n8n unreachable", () => Promise.reject(new TypeError("fetch failed"))],
    // n8n's Respond node defaults to 200, so a refused shared token arrives as ok.
    ["n8n 200 with an error body", () => new Response(JSON.stringify({ error: "invalid token" }))],
  ])("%s: the photo is released and the retry reaches n8n", async (_label, firstReply) => {
    n8n.mockImplementationOnce(firstReply);
    const first = await post({ donation_id: ID, image_b64: PHOTO });
    expect(first.status).toBeGreaterThanOrEqual(500);
    expect(put.mock.calls.some(([pathname]) => pathname.startsWith("records/"))).toBe(false);

    const retry = await post({ donation_id: ID, image_b64: PHOTO });
    expect(retry.status).toBe(200);
    expect(await retry.json()).toMatchObject({ weight_lbs: 12.5 });
    expect(n8n).toHaveBeenCalledTimes(2);
  });

  it("a timeout keeps the photo, because n8n may still log the first attempt", async () => {
    vi.useFakeTimers();
    // n8n never answers, so the relay's own 100 s timer aborts the call.
    n8n.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    const first = post({ donation_id: ID, image_b64: PHOTO });
    await vi.advanceTimersByTimeAsync(100_000);
    vi.useRealTimers();
    expect((await first).status).toBe(504);
    expect((await post({ donation_id: ID, image_b64: PHOTO })).status).toBe(409);
    expect(del).not.toHaveBeenCalled();
  });
});
