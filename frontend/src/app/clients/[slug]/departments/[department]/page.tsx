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
    redirect("/login");
  }
  if (slug !== resolved.slug) {
    redirect(`/clients/${resolved.slug}/departments/${department}`);
  }

  return (
    <ClientDepartmentDetailPage
      clientIdProp={resolved.id}
      clientPathProp={resolved.slug}
      initialClientName={resolved.name}
      departmentProp={department}
    />
  );
}
