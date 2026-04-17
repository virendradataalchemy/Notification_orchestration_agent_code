import { useOutletContext, useParams, Link } from "react-router-dom";

import { ClientOrchestrationWorkspace } from "@/components/client-orchestration-workspace";
import { ClientPortalShell } from "@/components/client-portal-shell";
import { DashboardStats } from "@/components/dashboard-stats";
import { ServiceShowcase } from "@/components/service-showcase";
import { RecentNotifications } from "@/components/recent-notifications";
import { clientAnalyticsUrl, clientDemoUrl, clientTemplatesUrl } from "@/lib/client-routes";

type ClientDashboardPageProps = {
  clientIdProp?: string;
  clientPathProp?: string;
};

export default function ClientDashboardPage({
  clientIdProp,
  clientPathProp,
}: ClientDashboardPageProps = {}) {
  const params = useParams<{ id: string }>();
  const context = useOutletContext<{ resolved: { id: string; name: string; slug: string | null } } | null>();
  
  const clientId = clientIdProp || context?.resolved?.id || String(params.id);
  const clientPath = clientPathProp || context?.resolved?.slug || context?.resolved?.id || clientId;

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPathProp || clientId}
      title="Notification Dashboard"
      description="Manage templates and view notifications with AI routing decisions from your central control center."
    >
      <div className="space-y-10">
        <DashboardStats clientId={clientId} />

        <section className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Intelligent Pipeline</p>
              <h2 className="text-2xl font-bold tracking-tight text-slate-950">Intelligent Orchestration Pipeline</h2>
            </div>
            <Link 
              to={clientDemoUrl(clientPath)}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
            >
              🎯 Open Demo
            </Link>
          </div>
          <ClientOrchestrationWorkspace clientId={clientId} />
        </section>

        <section className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-8">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Services</p>
            <h2 className="text-2xl font-bold tracking-tight text-slate-950">Service Showcase</h2>
          </div>
          <ServiceShowcase clientId={clientId} />
        </section>

        <section className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Analytics</p>
              <h2 className="text-2xl font-bold tracking-tight text-slate-950">Recent Notifications with AI Decisions</h2>
            </div>
            <Link 
              to={clientAnalyticsUrl(clientPath)}
              className="text-sm font-bold text-indigo-600 hover:text-indigo-700"
            >
              View All Analytics →
            </Link>
          </div>
          <RecentNotifications clientId={clientId} />
        </section>

        <section className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-8">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Management</p>
            <h2 className="text-2xl font-bold tracking-tight text-slate-950">Quick Actions</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <ActionCard 
              to={clientTemplatesUrl(clientPath)}
              icon="📚"
              title="My Templates"
              description="View and manage your notification templates"
            />
            <ActionCard 
              to={clientAnalyticsUrl(clientPath)}
              icon="📈"
              title="Client Metrics"
              description="Open detailed delivery analytics"
            />
            <ActionCard 
              to={clientTemplatesUrl(clientPath)}
              icon="🌐"
              title="Global Templates"
              description="Browse and clone platform templates"
            />
          </div>
        </section>
      </div>
    </ClientPortalShell>
  );
}

function ActionCard({ to, icon, title, description }: { to: string; icon: string; title: string; description: string }) {
  return (
    <Link 
      to={to}
      className="flex items-center gap-4 rounded-2xl border-2 border-slate-100 bg-slate-50 p-5 transition hover:border-indigo-500 hover:bg-indigo-50"
    >
      <div className="text-3xl">{icon}</div>
      <div>
        <h3 className="font-bold text-slate-900">{title}</h3>
        <p className="text-xs text-slate-500">{description}</p>
      </div>
    </Link>
  );
}

