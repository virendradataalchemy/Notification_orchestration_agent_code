"use client";

export default function ClientsSlugLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="min-h-screen bg-white text-slate-900 selection:bg-slate-900 selection:text-white">{children}</div>;
}
