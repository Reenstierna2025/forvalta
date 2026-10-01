import { afterEach, describe, it, expect, vi } from "vitest";
import { save, ApiError } from "./api";
const response = (data: any, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => vi.unstubAllGlobals());
describe("Bekräftad sparning", () => {
  it("återhämtar ett sparat svar efter nätverksavbrott", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(
        response({ saved: true, result: { id: "abc", version: 1 } }),
      );
    vi.stubGlobal("fetch", fetch);
    expect(await save("work/", { title: "test network" })).toEqual({
      id: "abc",
      version: 1,
    });
    expect(fetch.mock.calls[1][0]).toMatch(/receipts\//);
  });
  it("återanvänder samma nyckel efter osäkert serversvar", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({}, 502))
      .mockResolvedValueOnce(response({ saved: false }))
      .mockResolvedValueOnce(response({ id: "ok" }));
    vi.stubGlobal("fetch", fetch);
    await expect(save("work/", { title: "test retry" })).rejects.toThrow(
      "Ingen bekräftelse",
    );
    await save("work/", { title: "test retry" });
    expect(fetch.mock.calls[0][1].headers["Idempotency-Key"]).toEqual(
      fetch.mock.calls[2][1].headers["Idempotency-Key"],
    );
  });
  it("visar versionskonflikt utan att påstå sparat", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({ detail: "En annan användare har ändrat posten." }, 409),
        ),
    );
    await expect(
      save("assets/123/", { version: 1 }, "PATCH"),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
