"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson, formatTimeAgo } from "@/lib/client-portal";

type ChannelAnalytics = {
  channel: string;
  total: number;
  sent: number;
  delivered: number;
  failed: number;
  success_rate: number;
};

type OverviewResponse = {
  client_name: string;
  tier: string;
  channels: ChannelAnalytics[];
};

type NotificationItem = {
  type: string;
  recipient: string;
  status: string;
  priority: string;
  created_at?: string;
};

type ClientAnalyticsPageProps = {
  clientIdProp?: string;
  clientPathProp?: string;
  initialClientName?: string;
};

export default function ClientAnalyticsPage({
  clientIdProp,
  clientPathProp,
  initialClientName = "",
}: ClientAnalyticsPageProps = {}) {
  const params = useParams<{ id: string }>();
  const clientId = clientIdProp || String(params.id);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [activeChannel, setActiveChannel] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await fetchJson<OverviewResponse>(`/api/client-dashboard/client/${clientId}/overview`);
        if (!active) return;
        setOverview(data);
        const nextChannel = activeChannel || data.channels[0]?.channel || "";
        if (nextChannel) {
          setActiveChannel(nextChannel);
          const history = await fetchJson<{ notifications: NotificationItem[] }>(
            `/api/client-dashboard/client/${clientId}/channel/${nextChannel}`,
          );
          if (active) setNotifications(history.notifications || []);
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [activeChannel, clientId]);

  const loadChannel = async (channel: string) => {
    setActiveChannel(channel);
    const history = await fetchJson<{ notifications: NotificationItem[] }>(
      `/api/client-dashboard/client/${clientId}/channel/${channel}`,
    );
    setNotifications(history.notifications || []);
  };

  const channels = overview?.channels ?? [];
  const totalNotifications = channels.reduce((sum, channel) => sum + channel.total, 0);
  const totalSuccess = channels.reduce((sum, channel) => sum + channel.sent + channel.delivered, 0);
  const totalFailed = channels.reduce((sum, channel) => sum + channel.failed, 0);
  const avgSuccessRate = channels.length
    ? Math.round(channels.reduce((sum, channel) => sum + channel.success_rate, 0) / channels.length)
    : 0;

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPathProp || clientId}
      title={overview?.client_name || initialClientName || "Analytics"}
      description="Track delivery reliability, channel performance, and recent transmission ledger activity from the frontend analytics workspace."
    >
      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading analytics...</p>
        </section>
      ) : (
        <>
          <div className="mb-6 grid gap-5 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard label="Transmissions" value={String(totalNotifications)} />
            <MetricCard label="Endpoints" value={String(channels.length)} />
            <MetricCard label="Delivered" value={String(totalSuccess)} tone="emerald" />
            <MetricCard label="Dropped" value={String(totalFailed)} tone="rose" />
            <MetricCard label="Reliability" value={`${avgSuccessRate}%`} />
          </div>

          <section className="mb-6 rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
            <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-slate-400">Active Channels</p>
            <div className="space-y-4">
              {channels.map((channel) => (
                <button
                  key={channel.channel}
                  onClick={() => loadChannel(channel.channel)}
                  className={`w-full rounded-2xl border p-5 text-left transition ${
                    activeChannel === channel.channel
                      ? "border-slate-900 bg-slate-50 shadow-sm"
                      : "border-slate-200 bg-white hover:border-slate-400"
                  }`}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-bold uppercase tracking-wide text-slate-800">{channel.channel}</span>
                    <span className="font-mono text-sm text-slate-500">{channel.success_rate}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100">
                    <div
                      className={`h-2 rounded-full ${
                        channel.success_rate >= 80
                          ? "bg-emerald-500"
                          : channel.success_rate >= 50
                            ? "bg-amber-500"
                            : "bg-rose-500"
                      }`}
                      style={{ width: `${channel.success_rate}%` }}
                    />
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-200 bg-white/80 shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 px-6 py-5">
              <p className="text-sm font-bold uppercase tracking-[0.2em] text-slate-400">
                Transmission Ledger {activeChannel ? `• ${activeChannel.toUpperCase()}` : ""}
              </p>
            </div>
            {notifications.length === 0 ? (
              <div className="p-8 text-sm text-slate-500">No ledger entries found.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px]">
                  <thead className="bg-slate-50 text-left">
                    <tr>
                      {["Payload Type", "Target", "State", "Priority", "Clock"].map((label) => (
                        <th key={label} className="px-6 py-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {notifications.map((notification, index) => (
                      <tr key={`${notification.recipient}-${index}`} className="bg-white">
                        <td className="px-6 py-4 text-sm font-semibold text-slate-800">{notification.type}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{notification.recipient}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{notification.status}</td>
                        <td className="px-6 py-4 text-sm uppercase text-slate-500">{notification.priority}</td>
                        <td className="px-6 py-4 text-sm text-slate-500">{formatTimeAgo(notification.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </ClientPortalShell>
  );
}

function MetricCard({
  label,
  value,
  tone = "indigo",
}: {
  label: string;
  value: string;
  tone?: "indigo" | "emerald" | "rose";
}) {
  const toneMap = {
    indigo: "text-indigo-700",
    emerald: "text-emerald-700",
    rose: "text-rose-700",
  } as const;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className={`text-4xl font-bold tracking-tight ${toneMap[tone]}`}>{value}</p>
    </section>
  );
}
