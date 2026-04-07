"use client";

import { useState, useEffect, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function UnifiedClientDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  // Overview / Analytics State
  const [data, setData] = useState<any>(null);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [activeChannel, setActiveChannel] = useState<string>("");
  const [loadingOverview, setLoadingOverview] = useState(true);

  // Notification Trigger State
  const [contactInput, setContactInput] = useState("");
  const [channelSelect, setChannelSelect] = useState("");
  const [typeInput, setTypeInput] = useState("notification");
  const [prioritySelect, setPrioritySelect] = useState("medium");
  const [subjectInput, setSubjectInput] = useState("");
  const [bodyInput, setBodyInput] = useState("");
  const [sending, setSending] = useState(false);
  const [alertInfo, setAlertInfo] = useState<{type: 'success'|'error', msg: string} | null>(null);

  // Fetch Analytics & Logs Data
  const fetchOverview = async () => {
    try {
      const res = await fetch(`/api/client-dashboard/client/${id}/overview`);
      if (res.ok) {
        const overview = await res.json();
        setData(overview);
        if (!activeChannel && overview.channels?.length > 0) {
          handleLoadNotifications(overview.channels[0].channel);
        } else if (activeChannel) {
          handleLoadNotifications(activeChannel); // refresh active tab
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingOverview(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 30000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, activeChannel]);

  const handleLoadNotifications = async (channel: string) => {
    setActiveChannel(channel);
    try {
      const res = await fetch(`/api/client-dashboard/client/${id}/channel/${channel}`);
      if (res.ok) {
        const historyData = await res.json();
        setNotifications(historyData.notifications || []);
      }
    } catch {}
  };

  // Submit Notification form using exact legacy payload format
  const handleSendNotification = async (e: React.FormEvent) => {
    e.preventDefault();
    setSending(true);
    setAlertInfo(null);

    const isEmail = contactInput.includes('@');
    
    // As per legacy dashboard.html
    const payload = {
        recipient: {
            user_id: isEmail ? 0 : parseInt(contactInput) || 0,
            email: isEmail ? contactInput : '',
            phone: ''
        },
        notification: {
            type: typeInput,
            priority: prioritySelect,
            channels: [channelSelect],
            subject: subjectInput,
            body: bodyInput,
            data: {}
        }
    };

    try {
      const response = await fetch("/api/v1/notifications/send", {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json',
              'X-Tenant-ID': id,
              'X-Client-Id': id // Passing both to ensure compatibility
          },
          body: JSON.stringify(payload)
      });

      if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to send notification');
      }

      const result = await response.json();
      setAlertInfo({ type: 'success', msg: `Notification sent successfully! ID: ${result.notification_id}` });
      
      // Auto refresh ledger
      fetchOverview();

      // Clear specific form inputs
      setContactInput("");
      setSubjectInput("");
      setBodyInput("");

      // auto clear success message
      setTimeout(() => setAlertInfo(null), 5000);
    } catch (error: any) {
      setAlertInfo({ type: 'error', msg: `Error: ${error.message}` });
    } finally {
      setSending(false);
    }
  };

  const formatTimeAgo = (dateStr: string) => {
    if (!dateStr) return 'N/A';
    const s = Math.floor((new Date().getTime() - new Date(dateStr).getTime()) / 1000);
    if (s < 60) return '< 1m';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  };

  if (loadingOverview || !data) {
    return <div className="flex justify-center items-center h-[50vh]"><svg className="animate-spin h-6 w-6 border-2 border-indigo-600 border-t-transparent rounded-full"></svg></div>;
  }

  const totalNotifications = data.channels.reduce((s: number, c: any) => s + c.total, 0);
  const totalDelivered = data.channels.reduce((s: number, c: any) => s + (c.sent + c.delivered), 0);
  const totalFailed = data.channels.reduce((s: number, c: any) => s + c.failed, 0);

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-12">
      {/* Navigation Bar */}
      <nav className="bg-white border-b border-slate-100 flex items-center justify-between px-8 py-4 sticky top-0 z-50 shadow-sm rounded-b-lg">
          <div className="flex items-center space-x-8">
              <Link href="/" className="font-bold text-indigo-600">✦ Orchestrator</Link>
              <div className="flex space-x-6 text-sm font-bold text-slate-500">
                  <a href="#orchestration" className="hover:text-indigo-600 transition-colors">Intelligent Orchestration</a>
                  <a href="#analytics" className="hover:text-indigo-600 transition-colors">Analytics</a>
              </div>
          </div>
          <button onClick={async () => { await supabase.auth.signOut(); router.push('/login'); }} className="text-xs font-bold text-slate-400 hover:text-red-500 transition-colors">
              Sign Out
          </button>
      </nav>

      {/* Header matching dashboard.html */}
      <div className="bg-white p-8 rounded-lg shadow-sm border border-slate-100 flex justify-between items-center">
         <div>
            <h1 className="text-3xl font-extrabold text-slate-900 mb-2 tracking-tight">Notification Orchestration Dashboard</h1>
            <p className="text-slate-500 font-medium text-sm">Send and track notifications across all channels • Client: {data.client_name}</p>
         </div>
         <span className="border border-indigo-200 bg-indigo-50 text-indigo-700 px-3 py-1.5 text-xs font-bold uppercase tracking-widest rounded-md mt-4 md:mt-0">{data.tier} TIER</span>
      </div>

      {alertInfo && (
        <div className={`p-4 rounded-md border flex items-center justify-between text-sm font-bold ${alertInfo.type === 'success' ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-red-50 text-red-800 border-red-200'}`}>
           <div className="flex items-center space-x-2">
             <span className="text-lg">{alertInfo.type === 'success' ? '✓' : '✕'}</span>
             <span>{alertInfo.msg}</span>
           </div>
           {alertInfo.type === 'error' && <button onClick={() => setAlertInfo(null)} className="opacity-50 hover:opacity-100">×</button>}
        </div>
      )}

      {/* Main Grid: Form Left, Stats Right */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
         
         {/* Send Notification Card (takes 2 cols on xl) */}
         <div id="orchestration" className="xl:col-span-2 bg-gradient-to-br from-indigo-600 to-purple-700 rounded-xl p-8 shadow-md text-white relative overflow-hidden">
             <div className="absolute top-0 right-0 -mr-20 -mt-20 w-80 h-80 rounded-full bg-white opacity-5 blur-3xl"></div>
             
             <h2 className="text-sm font-bold uppercase tracking-widest text-indigo-100 mb-6 border-b border-indigo-400/30 pb-3">Send Notification</h2>
             
             <form onSubmit={handleSendNotification} className="space-y-5 relative z-10">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                   <div>
                      <label className="block text-xs font-semibold text-indigo-100 mb-2">Contact ID or Email</label>
                      <input type="text" required value={contactInput} onChange={e => setContactInput(e.target.value)} className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-md focus:outline-none focus:border-white text-sm text-white placeholder-indigo-200/50" placeholder="e.g., 9 or email@example.com" />
                   </div>
                   <div>
                      <label className="block text-xs font-semibold text-indigo-100 mb-2">Channel</label>
                      <select required value={channelSelect} onChange={e => setChannelSelect(e.target.value)} className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-md focus:outline-none focus:border-white text-sm text-white [&>option]:text-slate-900">
                          <option value="">Select Channel...</option>
                          <option value="email">📧 Email</option>
                          <option value="sms">💬 SMS</option>
                          <option value="whatsapp">💚 WhatsApp</option>
                          <option value="push">🔔 Push</option>
                          <option value="inapp">📱 In-App</option>
                          <option value="voice">☎️ Voice Call</option>
                      </select>
                   </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                   <div>
                      <label className="block text-xs font-semibold text-indigo-100 mb-2">Type</label>
                      <input type="text" required value={typeInput} onChange={e => setTypeInput(e.target.value)} className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-md focus:outline-none focus:border-white text-sm text-white placeholder-indigo-200/50" placeholder="notification, alert, info..." />
                   </div>
                   <div>
                      <label className="block text-xs font-semibold text-indigo-100 mb-2">Priority</label>
                      <select required value={prioritySelect} onChange={e => setPrioritySelect(e.target.value)} className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-md focus:outline-none focus:border-white text-sm text-white [&>option]:text-slate-900">
                          <option value="low">Low</option>
                          <option value="medium">Medium</option>
                          <option value="high">High</option>
                          <option value="critical">Critical</option>
                      </select>
                   </div>
                </div>

                <div>
                   <label className="block text-xs font-semibold text-indigo-100 mb-2">Subject (Optional)</label>
                   <input type="text" value={subjectInput} onChange={e => setSubjectInput(e.target.value)} className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-md focus:outline-none focus:border-white text-sm text-white placeholder-indigo-200/50" placeholder="Notification subject..." />
                </div>

                <div>
                   <label className="block text-xs font-semibold text-indigo-100 mb-2">Message</label>
                   <textarea required rows={3} value={bodyInput} onChange={e => setBodyInput(e.target.value)} className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-md focus:outline-none focus:border-white text-sm text-white placeholder-indigo-200/50 resize-y" placeholder="Enter your notification message..."></textarea>
                </div>

                <div className="flex flex-col sm:flex-row gap-3 pt-2">
                   <button type="submit" disabled={sending} className="flex-1 bg-white text-indigo-700 font-bold text-sm py-3 px-6 rounded-md shadow-sm hover:bg-slate-50 transition-colors disabled:opacity-75 flex justify-center items-center h-12">
                      {sending ? 'Sending...' : '✈️ Send Notification'}
                   </button>
                   <button type="button" onClick={() => {setContactInput("");setSubjectInput("");setBodyInput("");}} className="bg-white/10 text-white font-bold text-sm py-3 px-6 rounded-md hover:bg-white/20 border border-white/20 transition-colors">
                      Clear
                   </button>
                </div>
             </form>
         </div>

         {/* Stats Cards (takes 1 col on xl) */}
         <div id="analytics" className="xl:col-span-1 flex flex-col gap-5">
             <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 hover:-translate-y-1 transition-transform">
                 <h3 className="text-xs font-bold uppercase tracking-widest text-indigo-600 mb-3">Total Sent</h3>
                 <p className="text-4xl font-extrabold text-slate-900 mb-1">{totalNotifications.toLocaleString()}</p>
                 <span className="text-xs font-medium text-slate-400">Last 24 hours</span>
             </div>
             
             <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 hover:-translate-y-1 transition-transform">
                 <h3 className="text-xs font-bold uppercase tracking-widest text-emerald-600 mb-3">Delivered</h3>
                 <p className="text-4xl font-extrabold text-slate-900 mb-1">{totalDelivered.toLocaleString()}</p>
                 <span className="text-xs font-medium text-slate-400">Success rate metric</span>
             </div>

             <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 hover:-translate-y-1 transition-transform">
                 <h3 className="text-xs font-bold uppercase tracking-widest text-red-500 mb-3">Failed</h3>
                 <p className="text-4xl font-extrabold text-slate-900 mb-1">{totalFailed.toLocaleString()}</p>
                 <span className="text-xs font-medium text-slate-400">Requires review</span>
             </div>
         </div>

      </div>

      {/* Logs Section */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
         <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
             <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">📋 Recent Notifications</h2>
             <button onClick={fetchOverview} className="text-xs font-bold bg-white border border-slate-200 text-slate-600 px-4 py-2 hover:bg-slate-50 rounded-md shadow-sm transition-colors cursor-pointer">
                🔄 Refresh
             </button>
         </div>
         
         {/* Inter-active channel tabs above table */}
         {data.channels && data.channels.length > 0 && (
           <div className="flex border-b border-slate-100 px-6 pt-4 space-x-6 overflow-x-auto">
             {data.channels.map((ch: any) => (
                <button 
                   key={ch.channel} 
                   onClick={() => handleLoadNotifications(ch.channel)}
                   className={`pb-3 text-sm font-bold uppercase tracking-wider whitespace-nowrap transition-colors flex items-center gap-2 ${activeChannel === ch.channel ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-400 hover:text-slate-600'}`}
                >
                   {ch.channel}
                   <span className="bg-slate-100 text-slate-500 text-[10px] px-2 py-0.5 rounded-full">{ch.total}</span>
                </button>
             ))}
           </div>
         )}
         
         <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
                <thead>
                    <tr className="bg-white border-b border-slate-100">
                        <th className="py-4 px-6 text-[11px] font-bold uppercase tracking-widest text-slate-500">ID</th>
                        <th className="py-4 px-6 text-[11px] font-bold uppercase tracking-widest text-slate-500">Channel</th>
                        <th className="py-4 px-6 text-[11px] font-bold uppercase tracking-widest text-slate-500">Status</th>
                        <th className="py-4 px-6 text-[11px] font-bold uppercase tracking-widest text-slate-500">Recipient</th>
                        <th className="py-4 px-6 text-[11px] font-bold uppercase tracking-widest text-slate-500">Sent Time</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-sm">
                    {notifications.length === 0 ? (
                       <tr>
                          <td colSpan={5} className="py-12 text-center text-slate-400 font-medium">No recent notifications executed on this channel.</td>
                       </tr>
                    ) : (
                       notifications.slice(0, 15).map((log, idx) => {
                          const st = log.status?.toLowerCase() || '';
                          const sc = (st==='delivered'||st==='sent') ? 'bg-emerald-100 text-emerald-800' : (st==='failed' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800');
                          const cc = log.channel === 'email' ? 'bg-indigo-50 text-indigo-700' : log.channel === 'sms' ? 'bg-orange-50 text-orange-700' : 'bg-slate-100 text-slate-700';

                          return (
                            <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                                <td className="py-4 px-6 font-mono text-slate-500 text-xs">#{log.id || '...'}</td>
                                <td className="py-4 px-6">
                                    <span className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider rounded-full ${cc}`}>{log.channel}</span>
                                </td>
                                <td className="py-4 px-6">
                                    <span className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider rounded-full ${sc}`}>{log.status}</span>
                                </td>
                                <td className="py-4 px-6 font-medium text-slate-800">{log.recipient}</td>
                                <td className="py-4 px-6 text-slate-500 text-xs">{formatTimeAgo(log.created_at)}</td>
                            </tr>
                          );
                       })
                    )}
                </tbody>
            </table>
         </div>
      </div>

    </div>
  );
}
