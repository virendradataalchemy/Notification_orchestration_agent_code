import { useEffect, useState } from "react";
import { fetchJson } from "@/lib/client-portal";

type Stats = {
  total_client_templates: number;
  total_global_templates_available: number;
  templates_by_channel: Record<string, number>;
  client_name?: string;
};

export function DashboardStats({ clientId }: { clientId: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await fetchJson<Stats>("/api/v1/client/templates/stats", {
          headers: { "X-Client-Id": clientId },
        });
        setStats(data);
      } catch (err) {
        console.error("Failed to load stats", err);
      } finally {
        setLoading(false);
      }
    };
    loadStats();
  }, [clientId]);

  if (loading || !stats) return null;

  const totalAvailable = stats.total_client_templates + stats.total_global_templates_available;
  const activeChannels = Object.keys(stats.templates_by_channel).length;

  return (
    <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
      <StatCard icon="📝" label="Your Templates" value={stats.total_client_templates} />
      <StatCard icon="🌍" label="Global Templates" value={stats.total_global_templates_available} />
      <StatCard icon="📊" label="Active Channels" value={activeChannels} />
      <StatCard icon="✅" label="Total Available" value={totalAvailable} />
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: string; label: string; value: number }) {
  return (
    <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-md">
      <div className="mb-4 text-3xl">{icon}</div>
      <div className="text-3xl font-bold text-indigo-600">{value}</div>
      <div className="text-xs font-bold uppercase tracking-wider text-slate-400">{label}</div>
    </div>
  );
}
