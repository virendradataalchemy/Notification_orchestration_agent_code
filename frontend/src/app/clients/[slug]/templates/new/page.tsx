import { redirect } from "next/navigation";

import ClientTemplateCreatePage from "../../../../client/[id]/templates/create/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientTemplateNewRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const resolved = await resolveClientRouteParam(slug);
  if (!resolved) {
    redirect("/login");
  }
  if (slug !== resolved.slug) {
    redirect(`/clients/${resolved.slug}/templates/new`);
  }
  return <ClientTemplateCreatePage clientIdProp={resolved.id} clientPathProp={resolved.slug} initialClientName={resolved.name} />;
}
