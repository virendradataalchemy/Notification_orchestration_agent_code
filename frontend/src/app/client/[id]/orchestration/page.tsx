"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { ClientOrchestrationWorkspace } from "@/components/client-orchestration-workspace";
import { ClientPortalShell } from "@/components/client-portal-shell";
import { clientPortalUrl } from "@/lib/client-routes";

export default function ClientOrchestrationPage() {
  const params = useParams<{ id: string }>();
  const clientId = String(params.id);

  return (
    <ClientPortalShell
      clientId={clientId}
      title="Intelligent Orchestration Pipeline"
      description="This route uses the same full-page orchestration workspace as the Intelligent Portal while keeping a dedicated URL for direct access."
      actions={
        <Link
          href={clientPortalUrl(clientId)}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
        >
          Back to Intelligent Portal
        </Link>
      }
    >
      <ClientOrchestrationWorkspace clientId={clientId} />
    </ClientPortalShell>
  );
}
