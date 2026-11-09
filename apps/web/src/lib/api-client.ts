import type { components } from "@/types/api.generated";
export type Health = components["schemas"]["Health"];
export type SystemStatus = components["schemas"]["SystemStatus"];
type Session = components["schemas"]["SessionOut"];

export const API_BASE = "http://127.0.0.1:8000/api/v1";
let csrf: string | undefined;
export class ApiError extends Error {
  constructor(
    public code: string,
    public status = 0,
  ) {
    super(code);
  }
}
export async function request<T>(
  path: string,
  options: {
    method?: "GET" | "POST" | "DELETE";
    body?: unknown;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const attempts = method === "GET" ? 2 : 1;
  for (let i = 0; i < attempts; i++) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    options.signal?.addEventListener("abort", cancel, { once: true });
    if (options.signal?.aborted) controller.abort();
    const timeout = setTimeout(cancel, 5000);
    try {
      const response = await fetch(API_BASE + path, {
        method,
        credentials: "include",
        cache: "no-store",
        signal: controller.signal,
        headers: {
          ...(method !== "GET" ? { "Content-Type": "application/json" } : {}),
          ...(csrf && method !== "GET" ? { "X-CSRF-Token": csrf } : {}),
        },
        ...(options.body === undefined
          ? {}
          : { body: JSON.stringify(options.body) }),
      });
      if (!response.ok) {
        let code = "REQUEST_REJECTED";
        try {
          code = (await response.json()).error?.code ?? code;
        } catch {
          /* bounded public error */
        }
        if (response.status === 401) csrf = undefined;
        throw new ApiError(code, response.status);
      }
      return response.status === 204
        ? (undefined as T)
        : ((await response.json()) as T);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (options.signal?.aborted) throw new ApiError("ABORTED");
      if (i + 1 === attempts)
        throw new ApiError(controller.signal.aborted ? "TIMEOUT" : "OFFLINE");
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", cancel);
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new ApiError("OFFLINE");
}

let sessionPromise: Promise<void> | undefined;
export function initializeSession(): Promise<void> {
  // Shared promise prevents React StrictMode or route changes replaying bootstrap.
  if (!sessionPromise) {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const secret = fragment.get("bootstrap");
    window.history.replaceState(null, "", window.location.pathname);
    sessionPromise = (async () => {
      const value = secret
        ? await request<Session>("/session/bootstrap", {
            method: "POST",
            body: { bootstrap_secret: secret },
          })
        : await request<Session>("/session");
      csrf = value.csrf_token;
    })().catch((error) => {
      sessionPromise = undefined;
      throw error;
    });
  }
  return sessionPromise;
}
export async function revokeSession() {
  await request<void>("/session", { method: "DELETE" });
  csrf = undefined;
  sessionPromise = undefined;
}
export async function readDashboard(signal?: AbortSignal) {
  await initializeSession();
  const [health, status] = await Promise.all([
    request<Health>("/health", { signal }),
    request<SystemStatus>("/system/status", { signal }),
  ]);
  return { health, status };
}
