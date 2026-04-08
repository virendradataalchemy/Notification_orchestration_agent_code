import ClientTemplatesPage from "../../../client/[id]/templates/page";
import { redirect } from "next/navigation";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientsTemplatesRoute({
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
    redirect(`/clients/${resolved.slug}/templates`);
  }

  return <ClientTemplatesPage clientIdProp={resolved.id} clientPathProp={resolved.slug} initialClientName={resolved.name} />;
}
