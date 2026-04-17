import { useEffect, useState } from "react";
import { fetchJson, formatTimeAgo } from "@/lib/client-portal";

type Notification = {
  id: string;
  type: string;
  priority: string;
  user_id: string;
  status: string;
  subject: string;
  body: string;
  channels: string[];
  channel_statuses: string[];
  llm_decision?: {
    channel: string;
    reasoning: string;
  } | null;
  created_at: string;
};

export function RecentNotifications({ clientId }: { clientId: string }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadNotifications = async () => {
      try {
        const data = await fetchJson<Notification[]>(`/api/client-dashboard/client/${clientId}/recent-notifications?limit=10`, {
          headers: { "X-Client-Id": clientId },
        });
        setNotifications(data);
      } catch (err) {
        console.error("Failed to load notifications", err);
      } finally {
        setLoading(false);
      }
    };
    loadNotifications();
  }, [clientId]);

  if (loading) return <p className="text-sm text-slate-500">Loading notifications...</p>;
  if (notifications.length === 0) return <p className="text-sm text-slate-500">No recent notifications</p>;

  const priorityColors: Record<string, string> = {
    critical: "border-rose-500",
    high: "border-orange-500",
    medium: "border-amber-500",
    low: "border-emerald-500",
  };

  return (
    <div className="space-y-4">
      {notifications.map((notif) => (
        <div
          key={notif.id}
          className={`rounded-2xl border-l-4 bg-white p-5 shadow-sm ${priorityColors[notif.priority] || "border-slate-200"}`}
        >
          <div className="mb-3 flex items-start justify-between">
            <div>
              <h4 className="font-bold text-slate-900">{notif.subject}</h4>
              <p className="mt-1 text-sm text-slate-500">{notif.body}</p>
            </div>
            <div className="text-right">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">{notif.priority}</span>
              <p className="mt-1 text-[10px] text-slate-400">{formatTimeAgo(notif.created_at)}</p>
            </div>
          </div>
          
          <div className="flex flex-wrap gap-2">
            {notif.channels.map((channel, i) => (
              <span key={i} className="rounded-full bg-indigo-50 px-3 py-1 text-[10px] font-bold uppercase tracking-tight text-indigo-600">
                {channel}
              </span>
            ))}
          </div>

          {notif.llm_decision && (
            <div className="mt-4 rounded-xl border-l-4 border-indigo-500 bg-indigo-50 p-4">
              <div className="mb-1 flex items-center gap-2">
                <span className="rounded bg-indigo-600 px-1.5 py-0.5 text-[10px] font-bold text-white">🤖 AI DECISION</span>
                <span className="text-xs font-bold text-indigo-700">Channel: {notif.llm_decision.channel}</span>
              </div>
              <p className="text-xs italic text-slate-600">{notif.llm_decision.reasoning}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
