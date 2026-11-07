import { afterEach, expect, it, vi } from "vitest";
import { ApiError, request } from "./api-client";
afterEach(() => vi.unstubAllGlobals());
it("uses credentialed GET and retries network failures once", async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new TypeError())
    .mockResolvedValueOnce(new Response('{"status":"ok"}'));
  vi.stubGlobal("fetch", fetch);
  expect(await request("/health")).toEqual({ status: "ok" });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls[0][1].credentials).toBe("include");
});
it("never retries mutations", async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError());
  vi.stubGlobal("fetch", fetch);
  await expect(
    request("/session/bootstrap", { method: "POST", body: {} }),
  ).rejects.toMatchObject({ code: "OFFLINE" });
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("maps session expiry without retrying", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response('{"error":{"code":"SESSION_REQUIRED"}}', { status: 401 }),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(request("/system/status")).rejects.toMatchObject({
    status: 401,
    code: "SESSION_REQUIRED",
  });
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("cancels without retry when caller aborts", async () => {
  const controller = new AbortController();
  controller.abort();
  const fetch = vi
    .fn()
    .mockRejectedValue(new DOMException("Aborted", "AbortError"));
  vi.stubGlobal("fetch", fetch);
  await expect(
    request("/health", { signal: controller.signal }),
  ).rejects.toBeInstanceOf(ApiError);
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("reuses one bootstrap exchange and immediately clears fragment", async () => {
  vi.resetModules();
  window.history.replaceState(null, "", "/dashboard#bootstrap=unit-secret");
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response('{"csrf_token":"unit-csrf","expires_at":"later"}'),
    );
  vi.stubGlobal("fetch", fetch);
  const api = await import("./api-client");
  await Promise.all([api.initializeSession(), api.initializeSession()]);
  expect(window.location.hash).toBe("");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).not.toContain("unit-secret");
});
