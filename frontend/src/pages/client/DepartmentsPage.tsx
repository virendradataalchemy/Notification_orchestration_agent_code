import { useEffect, useState } from "react";
import { Link, useParams, useOutletContext } from "react-router-dom";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";
import { clientDepartmentUrl } from "@/lib/client-routes";
import { HiredCandidateModal } from "@/components/hired-candidate-modal";

type DepartmentKey = "hr" | "it" | "finance";

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

type DepartmentTemplate = {
  id: number;
  name?: string;
  notification_type?: string;
  category?: string | null;
  channel?: string;
  subject?: string | null;
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

type DepartmentsResponse = {
  client_id: number;
  client_name?: string;
  generated_at?: string;
  departments: DepartmentCard[];
  use_cases: UseCaseInfo[];
};

type ClientDepartmentsPageProps = {
  clientIdProp?: string;
  clientPathProp?: string;
  initialClientName?: string;
};

const departmentTone: Record<DepartmentKey, string> = {
  hr: "from-emerald-500/10 to-emerald-100/20 border-emerald-200",
  it: "from-sky-500/10 to-sky-100/20 border-sky-200",
  finance: "from-amber-500/10 to-amber-100/20 border-amber-200",
};

export default function DepartmentsPage({
  clientIdProp,
  clientPathProp,
  initialClientName = "",
}: ClientDepartmentsPageProps = {}) {
  const params = useParams<{ id: string }>();
  const context = useOutletContext<{ resolved: { id: string; name: string; slug: string | null } } | null>();
  
  const clientId = clientIdProp || context?.resolved?.id || String(params.id);
  const clientPath = clientPathProp || context?.resolved?.slug || context?.resolved?.id || clientId;
  const initialName = initialClientName || context?.resolved?.name || "";
  const [payload, setPayload] = useState<DepartmentsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchJson<DepartmentsResponse>(`/api/client-dashboard/client/${clientId}/departments?limit=10`, undefined, 5 * 60 * 1000);
        if (!active) return;
        setPayload(data);
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load department dashboards");
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [clientId]);

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPath}
      title={payload?.client_name ? `${payload.client_name} Departments` : initialClientName ? `${initialClientName} Departments` : "Departments"}
      description="Department-level dashboards for HR, IT, and Finance with auto-updated internal communication metrics and template categorization by template id mapping."
      actions={<HiredCandidateModal clientId={clientId} />}
    >
      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading departments...</p>
        </section>
      ) : error ? (
        <section className="rounded-[28px] border border-red-200 bg-red-50 p-6 shadow-sm">
          <p className="text-sm font-semibold text-red-700">{error}</p>
        </section>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {(payload?.departments || []).map((department) => (
              <Link
                key={department.department}
                to={clientDepartmentUrl(clientPath, department.department)}
                className={`rounded-[28px] border bg-gradient-to-b p-5 shadow-sm ${departmentTone[department.department]}`}
              >
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Department</p>
                    <h3 className="text-2xl font-bold tracking-tight text-slate-900">{department.label}</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-white/70 bg-white/80 px-3 py-1 text-xs font-bold text-slate-700">
                      {department.metrics.total} mails
                    </span>
                  </div>
                </div>

                <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
                  <MetricPill label="Sent" value={department.metrics.sent} />
                  <MetricPill label="Received" value={department.metrics.received} />
                  <MetricPill label="Opened" value={department.metrics.opened} />
                  <MetricPill label="In Progress" value={department.metrics.in_progress} />
                  <MetricPill label="Failed" value={department.metrics.failed} tone="warn" />
                  <MetricPill label="Templates" value={department.templates.length} />
                </div>

                <p className="text-xs font-semibold text-slate-500">View details →</p>
              </Link>
            ))}
          </div>
        </div>
      )}
    </ClientPortalShell>
  );
}

function MetricPill({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "warn";
}) {
  return (
    <div
      className={`rounded-xl border px-3 py-2 ${
        tone === "warn" ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-lg font-bold text-slate-900">{value}</p>
    </div>
  );
}
