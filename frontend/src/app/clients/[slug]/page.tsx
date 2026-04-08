import { redirect } from "next/navigation";
import { resolveClientRouteParam } from "@/lib/server-client-route";

export default async function ClientsIndexRedirect({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const resolved = await resolveClientRouteParam(slug);
  redirect(`/clients/${resolved?.slug || slug}/portal`);
}
