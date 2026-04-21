import { headers } from "next/headers";

export type ResolvedClientRoute = {
  id: string;
  name: string;
  slug: string | null;
};

// In-process cache: avoids repeated backend calls within the same server process
const _cache = new Map<string, { value: ResolvedClientRoute | null; expiresAt: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function appOrigin() {
  const headerStore = await headers();
  const host = headerStore.get("host");
  if (!host) throw new Error("Missing host header");
  const protocol = host.includes("localhost") || host.startsWith("127.0.0.1") ? "http" : "https";
  return `${protocol}://${host}`;
}

async function fetchClient(path: string) {
  const origin = await appOrigin();
  try {
    const response = await fetch(`${origin}${path}`, { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

export async function resolveClientRouteParam(clientParam: string): Promise<ResolvedClientRoute | null> {
  const now = Date.now();
  const cached = _cache.get(clientParam);
  if (cached && now < cached.expiresAt) {
    return cached.value;
  }

  let result: ResolvedClientRoute | null = null;

  const bySlug = await fetchClient(`/api/v1/clients/by-slug/${encodeURIComponent(clientParam)}`);
  if (bySlug) {
    result = {
      id: String(bySlug.id),
      name: bySlug.name || `Client ${bySlug.id}`,
      slug: bySlug.client_slug || null,
    };
  } else if (/^\d+$/.test(clientParam)) {
    const byId = await fetchClient(`/api/v1/clients/by-id/${encodeURIComponent(clientParam)}`);
    if (byId) {
      result = {
        id: String(byId.id),
        name: byId.name || `Client ${byId.id}`,
        slug: byId.client_slug || null,
      };
    }
  }

  _cache.set(clientParam, { value: result, expiresAt: now + CACHE_TTL_MS });
  return result;
}
