import { useEffect, useState } from "react";
import { useOutletContext, useParams, useNavigate, useSearchParams } from "react-router-dom";
import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";
import { clientTemplatesUrl } from "@/lib/client-routes";

type TemplateForm = {
  name: string;
  channel: string;
  subject: string;
  body: string;
  description: string;
  language: string;
};

type PreviewResult = {
  valid: boolean;
  rendered_subject?: string;
  rendered_body: string;
  error?: string;
};

export default function TemplateCreatePage() {
  const params = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const templateId = searchParams.get("templateId");
  const navigate = useNavigate();
  const context = useOutletContext<{ resolved: { id: string; name: string; slug: string | null } } | null>();
  
  const clientId = context?.resolved?.id || String(params.id);
  const clientPath = context?.resolved?.slug || context?.resolved?.id || clientId;

  const [form, setForm] = useState<TemplateForm>({
    name: "",
    channel: "",
    subject: "",
    body: "",
    description: "",
    language: "en",
  });

  const [sampleData, setSampleData] = useState<string>(JSON.stringify({
    user: { name: "John Doe", email: "john@example.com" },
    order: { id: "12345", total: "299.99" },
    company: { name: "Your Company" }
  }, null, 2));

  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (templateId) {
      const loadTemplate = async () => {
        try {
          const data = await fetchJson<any>(`/api/v1/client/templates/${templateId}`, {
            headers: { "X-Client-Id": clientId },
          });
          setForm({
            name: data.name || "",
            channel: data.channel || "",
            subject: data.subject || "",
            body: data.content || "",
            description: data.description || "",
            language: data.language || "en",
          });
        } catch (err) {
          console.error("Failed to load template", err);
          setError("Failed to load template for editing");
        }
      };
      loadTemplate();
    }
  }, [templateId, clientId]);

  useEffect(() => {
    const updatePreview = async () => {
      if (!form.body) {
        setPreview(null);
        return;
      }

      let parsedData;
      try {
        parsedData = JSON.parse(sampleData);
      } catch {
        return;
      }

      try {
        const result = await fetchJson<PreviewResult>("/api/v1/client/templates/preview", {
          method: "POST",
          headers: {
            "X-Client-Id": clientId,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            subject: form.subject || null,
            body: form.body,
            sample_data: parsedData,
          }),
        });
        setPreview(result);
      } catch (err) {
        console.error("Preview failed", err);
      }
    };

    const timeout = setTimeout(updatePreview, 500);
    return () => clearTimeout(timeout);
  }, [form.body, form.subject, sampleData, clientId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const url = templateId 
        ? `/api/v1/client/templates/${templateId}` 
        : "/api/v1/client/templates/";
      
      const method = templateId ? "PATCH" : "POST";

      await fetchJson(url, {
        method,
        headers: {
          "X-Client-Id": clientId,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...form,
          content: form.body,
        }),
      });

      navigate(clientTemplatesUrl(clientPath));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save template");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPath}
      title={templateId ? "Edit Template" : "Create New Template"}
      description="Build and test custom notification templates with live Jinja2 rendering."
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <h2 className="mb-6 text-xl font-bold text-slate-900">Template Configuration</h2>
          
          <div className="mb-6 rounded-2xl bg-amber-50 p-4 text-xs text-amber-800">
            <strong>💡 Using Variables</strong>
            <p className="mt-1">Use {"{{variable}}"} syntax for dynamic content. Example: {"{{user.name}}"}</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Template Name</label>
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g., order_confirmation"
                className="w-full rounded-xl border-2 border-slate-100 px-4 py-3 outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Channel</label>
              <select
                required
                value={form.channel}
                onChange={(e) => setForm({ ...form, channel: e.target.value })}
                className="w-full rounded-xl border-2 border-slate-100 px-4 py-3 outline-none focus:border-indigo-500"
              >
                <option value="">Select a channel...</option>
                <option value="email">Email</option>
                <option value="sms">SMS</option>
                <option value="slack">Slack</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="push">Push Notification</option>
              </select>
            </div>

            {form.channel === "email" && (
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Subject</label>
                <input
                  required
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  placeholder="Email subject line"
                  className="w-full rounded-xl border-2 border-slate-100 px-4 py-3 outline-none focus:border-indigo-500"
                />
              </div>
            )}

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Template Body</label>
              <textarea
                required
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                placeholder="Write your template here..."
                className="min-h-[200px] w-full rounded-xl border-2 border-slate-100 px-4 py-3 font-mono text-sm outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex gap-4 pt-4">
              <button
                type="submit"
                disabled={submitting}
                className="flex-1 rounded-xl bg-indigo-600 px-6 py-3 font-bold text-white transition hover:bg-indigo-700 disabled:opacity-50"
              >
                {submitting ? "Saving..." : templateId ? "Update Template" : "Create Template"}
              </button>
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="rounded-xl border border-slate-200 bg-white px-6 py-3 font-bold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
            {error && <p className="mt-2 text-sm font-medium text-rose-600">{error}</p>}
          </form>
        </div>

        <div className="space-y-8">
          <div className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
            <h2 className="mb-6 text-xl font-bold text-slate-900">Live Preview</h2>
            
            <div className="mb-6">
              <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Sample Data (JSON)</label>
              <textarea
                value={sampleData}
                onChange={(e) => setSampleData(e.target.value)}
                className="min-h-[150px] w-full rounded-xl border-2 border-slate-100 bg-slate-50 px-4 py-3 font-mono text-xs outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">Rendered Output</label>
              <div className="min-h-[200px] rounded-xl bg-slate-50 p-6">
                {preview ? (
                  preview.valid ? (
                    <div className="space-y-4">
                      {preview.rendered_subject && (
                        <div className="border-b border-slate-200 pb-2 text-sm font-bold text-slate-900">
                          Subject: {preview.rendered_subject}
                        </div>
                      )}
                      <div className="whitespace-pre-wrap text-sm text-slate-600">{preview.rendered_body}</div>
                    </div>
                  ) : (
                    <div className="text-sm font-medium text-rose-600">
                      <strong>Template Error:</strong>
                      <p className="mt-1">{preview.error}</p>
                    </div>
                  )
                ) : (
                  <p className="text-center text-sm text-slate-400 pt-10">Enter template content to see preview...</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </ClientPortalShell>
  );
}
