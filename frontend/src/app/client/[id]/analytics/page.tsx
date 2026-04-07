"use client";

import { useEffect, useState, use } from "react";

export default function ClientAnalytics({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<any>(null);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [activeChannel, setActiveChannel] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchOverview = async () => {
      try {
        const res = await fetch(`/api/client-dashboard/client/${id}/overview`);
        if (res.ok) {
          const overview = await res.json();
          setData(overview);
          if (overview.channels?.length > 0) {
            handleLoadNotifications(overview.channels[0].channel);
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchOverview();
    
    // Refresh every 30s
    const interval = setInterval(fetchOverview, 30000);
    return () => clearInterval(interval);
  }, [id]);

  const handleLoadNotifications = async (channel: string) => {
    setActiveChannel(channel);
    try {
      const res = await fetch(`/api/client-dashboard/client/${id}/channel/${channel}`);
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.notifications || []);
      }
    } catch {}
  };

  const formatTimeAgo = (dateStr: string) => {
    if (!dateStr) return 'N/A';
    const s = Math.floor((new Date().getTime() - new Date(dateStr).getTime()) / 1000);
    if (s < 60) return '< 1m';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  };

  if (loading || !data) {
    return <div className="flex justify-center py-20"><svg className="animate-spin h-6 w-6 border-2 border-slate-900 border-t-transparent rounded-full"></svg></div>;
  }

  const totalNotifications = data.channels.reduce((s: number, c: any) => s + c.total, 0);
  const totalSuccess = data.channels.reduce((s: number, c: any) => s + (c.sent + c.delivered), 0);
  const totalFailed = data.channels.reduce((s: number, c: any) => s + c.failed, 0);
  const avgSuccessRate = data.channels.length > 0 ? Math.round(data.channels.reduce((s: number, c: any) => s + c.success_rate, 0) / data.channels.length) : 0;

  return (
    <>
      <div>
        <div className="flex justify-between flex-col md:flex-row md:items-end mb-4">
          <div>
            <span className="text-xs font-bold font-mono text-slate-400 uppercase tracking-widest bg-slate-100 px-2.5 py-1 mb-4 inline-block">Analytics • ID: {id}</span>
            <h1 className="text-4xl font-bold tracking-tight text-slate-900 leading-none">{data.client_name}</h1>
          </div>
          <span className="border border-slate-200 px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-slate-500 mt-4 md:mt-0">{data.tier} TIER</span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-0 border border-slate-200 bg-white">
        <StatBlock label="Transmissions" value={totalNotifications.toLocaleString()} />
        <StatBlock label="Endpoints" value={data.channels.length} />
        <StatBlock label="Delivered" value={totalSuccess.toLocaleString()} extraClass="text-emerald-700 bg-emerald-50/30" />
        <StatBlock label="Dropped" value={totalFailed.toLocaleString()} extraClass="text-red-700 bg-red-50/30" />
        <StatBlock label="Reliability" value={`${avgSuccessRate}%`} />
      </div>

      <div>
        <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400 mb-4 border-b border-slate-200 pb-2">Active Channels</h2>
        <div className="space-y-4">
          {data.channels.map((ch: any) => {
            const isSel = ch.channel === activeChannel;
            const bC = ch.success_rate >= 80 ? 'bg-emerald-500' : ch.success_rate >= 50 ? 'bg-amber-500' : 'bg-red-500';
            return (
              <div key={ch.channel} onClick={() => handleLoadNotifications(ch.channel)} className={`bg-white border p-5 flex items-center justify-between cursor-pointer transition-all ${isSel ? 'border-slate-800 shadow-sm' : 'border-slate-200 hover:border-slate-400'}`}>
                <div className="w-1/4">
                    <span className="text-sm font-bold uppercase tracking-wider text-slate-800">{ch.channel}</span>
                </div>
                <div className="w-1/2 flex items-center space-x-6">
                    <div className="w-full bg-slate-100 h-1.5 flex-grow relative overflow-hidden">
                        <div className={`${bC} h-full`} style={{width: `${ch.success_rate}%`}}></div>
                    </div>
                    <span className="text-sm font-mono font-medium text-slate-600 w-12 text-right">{ch.success_rate}%</span>
                </div>
                <div className="w-1/4 flex justify-end space-x-6 text-sm font-medium">
                    <span className="text-slate-400 uppercase text-xs tracking-wider">Total <span className="text-slate-900 text-sm ml-1">{ch.total}</span></span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400 mb-4 border-b border-slate-200 pb-2">Transmission Ledger: {activeChannel.toUpperCase()}</h2>
        <div className="bg-white border border-slate-200 overflow-x-auto">
          {notifications.length === 0 ? (
             <div className="p-8 text-center text-slate-400 text-sm font-medium">No ledger entries found.</div>
          ) : (
            <table className="w-full text-left border-collapse">
                <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                        <th className="py-3 px-6 text-xs font-semibold uppercase tracking-widest text-slate-400">Payload Type</th>
                        <th className="py-3 px-6 text-xs font-semibold uppercase tracking-widest text-slate-400">Target</th>
                        <th className="py-3 px-6 text-xs font-semibold uppercase tracking-widest text-slate-400">State</th>
                        <th className="py-3 px-6 text-xs font-semibold uppercase tracking-widest text-slate-400">Priority</th>
                        <th className="py-3 px-6 text-xs font-semibold uppercase tracking-widest text-slate-400">Clock</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {notifications.slice(0, 15).map((n, i) => {
                        const st = n.status.toLowerCase();
                        const sc = (st==='delivered'||st==='sent') ? 'bg-emerald-100/50 text-emerald-700 border-emerald-200' : (st==='failed' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-slate-100 text-slate-600 border-slate-200');
                        const pc = (n.priority.toLowerCase()==='critical'||n.priority.toLowerCase()==='high') ? 'text-red-600 font-bold' : 'text-slate-600';
                        return (
                          <tr key={i} className="hover:bg-slate-50/50 transition-colors group">
                              <td className="py-3 px-6 text-sm font-medium text-slate-800">{n.type}</td>
                              <td className="py-3 px-6 text-xs font-mono text-slate-500">{n.recipient}</td>
                              <td className="py-3 px-6"><span className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest border ${sc}`}>{n.status}</span></td>
                              <td className={`py-3 px-6 text-xs uppercase tracking-wider ${pc}`}>{n.priority}</td>
                              <td className="py-3 px-6 text-xs text-slate-400">{formatTimeAgo(n.created_at)}</td>
                          </tr>
                        );
                    })}
                </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

const StatBlock = ({label, value, extraClass=""}: any) => (
  <div className={`p-6 border-b md:border-b-0 md:border-r border-slate-200 last:border-r-0 ${extraClass}`}>
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">{label}</p>
      <p className="text-3xl font-bold tracking-tight text-slate-900">{value}</p>
  </div>
);
