import { redirect } from "next/navigation";

import ClientDepartmentDetailPage from "../../../../client/[id]/departments/[department]/page";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientsDepartmentDetailRoute({
  params,
}: {
  params: Promise<{ slug: string; department: string }>;
}) {
  const { slug, department } = await params;
  const resolved = await resolveClientRouteParam(slug);
  if (!resolved) {
    redirect(`/clients/${slug}/portal`);
  }
  const canonicalPath = resolved.slug || resolved.id;
  if (slug !== canonicalPath) {
    redirect(`/clients/${canonicalPath}/departments/${department}`);
  }
  if (resolved.id !== "1") {
    redirect(`/clients/${canonicalPath}/portal`);
  }

  return (
    <ClientDepartmentDetailPage
      clientIdProp={resolved.id}
      clientPathProp={canonicalPath}
      initialClientName={resolved.name}
      departmentProp={department}
    />
  );
}
