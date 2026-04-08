import { redirect } from "next/navigation";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientsIndexRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const resolved = await resolveClientRouteParam(id);
  redirect(`/clients/${resolved?.slug || id}/portal`);
}
