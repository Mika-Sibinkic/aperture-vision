import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@vercel/blob", () => ({
  put: vi.fn(async (pathname: string) => ({ url: `https://blob.test/${pathname}` })),
  list: vi.fn(async () => ({ blobs: [], hasMore: false })),
}));

import { POST as donate } from "../donate/route";
import { POST as voidRoute } from "../void/route";
import { GET as exportRoute } from "../export/route";

const TOKEN = "device-secret-123";

function req(path: string, method: string, token?: string, body?: unknown) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token !== undefined) headers["x-aperture-token"] = token;
  return new NextRequest(`http://relay.test${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const routes = [
  ["donate", () => donate, "/api/donate", "POST"],
  ["void", () => voidRoute, "/api/void", "POST"],
  ["export", () => exportRoute, "/api/export", "GET"],
] as const;

let n8n: ReturnType<typeof vi.fn>;

beforeEach(() => {
  process.env.N8N_WEBHOOK_URL = "https://n8n.test/webhook/donate";
  n8n = vi.fn(async () => new Response(JSON.stringify({ weight_lbs: 12.5, item_type: "kale" })));
  vi.stubGlobal("fetch", n8n);
});

afterEach(() => {
  delete process.env.APERTURE_DEVICE_TOKEN;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("device token", () => {
  for (const [name, handler, path, method] of routes) {
    it(`${name}: no header -> 401`, async () => {
      process.env.APERTURE_DEVICE_TOKEN = TOKEN;
      const res = await handler()(req(path, method, undefined, method === "POST" ? {} : undefined));
      expect(res.status).toBe(401);
    });

    it(`${name}: wrong header -> 401`, async () => {
      process.env.APERTURE_DEVICE_TOKEN = TOKEN;
      const res = await handler()(req(path, method, "nope", method === "POST" ? {} : undefined));
      expect(res.status).toBe(401);
    });
  }

  it("right header reaches n8n", async () => {
    process.env.APERTURE_DEVICE_TOKEN = TOKEN;
    const res = await donate(req("/api/donate", "POST", TOKEN, { description: "kale" }));
    expect(res.status).toBe(200);
    expect(n8n).toHaveBeenCalledTimes(1);
    expect(String(n8n.mock.calls[0][0])).toBe("https://n8n.test/webhook/donate");
  });

  it("unset env lets the call through and warns", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const res = await donate(req("/api/donate", "POST", undefined, { description: "kale" }));
    expect(res.status).toBe(200);
    expect(n8n).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalled();
  });
});
