"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";

type TemplatePayload = {
  id: string | number;
  name: string;
  channel: string;
  language: string;
  subject?: string | null;
  body: string;
};

export default function ClientTemplateCreatePage() {
  const params = useParams<{ id: string }>();
  const clientId = String(params.id);
  const searchParams = useSearchParams();
  const templateId = searchParams.get("templateId");

  const [name, setName] = useState("");
  const [channel, setChannel] = useState("email");
  const [language, setLanguage] = useState("en");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<{ rendered_subject?: string | null; rendered_body: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const loadTemplate = async () => {
      if (!templateId) return;
      try {
        const data = await fetchJson<{ templates: TemplatePayload[] }>(`/api/v1/client/templates/?include_global=true`, {
          headers: { "X-Client-Id": clientId },
        });
        if (!active) return;
        const template = data.templates.find((item) => String(item.id) === templateId);
        if (template) {
          setName(template.name);
          setChannel(template.channel);
          setLanguage(template.language);
          setSubject(template.subject || "");
          setBody(template.body);
        }
      } catch {
        // Keep form usable even if preload fails.
      }
    };
    loadTemplate();
    return () => {
      active = false;
    };
  }, [clientId, templateId]);

  const handlePreview = async () => {
    setError(null);
    try {
      const data = await fetchJson<{ rendered_subject?: string | null; rendered_body: string }>(
        "/api/v1/client/templates/preview",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Client-Id": clientId,
          },
          body: JSON.stringify({
            subject,
            body,
            sample_data: {
              name: "Demo User",
              company: "Data Alchemy",
              month: "March",
            },
          }),
        },
      );
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await fetchJson("/api/v1/client/templates/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Client-Id": clientId,
        },
        body: JSON.stringify({
          name,
          channel,
          language,
          subject: subject || null,
          body,
        }),
      });
      setSuccess("Template saved successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save template");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ClientPortalShell
      clientId={clientId}
      title={templateId ? "Edit Template" : "Create Template"}
      description="Build custom notification templates for your channels from the frontend portal."
      actions={
        <Link
          href={`/client/${clientId}/templates`}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
        >
          Back to Templates
        </Link>
      }
    >
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <div className="space-y-5">
            <Field label="Template Name">
              <input value={name} onChange={(event) => setName(event.target.value)} className={inputClassName} />
            </Field>
            <div className="grid gap-5 md:grid-cols-2">
              <Field label="Channel">
                <select value={channel} onChange={(event) => setChannel(event.target.value)} className={inputClassName}>
                  {["email", "sms", "slack", "whatsapp", "push"].map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Language">
                <select value={language} onChange={(event) => setLanguage(event.target.value)} className={inputClassName}>
                  {["en", "hi", "es", "fr", "de"].map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="Subject">
              <input value={subject} onChange={(event) => setSubject(event.target.value)} className={inputClassName} />
            </Field>
            <Field label="Body">
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                className={`${inputClassName} min-h-72 font-mono`}
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <button onClick={handlePreview} className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700">
                Preview
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-70"
              >
                {saving ? "Saving..." : "Save Template"}
              </button>
            </div>
            {error ? <p className="text-sm font-semibold text-red-700">{error}</p> : null}
            {success ? <p className="text-sm font-semibold text-emerald-700">{success}</p> : null}
          </div>
        </section>

        <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
          <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-slate-400">Preview</p>
          {preview ? (
            <div className="space-y-4">
              {preview.rendered_subject ? (
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="mb-2 text-sm font-bold text-slate-700">Rendered Subject</p>
                  <p className="text-sm text-slate-600">{preview.rendered_subject}</p>
                </div>
              ) : null}
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="mb-2 text-sm font-bold text-slate-700">Rendered Body</p>
                <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-600">{preview.rendered_body}</pre>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Generate a preview to inspect how the template renders with sample data.</p>
          )}
        </section>
      </div>
    </ClientPortalShell>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">{label}</span>
      {children}
    </label>
  );
}

const inputClassName =
  "w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500";
