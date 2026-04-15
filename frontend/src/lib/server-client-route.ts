// Vite/React version — client-side only, no Next.js server headers needed
export type ResolvedClientRoute = {
  id: string;
  name: string;
  slug: string | null;
};

// Simple in-memory cache
const _cache = new Map<string, { value: ResolvedClientRoute | null; expiresAt: number }>();
const TTL = 5 * 60 * 1000;

export async function resolveClientRouteParam(clientParam: string): Promise<ResolvedClientRoute | null> {
  const now = Date.now();
  const cached = _cache.get(clientParam);
  if (cached && now < cached.expiresAt) return cached.value;

  let result: ResolvedClientRoute | null = null;
  try {
    const bySlug = await fetch(`/api/v1/clients/by-slug/${encodeURIComponent(clientParam)}`);
    if (bySlug.ok) {
      const d = await bySlug.json();
      result = { id: String(d.id), name: d.name || `Client ${d.id}`, slug: d.client_slug || null };
    } else if (/^\d+$/.test(clientParam)) {
      const byId = await fetch(`/api/v1/clients/by-id/${encodeURIComponent(clientParam)}`);
      if (byId.ok) {
        const d = await byId.json();
        result = { id: String(d.id), name: d.name || `Client ${d.id}`, slug: d.client_slug || null };
      }
    }
  } catch {
    // network error — return null
  }

  _cache.set(clientParam, { value: result, expiresAt: now + TTL });
  return result;
}
