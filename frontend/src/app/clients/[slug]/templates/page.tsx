import ClientTemplatesPage from "../../../client/[id]/templates/page";
import { redirect } from "next/navigation";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientsTemplatesRoute({
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
    redirect(`/clients/${canonical}/templates`);
  }
  return <ClientTemplatesPage clientIdProp={resolved.id} clientPathProp={canonical} initialClientName={resolved.name} />;
}
