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
  const res = await fetch(`/api/v1/clients/by-supabase/${userId}`);
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export async function ensureClientProfile(user: AuthLikeUser): Promise<ClientProfile> {
  const existing = await fetchClientBySupabaseUid(user.id);
  if (existing) {
    return existing;
  }

  const res = await fetch("/api/v1/clients/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: deriveClientName(user),
      default_language: "en",
      is_active: true,
      supabase_uid: user.id,
    }),
  });

  if (!res.ok) {
    let message = `Failed to provision client profile (${res.status}).`;
    try {
      const err = await res.json();
      message = err.detail || err.message || message;
    } catch {
      // Keep the fallback message.
    }
    throw new Error(message);
  }

  return res.json();
}
