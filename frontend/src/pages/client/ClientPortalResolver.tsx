import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { fetchJson } from "@/lib/client-portal";

export type ResolvedClientRoute = {
  id: string;
  name: string;
  slug: string | null;
};

export default function ClientPortalResolver() {
  const { slug } = useParams<{ slug: string }>();
  const location = useLocation();
  const [resolved, setResolved] = useState<ResolvedClientRoute | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const resolve = async () => {
      if (!slug) return;
      setLoading(true);
      setError(null);
      try {
        // Try by slug
        let data = await fetchJson<any>(`/api/v1/clients/by-slug/${encodeURIComponent(slug)}`).catch(() => null);
        
        // Try by id if not found and numeric
        if (!data && /^\d+$/.test(slug)) {
          data = await fetchJson<any>(`/api/v1/clients/by-id/${encodeURIComponent(slug)}`).catch(() => null);
        }

        if (!active) return;
        if (!data) {
          setError("Client not found");
          return;
        }

        setResolved({
          id: String(data.id),
          name: data.name || `Client ${data.id}`,
          slug: data.client_slug || null,
        });
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to resolve client");
      } finally {
        if (active) setLoading(false);
      }
    };
    resolve();
    return () => { active = false; };
  }, [slug]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <p className="text-sm text-slate-500">Resolving client portal...</p>
      </div>
    );
  }

  if (error || !resolved) {
    return <Navigate to="/login" replace />;
  }

  const canonical = resolved.slug || resolved.id;
  
  // Canonical redirect
  if (slug !== canonical) {
    const newPath = location.pathname.replace(`/clients/${slug}`, `/clients/${canonical}`);
    return <Navigate to={newPath} replace />;
  }

  return <Outlet context={{ resolved }} />;
}
