// In-memory cache for GET requests
const _cache = new Map<string, { data: unknown; expiresAt: number }>();

export async function fetchJson<T>(
  url: string,
  init?: RequestInit,
  cacheTtlMs = 0,  // 0 = no cache, pass ms to enable
): Promise<T> {
  const isGet = !init?.method || init.method.toUpperCase() === "GET";

  // Return cached value if available and not expired
  if (isGet && cacheTtlMs > 0) {
    const cached = _cache.get(url);
    if (cached && Date.now() < cached.expiresAt) {
      return cached.data as T;
    }
  }

  const response = await fetch(url, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  const data = await response.json() as T;

  if (isGet && cacheTtlMs > 0) {
    _cache.set(url, { data, expiresAt: Date.now() + cacheTtlMs });
  }

  return data;
}

export function invalidateFetchCache(urlPrefix?: string) {
  if (!urlPrefix) { _cache.clear(); return; }
  for (const key of _cache.keys()) {
    if (key.startsWith(urlPrefix)) _cache.delete(key);
  }
}

export function formatTimeAgo(dateStr?: string | null) {
  if (!dateStr) return "N/A";
  let s = dateStr;
  if (!s.endsWith("Z") && s.indexOf("+", 10) === -1) s = `${s}Z`;
  const seconds = Math.floor((Date.now() - new Date(s).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
