import { redirect } from "next/navigation";

import ClientAnalyticsPage from "../../../client/[id]/analytics/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientAnalyticsRoute({
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
    redirect(`/clients/${resolved.slug}/analytics`);
  }
  return <ClientAnalyticsPage clientIdProp={resolved.id} clientPathProp={resolved.slug} initialClientName={resolved.name} />;
}
