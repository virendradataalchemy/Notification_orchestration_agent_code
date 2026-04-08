import { redirect } from "next/navigation";

import ClientDashboardPage from "../../../client/[id]/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientPortalRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const resolved = await resolveClientRouteParam(id);
  if (!resolved) {
    redirect("/login");
  }
  if (id !== resolved.slug) {
    redirect(`/clients/${resolved.slug}/portal`);
  }
  return <ClientDashboardPage clientIdProp={resolved.id} clientPathProp={resolved.slug} />;
}
