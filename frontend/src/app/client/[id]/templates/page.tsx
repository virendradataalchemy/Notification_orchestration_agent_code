"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";
import { clientTemplateEditUrl, clientTemplateNewUrl } from "@/lib/client-routes";

type TemplateRecord = {
  id: string | number;
  client_id?: string | number | null;
  name: string;
  channel: string;
  language: string;
  subject?: string | null;
  body: string;
  version: number;
  active: boolean;
  is_global: boolean;
};

type TemplatesResponse = {
  client_id: string | number;
  client_name?: string;
  templates: TemplateRecord[];
};

export default function ClientTemplatesPage() {
  const params = useParams<{ id: string }>();
  const clientId = String(params.id);
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
  const [clientName, setClientName] = useState<string>("");
  const [channelFilter, setChannelFilter] = useState("");
  const [includeGlobal, setIncludeGlobal] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ include_global: String(includeGlobal) });
        if (channelFilter) params.set("channel", channelFilter);
        const data = await fetchJson<TemplatesResponse>(`/api/v1/client/templates?${params.toString()}`, {
          headers: { "X-Client-Id": clientId },
        });
        if (!active) return;
        setTemplates(data.templates || []);
        setClientName(data.client_name || `Client ${clientId}`);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load templates");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [channelFilter, clientId, includeGlobal]);

  const channels = useMemo(
    () => Array.from(new Set(templates.map((template) => template.channel))).sort(),
    [templates],
  );

  return (
    <ClientPortalShell
      clientId={clientId}
      title={clientName || `Client ${clientId} Templates`}
      description="Manage your notification templates from the frontend portal. Filter by channel, include platform templates, and create client-specific variations here."
      actions={
        <Link
          href={clientTemplateNewUrl(clientId)}
          className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:-translate-y-0.5"
        >
          Create Template
        </Link>
      }
    >
      <section className="mb-6 flex flex-wrap items-center gap-4 rounded-[28px] border border-slate-200 bg-white/80 p-5 shadow-sm">
        <label className="text-sm font-semibold text-slate-700">
          Channel
          <select
            value={channelFilter}
            onChange={(event) => setChannelFilter(event.target.value)}
            suppressHydrationWarning
            className="ml-3 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none"
          >
            <option value="">All Channels</option>
            {channels.map((channel) => (
              <option key={channel} value={channel}>
                {channel}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <input
            type="checkbox"
            checked={includeGlobal}
            onChange={(event) => setIncludeGlobal(event.target.checked)}
            suppressHydrationWarning
            className="h-4 w-4 rounded"
          />
          Include Global Templates
        </label>
      </section>

      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading templates...</p>
        </section>
      ) : error ? (
        <section className="rounded-[28px] border border-red-200 bg-red-50 p-6 shadow-sm">
          <p className="text-sm font-semibold text-red-700">{error}</p>
        </section>
      ) : templates.length === 0 ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-10 text-center shadow-sm">
          <p className="mb-2 text-lg font-bold text-slate-800">No templates yet</p>
          <p className="mb-5 text-sm text-slate-500">Create your first client template to get started.</p>
          <Link
            href={clientTemplateNewUrl(clientId)}
            className="inline-flex rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white"
          >
            Create Template
          </Link>
        </section>
      ) : (
        <div className="grid gap-5">
          {templates.map((template) => (
            <article key={String(template.id)} className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold tracking-tight text-slate-900">{template.name}</h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Badge>{template.channel}</Badge>
                    <Badge tone={template.is_global ? "amber" : "emerald"}>
                      {template.is_global ? "Global" : "Custom"}
                    </Badge>
                    <Badge>{template.language}</Badge>
                    <Badge>v{template.version}</Badge>
                  </div>
                </div>
                <div className="flex gap-3">
                  <Link
                    href={clientTemplateEditUrl(clientId, template.id)}
                    className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
                  >
                    Edit
                  </Link>
                </div>
              </div>
              {template.subject ? <p className="mb-3 text-sm font-semibold text-slate-700">Subject: {template.subject}</p> : null}
              <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                {template.body.slice(0, 240)}
                {template.body.length > 240 ? "..." : ""}
              </div>
            </article>
          ))}
        </div>
      )}
    </ClientPortalShell>
  );
}

function Badge({
  children,
  tone = "indigo",
}: {
  children: ReactNode;
  tone?: "indigo" | "emerald" | "amber";
}) {
  const toneMap = {
    indigo: "bg-indigo-50 text-indigo-700",
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
  } as const;

  return <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${toneMap[tone]}`}>{children}</span>;
}
