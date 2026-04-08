import { redirect } from "next/navigation";

import ClientSendDemoPage from "../../../../client/[id]/send-demo/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientDemoRoute({
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
    redirect(`/clients/${resolved.slug}/notifications/demo`);
  }
  return <ClientSendDemoPage clientIdProp={resolved.id} clientPathProp={resolved.slug} initialClientName={resolved.name} />;
}
