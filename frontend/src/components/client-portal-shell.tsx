"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { supabase } from "@/lib/supabase";

type ClientPortalShellProps = {
  clientId: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
};

const navItems = [
  { label: "Intelligent Portal", href: (id: string) => `/client/${id}` },
  { label: "Templates", href: (id: string) => `/client/${id}/templates` },
  { label: "Send Demo", href: (id: string) => `/client/${id}/send-demo` },
  { label: "Analytics", href: (id: string) => `/client/${id}/analytics` },
];

export function ClientPortalShell({
  clientId,
  title,
  description,
  actions,
  children,
}: ClientPortalShellProps) {
  const router = useRouter();

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-white text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white shadow-sm">
        <div className="flex w-full items-center justify-between gap-4 px-6 py-4 xl:px-10">
          <div className="flex items-center gap-6">
            <Link href={`/client/${clientId}`} className="text-lg font-bold tracking-tight text-slate-950">
              Client Portal
            </Link>
            <nav className="hidden flex-wrap gap-2 md:flex">
              {navItems.map((item) => (
                <Link
                  key={item.label}
                  href={item.href(clientId)}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <button
            onClick={handleSignOut}
            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
          >
            Sign Out
          </button>
        </div>
      </header>

      <main className="w-full px-6 py-8 xl:px-10">
        <section className="mb-6 rounded-[28px] border border-slate-200 bg-white px-7 py-7 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Client {clientId}</p>
              <h1 className="text-3xl font-bold tracking-tight text-slate-950">{title}</h1>
              {description ? <p className="mt-2 max-w-3xl text-sm text-slate-600">{description}</p> : null}
            </div>
            {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
          </div>
        </section>

        {children}
      </main>
    </div>
  );
}
