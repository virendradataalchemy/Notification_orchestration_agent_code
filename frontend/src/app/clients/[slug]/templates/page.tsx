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
  if (slug !== resolved.slug) {
    redirect(`/clients/${resolved.slug}/templates`);
  }

  return <ClientTemplatesPage clientIdProp={resolved.id} clientPathProp={resolved.slug} initialClientName={resolved.name} />;
}
