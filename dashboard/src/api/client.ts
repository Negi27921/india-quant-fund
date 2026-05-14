import { API_BASE } from "@/lib/constants";

const TIMEOUT_MS = 10_000;
const TIMEOUT_CHAT_MS = 35_000;

async function request<T>(path: string, options?: RequestInit, timeoutMs = TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const isBodyRequest = options?.method && ["POST", "PUT", "PATCH"].includes(options.method);
  const headers: Record<string, string> = isBodyRequest ? { "Content-Type": "application/json" } : {};
  if (options?.headers) Object.assign(headers, options.headers);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`API ${res.status}: ${text}`);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error(`Request timeout: ${path}`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }, path.includes("/chat/") ? TIMEOUT_CHAT_MS : TIMEOUT_MS),
  delete: <T>(path: string) =>
    request<T>(path, { method: "DELETE" }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
};
