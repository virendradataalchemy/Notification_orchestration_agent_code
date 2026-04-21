import { redirect } from "next/navigation";

import ClientAnalyticsPage from "../../../client/[id]/analytics/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientAnalyticsRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const resolved = await resolveClientRouteParam(slug);
  if (!resolved) {
    redirect("/login");
  }
  const canonical = resolved.slug || resolved.id;
  if (slug !== canonical) {
    redirect(`/clients/${canonical}/analytics`);
  }
  return <ClientAnalyticsPage clientIdProp={resolved.id} clientPathProp={canonical} initialClientName={resolved.name} />;
}
