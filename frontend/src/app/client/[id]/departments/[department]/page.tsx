"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson, formatTimeAgo } from "@/lib/client-portal";
import { supabase } from "@/lib/supabase";
import {
  clientAnalyticsUrl,
  clientDepartmentsUrl,
  clientPortalUrl,
  clientTemplatesUrl,
} from "@/lib/client-routes";

type DepartmentKey = "hr" | "it" | "finance";

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
  created_at?: string | null;
  opened_at?: string | null;
};

type DepartmentStats = {
  total: number;
  sent: number;
  received: number;
  opened: number;
  failed: number;
  in_progress: number;
};

type DepartmentCard = {
  department: DepartmentKey;
  label: string;
  role_emails: string[];
  metrics: DepartmentStats;
  templates: DepartmentTemplate[];
  recent_mails: DepartmentMail[];
};

type UseCaseInfo = {
  key: string;
  title: string;
  description: string;
  teams: string[];
};

type DepartmentDetailResponse = {
  client_id: number;
  client_name?: string;
  generated_at?: string;
  department?: DepartmentCard;
  use_cases?: UseCaseInfo[];
  error?: string;
};

type ClientDepartmentDetailPageProps = {
  clientIdProp?: string;
  clientPathProp?: string;
  initialClientName?: string;
  departmentProp?: string;
};

export default function ClientDepartmentDetailPage({
  clientIdProp,
  clientPathProp,
  initialClientName = "",
  departmentProp,
}: ClientDepartmentDetailPageProps = {}) {
  const params = useParams<{ id: string; department: string }>();
  const clientId = clientIdProp || String(params.id);
  const clientPath = clientPathProp || clientId;
  const departmentKey = (departmentProp || params.department || "").toLowerCase();

  const [payload, setPayload] = useState<DepartmentDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
        );
        if (!active) return;
        if (data.error) {
          setError(data.error);
          setPayload(null);
          return;
        }
        setPayload(data);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load department details");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [clientId, departmentKey]);

  useEffect(() => {
    let active = true;
    const loadCurrentUser = async () => {
      const { data } = await supabase.auth.getUser();
      if (!active) return;
      setFromEmail(data.user?.email || "");
    };
    loadCurrentUser();
    return () => {
      active = false;
    };
  }, []);

  const department = payload?.department;

  useEffect(() => {
    if (!department) return;
    if (!toEmail && department.role_emails.length) {
      setToEmail(department.role_emails[0]);
    }
  }, [department, toEmail]);
  const navLinks = useMemo(
    () => [
      { label: "Intelligent Portal", href: clientPortalUrl(clientPath) },
      { label: "Templates", href: clientTemplatesUrl(clientPath) },
      { label: "Analytics", href: clientAnalyticsUrl(clientPath) },
      { label: "All Departments", href: clientDepartmentsUrl(clientPath) },
    ],
    [clientPath],
  );

  const emailTemplates = useMemo(
    () => (department?.templates || []).filter((template) => (template.channel || "").toLowerCase() === "email"),
    [department],
  );

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId);
    if (!templateId) {
      setComposeSubject("");
      setComposeBody("");
      return;
    }
    const selected = emailTemplates.find((template) => String(template.id) === templateId);
    if (!selected) return;
    setComposeSubject(selected.subject || "");
    setComposeBody(selected.content || "");
  };

  const handleSendEmail = async () => {
    setSendError(null);
    setSendResult(null);
    if (!toEmail.trim()) {
      setSendError("Mail To is required.");
      return;
    }
    if (!composeBody.trim()) {
      setSendError("Email body is required.");
      return;
    }

    setSending(true);
    try {
      const response = await fetchJson<{
        status: string;
        to_email: string;
        from_email: string;
        result?: { channels?: Array<{ channel: string; status: string }> };
      }>(`/api/client-dashboard/client/${clientId}/departments/${departmentKey}/send-email`, {
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
      });

      setSendResult(
        `Queued for delivery to ${response.to_email} from ${response.from_email || "system"}`,
      );

      const refreshed = await fetchJson<DepartmentDetailResponse>(
        `/api/client-dashboard/client/${clientId}/departments/${departmentKey}?limit=40`,
      );
      setPayload(refreshed.error ? payload : refreshed);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Failed to send department email");
    } finally {
      setSending(false);
    }
  };

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPath}
      title={department?.label ? `${department.label} Dashboard` : "Department Dashboard"}
      description={
        payload?.client_name
          ? `${payload.client_name} internal communication dashboard with sent, received, opened, in-progress, and failed visibility.`
          : `${initialClientName} internal communication dashboard.`
      }
    >
      <section className="mb-6 rounded-[28px] border border-slate-200 bg-white/80 p-5 shadow-sm">
        <div className="flex flex-wrap gap-2">
          {navLinks.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            >
              {item.label}
            </Link>
          ))}
        </div>
      </section>

      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading department dashboard...</p>
        </section>
      ) : error || !department ? (
        <section className="rounded-[28px] border border-red-200 bg-red-50 p-6 shadow-sm">
          <p className="text-sm font-semibold text-red-700">{error || "Department not found"}</p>
        </section>
      ) : (
        <div className="space-y-6">
          <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Compose Department Email</p>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">From</label>
                <input
                  value={fromEmail}
                  onChange={(event) => setFromEmail(event.target.value)}
                  className="w-full rounded-2xl border-2 border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700"
                />
                <p className="mt-1 text-xs text-slate-500">Auto-filled from signed-in user email.</p>
              </div>
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Mail To</label>
                <input
                  value={toEmail}
                  onChange={(event) => setToEmail(event.target.value)}
                  placeholder="recipient@company.com"
                  className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Predefined Template</label>
                <select
                  value={selectedTemplateId}
                  onChange={(event) => handleTemplateChange(event.target.value)}
                  className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                >
                  <option value="">Select template</option>
                  {emailTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      #{template.id} {template.name || "Unnamed"}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Subject</label>
                <input
                  value={composeSubject}
                  onChange={(event) => setComposeSubject(event.target.value)}
                  className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="mt-4">
              <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Body</label>
              <textarea
                value={composeBody}
                onChange={(event) => setComposeBody(event.target.value)}
                className="min-h-44 w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                onClick={handleSendEmail}
                disabled={sending}
                className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60"
              >
                {sending ? "Sending..." : "Send Direct Email"}
              </button>
              {sendResult ? <p className="text-sm font-semibold text-emerald-700">{sendResult}</p> : null}
              {sendError ? <p className="text-sm font-semibold text-red-700">{sendError}</p> : null}
            </div>
          </section>

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

          <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Role Inboxes</p>
            {department.role_emails.length ? (
              <div className="flex flex-wrap gap-2">
                {department.role_emails.map((mail) => (
                  <span key={mail} className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-700">
                    {mail}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No role inbox configured for this tenant department yet.</p>
            )}
          </section>

          <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Department Templates</p>
            {department.templates.length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {department.templates.map((template) => (
                  <article key={template.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-sm font-bold text-slate-900">#{template.id} {template.name || "Unnamed"}</p>
                    <p className="text-xs text-slate-500">{template.notification_type || "general"} • {template.channel || "unknown"}</p>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Category: {template.category || "unassigned"}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No templates mapped to this department.</p>
            )}
          </section>

          <section className="rounded-[28px] border border-slate-200 bg-white/80 shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 px-6 py-5">
              <p className="text-sm font-bold uppercase tracking-[0.2em] text-slate-400">Recent Mail Activities</p>
            </div>
            {department.recent_mails.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead className="bg-slate-50 text-left">
                    <tr>
                      {[
                        "Type",
                        "Category",
                        "Direction",
                        "Status",
                        "Channel",
                        "Recipient",
                        "Created",
                        "Opened",
                      ].map((header) => (
                        <th key={header} className="px-6 py-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">
                          {header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {department.recent_mails.map((mail) => (
                      <tr key={`${mail.communication_id}-${mail.template_id || "none"}`}>
                        <td className="px-6 py-4 text-sm font-semibold text-slate-800">{mail.mail_type || mail.template_name || "General"}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{mail.template_category || "unassigned"}</td>
                        <td className="px-6 py-4 text-sm uppercase text-slate-600">{mail.direction}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{mail.status}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{mail.channel}</td>
                        <td className="px-6 py-4 text-sm text-slate-600">{mail.recipient}</td>
                        <td className="px-6 py-4 text-sm text-slate-500">{formatTimeAgo(mail.created_at)}</td>
                        <td className="px-6 py-4 text-sm text-slate-500">{formatTimeAgo(mail.opened_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-sm text-slate-500">No mail activities available for this department yet.</div>
            )}
          </section>

          {(payload?.use_cases || []).length ? (
            <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Relevant Use Cases</p>
              <div className="grid gap-4 md:grid-cols-2">
                {(payload?.use_cases || []).map((item) => (
                  <article key={item.key} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm font-bold text-slate-900">{item.title}</p>
                    <p className="mt-1 text-sm text-slate-600">{item.description}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </ClientPortalShell>
  );
}

function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "danger";
}) {
  return (
    <div className={`rounded-2xl border px-4 py-4 ${tone === "danger" ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-slate-50"}`}>
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
