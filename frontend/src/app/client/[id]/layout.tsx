"use client";

import { use } from "react";

export default function ClientLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id: clientId } = use(params);

  if (!clientId) return null;

  return <div className="min-h-screen bg-white text-slate-900 selection:bg-slate-900 selection:text-white">{children}</div>;
}
