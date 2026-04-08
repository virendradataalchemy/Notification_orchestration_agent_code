"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clientPortalUrl } from "@/lib/client-routes";

export default function AdminDashboard() {
  const router = useRouter();
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchClients = async () => {
      try {
        const res = await fetch("/api/v1/clients/");
        if (res.ok) {
          const data = await res.json();
          setClients(data);
        }
      } catch (err) {
        console.error("Failed to load clients", err);
      } finally {
        setLoading(false);
      }
    };
    fetchClients();
  }, []);

  return (
    <div className="min-h-screen text-slate-900 pb-12 selection:bg-slate-900 selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3 text-slate-900">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            <span className="font-bold tracking-tight text-lg">System Dashboard</span>
          </div>
          <nav className="flex space-x-6 text-sm font-medium text-slate-500">
            <Link href="/" className="hover:text-slate-900 transition-colors">Portal Home</Link>
            <span className="text-slate-900 border-b-2 border-slate-900">Admin Authority</span>
            <button onClick={() => router.push("/")} className="hover:text-red-600 transition-colors">Sign Out</button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 mt-12">
        <div className="flex justify-between items-end mb-10">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 mb-2">Registered Clients</h1>
            <p className="text-slate-500 text-sm">Monitor and orchestrate all tenant organizations.</p>
          </div>
          <Link href="/signup" className="flex items-center gap-2 bg-slate-900 text-white px-5 py-2.5 text-sm font-medium hover:bg-slate-800 transition-colors shadow-sm">
            <span>+</span> New Client
          </Link>
        </div>

        {loading ? (
           <div className="flex flex-col items-center justify-center py-20 text-slate-400">
              <svg className="animate-spin h-8 w-8 mb-4 border-t-2 border-slate-900 rounded-full" viewBox="0 0 24 24"></svg>
              <p className="text-sm font-medium">Resolving Client Network...</p>
           </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {clients.map(client => {
              const isActive = client.status?.toLowerCase() === 'active';
              return (
                <div key={client.id} onClick={() => router.push(clientPortalUrl(client.id))} className="bg-white p-6 border border-slate-200 hover:border-slate-400 hover:shadow-md transition-all cursor-pointer group flex flex-col justify-between min-h-[220px]">
                  <div>
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-widest shadow-sm border border-slate-100 px-2 py-1 mb-3 inline-block">
                          ID: {client.id}
                        </span>
                        <h3 className="text-xl font-bold text-slate-900 tracking-tight leading-none group-hover:text-blue-600 transition-colors">
                          {client.name}
                        </h3>
                      </div>
                      <span className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider border ${isActive ? 'bg-emerald-100/50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
                        {client.status || 'ACTIVE'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-4 mt-8">
                      <div>
                        <p className="text-2xl font-semibold text-slate-900">{(client.notification_count || 0).toLocaleString()}</p>
                        <p className="text-xs text-slate-500 uppercase tracking-wider font-medium">Outbound</p>
                      </div>
                      <div>
                        <p className="text-2xl font-semibold text-slate-900">{client.provider_configs || 0}</p>
                        <p className="text-xs text-slate-500 uppercase tracking-wider font-medium">Providers</p>
                      </div>
                    </div>
                  </div>
                  <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="text-xs text-slate-500 font-medium">Manage Integrations</span>
                    <span className="text-slate-900 font-bold">&rarr;</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
