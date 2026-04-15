import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useOutletContext } from "react-router-dom";
import type { ReactNode } from "react";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson, formatTimeAgo } from "@/lib/client-portal";
import { clientTemplateNewUrl, clientTemplateEditUrl } from "@/lib/client-routes";

type DepartmentKey = "hr" | "it";
type Tab = "dashboard" | "portal" | "templates";

type DepartmentTemplate = {
  id: number;
  name?: string;
  notification_type?: string;
  category?: string | null;
  channel?: string;
  subject?: string | null;
  content?: string | null;
};

type DepartmentMail = {
  communication_id: number;
  mail_type?: string | null;
  template_id?: number | null;
  template_name?: string | null;
  template_category?: string | null;
  channel: string;
  status: string;
  direction: "sent" | "received";
  recipient: string;
  subject?: string | null;
  body?: string | null;
  created_at?: string | null;
  opened_at?: string | null;
};

type DepartmentStats = {
  total: number; sent: number; received: number;
  opened: number; failed: number; in_progress: number;
};

type DepartmentCard = {
  department: DepartmentKey;
  label: string;
  role_emails: string[];
  metrics: DepartmentStats;
  templates: DepartmentTemplate[];
  recent_mails: DepartmentMail[];
};

type DepartmentDetailResponse = {
  client_id: number;
  client_name?: string;
  generated_at?: string;
  department?: DepartmentCard;
  error?: string;
};

type ClientDepartmentDetailPageProps = {
  clientIdProp?: string;
  clientPathProp?: string;
  initialClientName?: string;
  departmentProp?: string;
};

export default function DepartmentDetailPage({
  clientIdProp,
  clientPathProp,
  initialClientName = "",
  departmentProp,
}: ClientDepartmentDetailPageProps = {}) {
  const params = useParams<{ id: string; department: string }>();
  const context = useOutletContext<{ resolved: { id: string; name: string; slug: string | null } } | null>();
  
  const clientId = clientIdProp || context?.resolved?.id || String(params.id);
  const clientPath = clientPathProp || context?.resolved?.slug || context?.resolved?.id || clientId;
  const initialName = initialClientName || context?.resolved?.name || "";
  const departmentKey = (departmentProp || params.department || "").toLowerCase() as DepartmentKey;

  const [payload, setPayload] = useState<DepartmentDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [selectedMail, setSelectedMail] = useState<DepartmentMail | null>(null);

  // Portal tab state
  const [fromEmail, setFromEmail] = useState("");
  const [toEmail, setToEmail] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchJson<DepartmentDetailResponse>(
          `/api/client-dashboard/client/${clientId}/departments/${departmentKey}?limit=40`,
          undefined,
          5 * 60 * 1000,
        );
        if (!active) return;
        if (data.error) { setError(data.error); setPayload(null); return; }
        setPayload(data);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [clientId, departmentKey]);

  const department = payload?.department;

  // Pre-fill "From" with department's own role email from DB
  useEffect(() => {
    if (!department) return;
    if (!fromEmail && department.role_emails.length) {
      setFromEmail(department.role_emails[0]);
    }
  }, [department, fromEmail]);

  const emailTemplates = useMemo(
    () => (department?.templates || []).filter((t) => (t.channel || "").toLowerCase() === "email"),
    [department],
  );

  const receivedMails = useMemo(
    () => (department?.recent_mails || []).filter((m) => m.direction === "received"),
    [department],
  );

  const sentMails = useMemo(
    () => (department?.recent_mails || []).filter((m) => m.direction === "sent"),
    [department],
  );

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId);
    if (!templateId) { setComposeSubject(""); setComposeBody(""); return; }
    const selected = emailTemplates.find((t) => String(t.id) === templateId);
    if (!selected) return;
    setComposeSubject(selected.subject || "");
    setComposeBody(selected.content || "");
  };

  const handleSendEmail = async () => {
    setSendError(null);
    setSendResult(null);
    if (!toEmail.trim()) { setSendError("Mail To is required."); return; }
    if (!composeBody.trim()) { setSendError("Body is required."); return; }
    setSending(true);
    try {
      const response = await fetchJson<{ status: string; to_email: string; from_email: string }>(
        `/api/client-dashboard/client/${clientId}/departments/${departmentKey}/send-email`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            to_email: toEmail,
            from_email: fromEmail,
            template_id: selectedTemplateId ? Number(selectedTemplateId) : null,
            subject: composeSubject,
            body: composeBody,
            priority: "high",
          }),
        },
      );
      setSendResult(`Queued for delivery to ${response.to_email}`);
      const refreshed = await fetchJson<DepartmentDetailResponse>(
        `/api/client-dashboard/client/${clientId}/departments/${departmentKey}?limit=40`,
      );
      setPayload(refreshed.error ? payload : refreshed);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Failed to send");
    } finally {
      setSending(false);
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "dashboard", label: "Dashboard" },
    { key: "portal", label: "Intelligent Portal" },
    { key: "templates", label: "Templates" },
  ];

  const deptLabel = department?.label || departmentKey.toUpperCase();

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPath}
      title={`${deptLabel} Department`}
      description={`${payload?.client_name || initialClientName} — ${deptLabel} internal workspace`}
    >
      <div className="mb-6 flex gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`rounded-full px-4 py-1.5 text-xs font-semibold transition ${
              activeTab === tab.key
                ? "bg-slate-900 text-white"
                : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading...</p>
        </section>
      ) : error || !department ? (
        <section className="rounded-[28px] border border-red-200 bg-red-50 p-6 shadow-sm">
          <p className="text-sm font-semibold text-red-700">{error || "Department not found"}</p>
        </section>
      ) : (
        <>
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
                <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">KPIs</p>
                <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                  <Metric label="Sent" value={department.metrics.sent} />
                  <Metric label="Received" value={department.metrics.received} />
                  <Metric label="Opened" value={department.metrics.opened} />
                  <Metric label="In Progress" value={department.metrics.in_progress} />
                  <Metric label="Failed" value={department.metrics.failed} tone="danger" />
                  <Metric label="Templates" value={department.templates.length} />
                </div>
              </section>

              <section className="rounded-[28px] border border-slate-200 bg-white/80 shadow-sm overflow-hidden mt-6">
                <div className="border-b border-slate-200 px-6 py-5">
                  <p className="text-sm font-bold uppercase tracking-[0.2em] text-slate-400">Received Emails</p>
                </div>
                {receivedMails.length ? (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[800px]">
                      <thead className="bg-slate-50 text-left">
                        <tr>
                          {["Type / Subject", "Status", "Channel", "Sender", "Created"].map((h) => (
                            <th key={h} className="px-6 py-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {receivedMails.map((mail) => (
                          <tr
                            key={`recv-${mail.communication_id}-${mail.template_id || "none"}`}
                            className="hover:bg-slate-50 cursor-pointer transition-colors"
                            onClick={() => setSelectedMail(mail)}
                          >
                            <td className="px-6 py-4 text-sm font-semibold text-slate-800">{mail.mail_type || mail.template_name || "General"}</td>
                            <td className="px-6 py-4 text-sm text-slate-600">{mail.status}</td>
                            <td className="px-6 py-4 text-sm text-slate-600">{mail.channel}</td>
                            <td className="px-6 py-4 text-sm text-slate-600">{mail.recipient}</td>
                            <td className="px-6 py-4 text-sm text-slate-500">{formatTimeAgo(mail.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="p-8 text-sm text-slate-500">No received emails yet.</div>
                )}
              </section>

              <section className="rounded-[28px] border border-slate-200 bg-white/80 shadow-sm overflow-hidden mt-6">
                <div className="border-b border-slate-200 px-6 py-5">
                  <p className="text-sm font-bold uppercase tracking-[0.2em] text-slate-400">Sent Emails</p>
                </div>
                {sentMails.length ? (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[800px]">
                      <thead className="bg-slate-50 text-left">
                        <tr>
                          {["Type / Subject", "Status", "Channel", "Recipient", "Created"].map((h) => (
                            <th key={h} className="px-6 py-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {sentMails.map((mail) => (
                          <tr
                            key={`sent-${mail.communication_id}-${mail.template_id || "none"}`}
                            className="hover:bg-slate-50 cursor-pointer transition-colors"
                            onClick={() => setSelectedMail(mail)}
                          >
                            <td className="px-6 py-4 text-sm font-semibold text-slate-800">{mail.mail_type || mail.template_name || "General"}</td>
                            <td className="px-6 py-4 text-sm text-slate-600">{mail.status}</td>
                            <td className="px-6 py-4 text-sm text-slate-600">{mail.channel}</td>
                            <td className="px-6 py-4 text-sm text-slate-600">{mail.recipient}</td>
                            <td className="px-6 py-4 text-sm text-slate-500">{formatTimeAgo(mail.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="p-8 text-sm text-slate-500">No sent emails yet.</div>
                )}
              </section>
            </div>
          )}

          {activeTab === "portal" && (
            <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
              <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Send {deptLabel} Email</p>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">From</label>
                  <input
                    value={fromEmail}
                    readOnly
                    className="w-full rounded-2xl border-2 border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500 cursor-not-allowed"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Mail To</label>
                  <input
                    value={toEmail}
                    onChange={(e) => setToEmail(e.target.value)}
                    placeholder="recipient@company.com"
                    className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Template</label>
                  <select
                    value={selectedTemplateId}
                    onChange={(e) => handleTemplateChange(e.target.value)}
                    className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                  >
                    <option value="">Select template</option>
                    {emailTemplates.map((t) => (
                      <option key={t.id} value={t.id}>#{t.id} {t.name || "Unnamed"}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Subject</label>
                  <input
                    value={composeSubject}
                    onChange={(e) => setComposeSubject(e.target.value)}
                    className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="mt-4">
                <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Body</label>
                <textarea
                  value={composeBody}
                  onChange={(e) => setComposeBody(e.target.value)}
                  className="min-h-36 w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                />
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  onClick={handleSendEmail}
                  disabled={sending}
                  className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60"
                >
                  {sending ? "Sending..." : "Send Email"}
                </button>
                {sendResult && <p className="text-sm font-semibold text-emerald-700">{sendResult}</p>}
                {sendError && <p className="text-sm font-semibold text-red-700">{sendError}</p>}
              </div>
            </section>
          )}

          {activeTab === "templates" && (
            <DeptTemplatesTab
              clientId={clientId}
              clientPath={clientPath}
              departmentKey={departmentKey}
            />
          )}
        </>
      )}

      {selectedMail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-2xl overflow-hidden rounded-[24px] bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <div>
                <h3 className="font-bold text-slate-900">{selectedMail.subject || selectedMail.mail_type || "Communication Details"}</h3>
                <p className="text-xs text-slate-500 mt-1">
                  {selectedMail.direction === "sent" ? "To" : "From"}: {selectedMail.recipient} • {formatTimeAgo(selectedMail.created_at)}
                </p>
              </div>
              <button
                onClick={() => setSelectedMail(null)}
                className="rounded-full bg-slate-100 p-2 text-slate-500 transition hover:bg-slate-200 hover:text-slate-900"
              >
                ✕
              </button>
            </div>
            
            <div className="p-6 max-h-[70vh] overflow-y-auto">
              {selectedMail.body ? (
                <div 
                  className="prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: selectedMail.body }}
                />
              ) : (
                <div className="flex h-32 items-center justify-center rounded-xl bg-slate-50 border border-slate-100 text-sm text-slate-400 font-medium">
                  No content available for this communication
                </div>
              )}
            </div>
            
            <div className="bg-slate-50 px-6 py-4 border-t border-slate-100 flex justify-end">
              <button 
                onClick={() => setSelectedMail(null)}
                className="rounded-xl px-5 py-2 font-semibold text-slate-600 hover:bg-slate-200 bg-slate-100 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </ClientPortalShell>
  );
}

function Metric({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "danger" }) {
  return (
    <div className={`rounded-2xl border px-4 py-4 ${tone === "danger" ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-slate-50"}`}>
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

type TemplateRecord = {
  id: string | number;
  name: string;
  channel: string;
  language: string;
  subject?: string | null;
  body: string;
  version: number;
  active: boolean;
  is_global: boolean;
  visibility?: "public" | "private";
  category?: string | null;
};

function DeptTemplatesTab({
  clientId,
  clientPath,
  departmentKey,
}: {
  clientId: string;
  clientPath: string;
  departmentKey: string;
}) {
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
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
        const data = await fetchJson<{ templates: TemplateRecord[] }>(
          `/api/client-dashboard/client/${clientId}/department-templates/${departmentKey}`,
        );
        if (!active) return;
        let result = data.templates || [];
        if (!includeGlobal) result = result.filter((t) => !t.is_global);
        if (channelFilter) result = result.filter((t) => t.channel === channelFilter);
        setTemplates(result);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load templates");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [channelFilter, clientId, includeGlobal, departmentKey]);

  const channels = useMemo(
    () => Array.from(new Set(templates.map((t) => t.channel))).sort(),
    [templates],
  );

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-[28px] border border-slate-200 bg-white/80 p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-4">
          <label className="text-sm font-semibold text-slate-700">
            Channel
            <select
              value={channelFilter}
              onChange={(e) => setChannelFilter(e.target.value)}
              className="ml-3 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none"
            >
              <option value="">All</option>
              {channels.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={includeGlobal}
              onChange={(e) => setIncludeGlobal(e.target.checked)}
              className="h-4 w-4 rounded"
            />
            Include Global Templates
          </label>
        </div>
        <Link
          to={clientTemplateNewUrl(clientPath)}
          className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:-translate-y-0.5"
        >
          + Create Template
        </Link>
      </section>

      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading templates...</p>
        </section>
      ) : error ? (
        <section className="rounded-[28px] border border-red-200 bg-red-50 p-6 shadow-sm">
          <p className="text-sm font-semibold text-red-700">{error}</p>
        </section>
      ) : (
        <div className="grid gap-5">
          {templates.map((t) => (
            <article key={String(t.id)} className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-bold tracking-tight text-slate-900">{t.name}</h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Badge>{t.channel}</Badge>
                    <Badge tone={t.is_global ? "amber" : "emerald"}>{t.is_global ? "Global" : "Custom"}</Badge>
                    <Badge tone={t.visibility === "private" ? "slate" : "indigo"}>{t.visibility || "public"}</Badge>
                    <Badge>{t.language}</Badge>
                    <Badge>v{t.version}</Badge>
                  </div>
                </div>
                <Link
                  to={clientTemplateEditUrl(clientPath, t.id)}
                  className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50 transition"
                >
                  Edit
                </Link>
              </div>
              {t.subject ? <p className="mb-3 text-sm font-semibold text-slate-700">Subject: {t.subject}</p> : null}
              <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                {t.body.slice(0, 240)}{t.body.length > 240 ? "..." : ""}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Badge({ children, tone = "indigo" }: { children: ReactNode; tone?: "indigo" | "emerald" | "amber" | "slate" }) {
  const toneMap = {
    indigo: "bg-indigo-50 text-indigo-700",
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    slate: "bg-slate-100 text-slate-700",
  } as const;
  return <span className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${toneMap[tone]}`}>{children}</span>;
}
