export type ClientProfile = {
  id: number;
  name?: string;
  client_slug?: string | null;
};

type AuthLikeUser = {
  id: string;
  email?: string | null;
  user_metadata?: {
    full_name?: string;
    name?: string;
  };
};

const DEFAULT_CLIENT_NAME_PREFIX = "Client";

function deriveClientName(user: AuthLikeUser) {
  const metadataName = user.user_metadata?.full_name || user.user_metadata?.name;
  if (metadataName && metadataName.trim()) {
    return metadataName.trim();
  }
  if (user.email && user.email.trim()) {
    return user.email.split("@")[0];
  }
  return `${DEFAULT_CLIENT_NAME_PREFIX} ${user.id.slice(0, 8)}`;
}

export async function fetchClientBySupabaseUid(userId: string): Promise<ClientProfile | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000); // 5s timeout
    const res = await fetch(`/api/v1/clients/by-supabase/${userId}`, { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) return null;
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function ensureClientProfile(user: AuthLikeUser): Promise<ClientProfile> {
  const existing = await fetchClientBySupabaseUid(user.id);
  if (existing) return existing;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  const res = await fetch("/api/v1/clients/create", {
    method: "POST",
    signal: controller.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: deriveClientName(user),
      default_language: "en",
      is_active: true,
      supabase_uid: user.id,
    }),
  });
  clearTimeout(timer);

  const text = await res.text();
  if (!res.ok) {
    let message = `Failed to provision client profile (${res.status}).`;
    try { const err = JSON.parse(text); message = err.detail || err.message || message; } catch { /* keep fallback */ }
    throw new Error(message);
  }

  try { return JSON.parse(text); } catch {
    throw new Error("Invalid response from server during client provisioning.");
  }
}
