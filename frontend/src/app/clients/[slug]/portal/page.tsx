import { redirect } from "next/navigation";

import ClientDashboardPage from "../../../client/[id]/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientPortalRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const resolved = await resolveClientRouteParam(slug);
  if (!resolved) {
    redirect("/login");
  }
  if (slug !== (resolved.slug || resolved.id)) {
    redirect(`/clients/${resolved.slug || resolved.id}/portal`);
  }
  return <ClientDashboardPage clientIdProp={resolved.id} clientPathProp={resolved.slug || resolved.id} />;
}
