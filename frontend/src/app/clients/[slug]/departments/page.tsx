import { redirect } from "next/navigation";

import ClientDepartmentsPage from "../../../client/[id]/departments/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientsDepartmentsRoute({
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
    redirect(`/clients/${resolved.slug}/departments`);
  }

  return <ClientDepartmentsPage clientIdProp={resolved.id} clientPathProp={resolved.slug} initialClientName={resolved.name} />;
}
