import { useEffect, useState } from "react";
import { fetchJson } from "@/lib/client-portal";

type Service = {
  channel: string;
  enabled: boolean;
  priority: number;
  providers: string[];
  template_count: number;
  sample_templates: string[];
};

type Showcase = {
  services: Service[];
  routing: { provider_count: number };
  deduplication: { potential_duplicates_prevented: number };
  templates: { total: number };
  slots: { total: number };
};

export function ServiceShowcase({ clientId }: { clientId: string }) {
  const [showcase, setShowcase] = useState<Showcase | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadShowcase = async () => {
      try {
        const data = await fetchJson<Showcase>(`/api/client-dashboard/client/${clientId}/service-showcase`, {
          headers: { "X-Client-Id": clientId },
        });
        setShowcase(data);
      } catch (err) {
        console.error("Failed to load showcase", err);
      } finally {
        setLoading(false);
      }
    };
    loadShowcase();
  }, [clientId]);

  if (loading || !showcase) return null;

  return (
    <section className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard 
          label="Routing" 
          value={`${showcase.routing.provider_count} providers`} 
          bg="bg-blue-50" 
          text="text-blue-700" 
        />
        <SummaryCard 
          label="Deduplication" 
          value={`${showcase.deduplication.potential_duplicates_prevented} prevented`} 
          bg="bg-emerald-50" 
          text="text-emerald-700" 
        />
        <SummaryCard 
          label="Templates" 
          value={`${showcase.templates.total} active`} 
          bg="bg-orange-50" 
          text="text-orange-700" 
        />
        <SummaryCard 
          label="Slots" 
          value={`${showcase.slots.total} scheduling`} 
          bg="bg-purple-50" 
          text="text-purple-700" 
        />
      </div>

      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {showcase.services.map((service) => (
          <div key={service.channel} className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
            <div className="mb-3 flex items-center justify-between">
              <strong className="capitalize text-slate-900">{service.channel.replace("_", " ")}</strong>
              <span className={`text-xs font-bold ${service.enabled ? "text-emerald-600" : "text-rose-600"}`}>
                {service.enabled ? "Enabled" : "Disabled"}
              </span>
            </div>
            <div className="space-y-1.5 text-xs text-slate-500">
              <p>Priority: {service.priority}</p>
              <p>Providers: {service.providers.length ? service.providers.join(", ") : "None"}</p>
              <p>Templates: {service.template_count}</p>
              <p className="mt-2 font-medium text-slate-400">
                {service.sample_templates.length ? service.sample_templates.join(", ") : "No client templates yet"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SummaryCard({ label, value, bg, text }: { label: string; value: string; bg: string; text: string }) {
  return (
    <div className={`rounded-2xl ${bg} p-4`}>
      <strong className="block text-sm text-slate-900">{label}</strong>
      <div className={`mt-1 text-xs font-medium ${text}`}>{value}</div>
    </div>
  );
}
