export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  // Only apply default caching for GET requests
  const isGet = !init?.method || init.method.toUpperCase() === "GET";
  const options: RequestInit = init ?? (isGet ? {
    next: { revalidate: 60 },
  } : {});

  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch {
      // Ignore invalid JSON and keep fallback message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function formatTimeAgo(dateStr?: string | null) {
  if (!dateStr) return "N/A";
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "< 1m";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
