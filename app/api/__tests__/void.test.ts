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
