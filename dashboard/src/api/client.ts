/**
 * One Piece API client — typed, timeout-aware, retryable HTTP wrapper.
 *
 * All API calls go through this module. Never call fetch() directly in components.
 * Timeouts:  default 10s, chat endpoints 35s
 * Retries:   GET requests retry once on network error (not on 4xx/5xx)
 */
import { API_BASE, API_KEY } from "@/lib/constants";

const TIMEOUT_MS      = 10_000;
const TIMEOUT_CHAT_MS = 35_000;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly path: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const isBodyRequest = options?.method && ["POST", "PUT", "PATCH"].includes(options.method);
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-Api-Key"] = API_KEY;
  if (isBodyRequest) headers["Content-Type"] = "application/json";
  if (options?.headers) Object.assign(headers, options.headers);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new ApiError(`API ${res.status}: ${text}`, res.status, path);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new ApiError(`Request timeout after ${timeoutMs}ms: ${path}`, 408, path);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** GET with one automatic retry on transient network failure (not on HTTP errors). */
async function get<T>(path: string): Promise<T> {
  try {
    return await request<T>(path);
  } catch (err) {
    if (err instanceof ApiError) throw err; // don't retry HTTP errors
    return request<T>(path);               // retry once on network/timeout
  }
}

export const api = {
  get,
  post: <T>(path: string, body?: unknown) =>
    request<T>(
      path,
      { method: "POST", body: body != null ? JSON.stringify(body) : undefined },
      path.includes("/chat/") || path.includes("/scan/chunk") ? TIMEOUT_CHAT_MS : TIMEOUT_MS,
    ),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body != null ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) =>
    request<T>(path, { method: "DELETE" }),
};
