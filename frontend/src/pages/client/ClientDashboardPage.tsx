import { useOutletContext, useParams } from "react-router-dom";

import { ClientOrchestrationWorkspace } from "@/components/client-orchestration-workspace";
import { ClientPortalShell } from "@/components/client-portal-shell";

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
      title="Intelligent Portal"
      description="Use the orchestration workspace to run message analysis, routing, template selection, and dispatch from a single full-page view."
    >
      <ClientOrchestrationWorkspace clientId={clientId} />
    </ClientPortalShell>
  );
}
