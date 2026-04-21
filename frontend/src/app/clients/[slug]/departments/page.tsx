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
    // Can't resolve client — send back to portal rather than login
    redirect(`/clients/${slug}/portal`);
  }
  const canonicalPath = resolved.slug || resolved.id;
  if (slug !== canonicalPath) {
    redirect(`/clients/${canonicalPath}/departments`);
  }
  if (resolved.id !== "1") {
    redirect(`/clients/${canonicalPath}/portal`);
  }

  return <ClientDepartmentsPage clientIdProp={resolved.id} clientPathProp={canonicalPath} initialClientName={resolved.name} />;
}
