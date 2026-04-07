"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { use } from "react";

export default function ClientLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const pathname = usePathname();
  const { id: clientId } = use(params);

  if (!clientId) return null;

  const isAnalytics = pathname.includes("analytics");

  return (
    <div className="min-h-screen text-slate-900 pb-12 selection:bg-slate-900 selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3 text-slate-900">
             <Link href="/" className="text-sm font-semibold text-slate-500 hover:text-slate-900 uppercase tracking-widest transition-colors flex items-center gap-2">
                &larr; Switch Client
            </Link>
          </div>
          <nav className="flex space-x-6 text-sm font-medium text-slate-500">
            <Link 
              href={`/client/${clientId}`} 
              className={`pb-1 ${!isAnalytics ? 'text-slate-900 border-b-2 border-slate-900 font-semibold' : 'hover:text-slate-900 transition-colors'}`}
            >
              Intelligent Portal
            </Link>
            <Link 
              href={`/client/${clientId}/analytics`} 
              className={`pb-1 ${isAnalytics ? 'text-slate-900 border-b-2 border-slate-900 font-semibold' : 'hover:text-slate-900 transition-colors'}`}
            >
              Analytics
            </Link>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 mt-12 space-y-12">
        {children}
      </main>
    </div>
  );
}
