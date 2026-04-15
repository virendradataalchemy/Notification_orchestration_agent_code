import { useEffect, useMemo, useState } from "react";
import { useParams, useOutletContext } from "react-router-dom";
import type { ReactNode } from "react";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";

type DemoOptions = {
  candidates: Array<{
    id: number;
    name: string;
    email?: string | null;
    phone?: string | null;
    whatsapp_number?: string | null;
  }>;
  templates: Array<{
    id: number;
    name: string;
    channel: string;
    notification_type?: string | null;
  }>;
  channels: Array<{ id: number; name: string }>;
};

type HistoryItem = {
  id: number | string;
  type?: string;
  channel?: string;
  recipient?: string;
  status: string;
  created_at?: string;
  candidate_name?: string;
  template_name?: string;
};

type ClientSendDemoPageProps = {
  clientIdProp?: string;
  clientPathProp?: string;
  initialClientName?: string;
};

const inputClassName =
  "w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500";

export default function SendDemoPage({
  clientIdProp,
  clientPathProp,
  initialClientName = "",
}: ClientSendDemoPageProps = {}) {
  const params = useParams<{ id: string }>();
  const context = useOutletContext<{ resolved: { id: string; name: string; slug: string | null } } | null>();
  
  const clientId = clientIdProp || context?.resolved?.id || String(params.id);
  const clientPath = clientPathProp || context?.resolved?.slug || context?.resolved?.id || clientId;
  const initialName = initialClientName || context?.resolved?.name || "";
  const [options, setOptions] = useState<DemoOptions | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [candidateId, setCandidateId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [notificationType, setNotificationType] = useState("");
  const [priority, setPriority] = useState("medium");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [dataInput, setDataInput] = useState(`{
  "name": "Demo User",
  "company": "Data Alchemy",
  "month": "March"
}`);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [demoOptions, recentHistory] = await Promise.all([
          fetchJson<DemoOptions>("/api/v1/notifications/demo/options", {
            headers: { "X-Client-Id": clientId },
          }),
          fetchJson<HistoryItem[]>("/api/v1/notifications/history?limit=12", {
            headers: { "X-Client-Id": clientId },
          }),
        ]);
        if (!active) return;
        setOptions(demoOptions);
        setHistory(recentHistory);
        if (demoOptions.candidates[0]) setCandidateId(String(demoOptions.candidates[0].id));
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load demo data");
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [clientId]);

  const templateMap = useMemo(() => {
    const map = new Map<number, DemoOptions["templates"][number]>();
    options?.templates.forEach((template) => map.set(template.id, template));
    return map;
  }, [options]);

  const toggleChannel = (channel: string) => {
    setSelectedChannels((current) =>
      current.includes(channel) ? current.filter((item) => item !== channel) : [...current, channel],
    );
  };

  const sendDemo = async () => {
    setError(null);
    setResult(null);

    let parsedData: Record<string, unknown> = {};
    try {
      parsedData = JSON.parse(dataInput || "{}");
    } catch {
      setError("Template Data JSON is invalid.");
      return;
    }

    try {
      const response = await fetchJson<{
        deduplicated?: boolean;
        notification_type?: string;
        candidate_name?: string;
        channels?: Array<{ channel: string; provider: string; status: string; message_id?: string; error?: string }>;
      }>("/api/v1/notifications/demo/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Client-Id": clientId,
        },
        body: JSON.stringify({
          candidate_id: Number(candidateId),
          template_id: templateId ? Number(templateId) : null,
          notification_type: notificationType || null,
          priority,
          channels: selectedChannels,
          subject: subject || null,
          body: body || null,
          data: parsedData,
        }),
      });

      setResult(
        [
          response.deduplicated ? "Duplicate prevented" : "Notification processed",
          response.notification_type ? `Type: ${response.notification_type}` : null,
          response.candidate_name ? `Recipient: ${response.candidate_name}` : null,
          ...(response.channels || []).map(
            (channel) => `${channel.channel} via ${channel.provider}: ${channel.status}${channel.message_id ? ` (${channel.message_id})` : ""}`,
          ),
        ]
          .filter(Boolean)
          .join("\n"),
      );

      const recentHistory = await fetchJson<HistoryItem[]>("/api/v1/notifications/history?limit=12", {
        headers: { "X-Client-Id": clientId },
      });
      setHistory(recentHistory);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send demo notification");
    }
  };

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPathProp || clientId}
      title={initialClientName ? `${initialClientName} Demo` : "Interactive Channel Demo"}
      description="Send frontend-powered demo notifications using the same backend APIs as the legacy portal, but with a dedicated experience."
    >
      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <div className="space-y-5">
            <Field label="Candidate">
              <select value={candidateId} onChange={(event) => setCandidateId(event.target.value)} className={inputClassName}>
                {(options?.candidates || []).map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name} | {candidate.email || candidate.phone || candidate.whatsapp_number || "No recipient"}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Template">
              <select
                value={templateId}
                onChange={(event) => {
                  const nextTemplateId = event.target.value;
                  setTemplateId(nextTemplateId);
                  const template = templateMap.get(Number(nextTemplateId));
                  if (template?.notification_type) setNotificationType(template.notification_type);
                }}
                className={inputClassName}
              >
                <option value="">Auto Select</option>
                {(options?.templates || []).map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name} | {template.channel}
                  </option>
                ))}
              </select>
            </Field>

            <div className="grid gap-5 md:grid-cols-2">
              <Field label="Notification Type">
                <input value={notificationType} onChange={(event) => setNotificationType(event.target.value)} className={inputClassName} />
              </Field>
              <Field label="Priority">
                <select value={priority} onChange={(event) => setPriority(event.target.value)} className={inputClassName}>
                  {["low", "medium", "high", "critical"].map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <Field label="Channels">
              <div className="flex flex-wrap gap-2">
                {(options?.channels || []).map((channel) => (
                  <button
                    key={channel.id}
                    onClick={() => toggleChannel(channel.name)}
                    className={`rounded-full px-3 py-2 text-xs font-bold uppercase tracking-wide ${
                      selectedChannels.includes(channel.name)
                        ? "bg-indigo-600 text-white"
                        : "border border-slate-300 bg-white text-slate-700"
                    }`}
                  >
                    {channel.name}
                  </button>
                ))}
              </div>
            </Field>

            <Field label="Subject Override">
              <input value={subject} onChange={(event) => setSubject(event.target.value)} className={inputClassName} />
            </Field>

            <Field label="Body Override">
              <textarea value={body} onChange={(event) => setBody(event.target.value)} className={`${inputClassName} min-h-36`} />
            </Field>

            <Field label="Template Data JSON">
              <textarea value={dataInput} onChange={(event) => setDataInput(event.target.value)} className={`${inputClassName} min-h-44 font-mono`} />
            </Field>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={sendDemo}
                className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white transition hover:-translate-y-0.5"
              >
                Send Notification
              </button>
              <button
                onClick={() => {
                  setSelectedChannels([]);
                  setSubject("");
                  setBody("");
                  setResult(null);
                  setError(null);
                }}
                className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
              >
                Clear
              </button>
            </div>

            {result ? <pre className="rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-800 whitespace-pre-wrap">{result}</pre> : null}
            {error ? <p className="text-sm font-semibold text-red-700">{error}</p> : null}
          </div>
        </section>

        <section className="space-y-5">
          <div className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
            <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-slate-400">Recent History</p>
            <div className="space-y-3">
              {history.length === 0 ? (
                <p className="text-sm text-slate-500">No notifications yet.</p>
              ) : (
                history.map((item) => (
                  <article key={String(item.id)} className="rounded-2xl bg-slate-50 p-4">
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <p className="text-sm font-bold text-slate-800">{item.type || "notification"}</p>
                      <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-bold uppercase text-white">
                        {item.status}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600">
                      {item.channel || "channel"} | {item.recipient || item.candidate_name || "recipient"}
                    </p>
                    <p className="text-xs text-slate-400">{item.template_name || "No template linked"}</p>
                  </article>
                ))
              )}
            </div>
          </div>
        </section>
      </div>
    </ClientPortalShell>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">{label}</span>
      {children}
    </label>
  );
}
