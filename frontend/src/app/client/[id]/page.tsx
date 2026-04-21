"use client";

import { useParams } from "next/navigation";

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
  const clientId = clientIdProp || String(params.id);

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
