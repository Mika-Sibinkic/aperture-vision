import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const { put } = vi.hoisted(() => ({
  put: vi.fn(async (pathname: string, _body?: unknown, _opts?: unknown) => ({ url: `https://blob.test/${pathname}` })),
}));
vi.mock("@vercel/blob", () => ({ put, list: vi.fn() }));

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
