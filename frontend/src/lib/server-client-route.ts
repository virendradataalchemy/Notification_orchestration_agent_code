import { headers } from "next/headers";

export type ResolvedClientRoute = {
  id: string;
  name: string;
  slug: string;
};

function fallbackSlug(name: string, id: string) {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return base || id;
}

async function appOrigin() {
  const headerStore = await headers();
  const host = headerStore.get("host");
  if (!host) throw new Error("Missing host header");
  const protocol = host.includes("localhost") || host.startsWith("127.0.0.1") ? "http" : "https";
  return `${protocol}://${host}`;
}

async function fetchClient(path: string) {
  const origin = await appOrigin();
  const response = await fetch(`${origin}${path}`, { cache: "no-store" });
  if (!response.ok) return null;
  return response.json();
}

export async function resolveClientRouteParam(clientParam: string): Promise<ResolvedClientRoute | null> {
  const bySlug = await fetchClient(`/api/v1/clients/by-slug/${encodeURIComponent(clientParam)}`);
  if (bySlug) {
    return {
      id: String(bySlug.id),
      name: bySlug.name || `Client ${bySlug.id}`,
      slug: bySlug.client_slug || fallbackSlug(bySlug.name || "", String(bySlug.id)),
    };
  }

  if (/^\d+$/.test(clientParam)) {
    const byId = await fetchClient(`/api/v1/clients/by-id/${encodeURIComponent(clientParam)}`);
    if (byId) {
      return {
        id: String(byId.id),
        name: byId.name || `Client ${byId.id}`,
        slug: byId.client_slug || fallbackSlug(byId.name || "", String(byId.id)),
      };
    }
  }

  return null;
}
