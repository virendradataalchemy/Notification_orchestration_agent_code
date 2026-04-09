"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { fetchJson } from "@/lib/client-portal";

type OrchestrationResult = {
  delivery_status: string;
  channel_used?: string | null;
  processing_time_ms: number;
  urgency?: string;
  selected_template?: {
    template_id?: string | number | null;
    template_name?: string | null;
    confidence_score?: number;
    reasoning?: string;
  };
  priority_order?: string[];
  reasoning?: {
    priority_determination?: string;
    delivery?: string;
  };
};

type ClientOrchestrationWorkspaceProps = {
  clientId: string;
};

type RecipientField = "email" | "phone" | "whatsapp_number" | "slack_channel";

type ClientPreferences = {
  preferred_channels?: string[] | { default?: string[] } | null;
};

const DIRECT_CHANNEL_FIELDS: Record<string, RecipientField> = {
  email: "email",
  sms: "phone",
  voice: "phone",
  whatsapp: "whatsapp_number",
  slack: "slack_channel",
};

const RECIPIENT_FIELD_COPY: Record<RecipientField, { label: string; placeholder: string }> = {
  email: { label: "Email ID", placeholder: "person@example.com" },
  phone: { label: "Mobile Number", placeholder: "+919876543210" },
  whatsapp_number: { label: "WhatsApp Number", placeholder: "+919876543210" },
  slack_channel: { label: "Slack", placeholder: "C0123456789, U0123456789, or #alerts" },
};

const DEFAULT_DIRECT_CHANNELS = ["sms", "whatsapp", "email", "slack"];

export function ClientOrchestrationWorkspace({ clientId }: ClientOrchestrationWorkspaceProps) {
  const [message, setMessage] = useState("");
  const [userId, setUserId] = useState("");
  const [directRecipients, setDirectRecipients] = useState<Record<RecipientField, string>>({
    email: "",
    phone: "",
    whatsapp_number: "",
    slack_channel: "",
  });
  const [clientPreferredChannels, setClientPreferredChannels] = useState<string[]>(DEFAULT_DIRECT_CHANNELS);
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(0);
  const [result, setResult] = useState<OrchestrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recipientFields = useMemo(() => {
    const fields = clientPreferredChannels
      .map((channel) => DIRECT_CHANNEL_FIELDS[channel])
      .filter((field): field is RecipientField => Boolean(field));
    return Array.from(new Set(fields));
  }, [clientPreferredChannels]);

  useEffect(() => {
    let cancelled = false;

    const loadClientPreferences = async () => {
      try {
        const preferences = await fetchJson<ClientPreferences>("/preferences/orchestration-recipient", {
          headers: {
            "X-Client-Id": clientId,
          },
        });
        if (cancelled) return;

        const preferred = preferences.preferred_channels;
        const nextChannels = Array.isArray(preferred) ? preferred : preferred?.default;
        setClientPreferredChannels(nextChannels?.length ? nextChannels : DEFAULT_DIRECT_CHANNELS);
      } catch {
        if (!cancelled) {
          setClientPreferredChannels(DEFAULT_DIRECT_CHANNELS);
        }
      }
    };

    loadClientPreferences();

    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const runPipeline = async () => {
    if (!message.trim()) {
      setError("Please enter message content");
      return;
    }
    const trimmedUserId = userId.trim();
    const recipientPayload = Object.fromEntries(
      recipientFields.map((field) => [field, directRecipients[field].trim()]).filter(([, value]) => value)
    );
    if (!trimmedUserId && !Object.keys(recipientPayload).length) {
      setError("Please enter a user id or at least one recipient contact");
      return;
    }

    setRunning(true);
    setStage(1);
    setResult(null);
    setError(null);

    try {
      for (const nextStage of [2, 3, 4]) {
        await new Promise((resolve) => setTimeout(resolve, 300));
        setStage(nextStage);
      }

      const orchestrationResult = await fetchJson<OrchestrationResult>("/api/v1/orchestrate/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Client-Id": clientId,
        },
        body: JSON.stringify({
          message_content: message,
          user_id: trimmedUserId || undefined,
          ...(trimmedUserId ? {} : recipientPayload),
        }),
      });

      setResult(orchestrationResult);
      setStage(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline failed");
      setStage(-1);
    } finally {
      setRunning(false);
    }
  };

  const resetWorkspace = () => {
    setMessage("");
    setUserId("");
    setDirectRecipients({
      email: "",
      phone: "",
      whatsapp_number: "",
      slack_channel: "",
    });
    setStage(0);
    setResult(null);
    setError(null);
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Intelligent Pipeline</p>
            <h2 className="text-3xl font-bold tracking-tight text-slate-950">Intelligent Orchestration Pipeline</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Analyze the message, identify the best delivery path, choose a template, and dispatch through the backend
              orchestration flow from one workspace.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {[
              ["Message Input", "Add the outbound content you want processed."],
              ["Recipient Target", "Use a user id when available, or send to direct contact details."],
              ["AI Delivery", "Review routing, urgency, and channel decisions."],
            ].map(([title, body]) => (
              <div key={title} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="mb-2 text-sm font-bold text-slate-800">{title}</p>
                <p className="text-sm leading-6 text-slate-500">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <div className="space-y-5">
            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Message Content</label>
              <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Enter your message here..."
                className="min-h-52 w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-4 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Candidate / User ID Optional</label>
                <input
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                  placeholder="Use this first when available"
                  className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                />
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  If this is filled, the pipeline uses it as the main recipient target.
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Pipeline Stages</p>
                <p className="text-sm leading-6 text-slate-600">
                  Content analysis, template selection, priority scoring, and dispatch execution run in order each time you
                  start the flow.
                </p>
              </div>
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Direct Recipient Details</label>
              <div className="grid gap-4 md:grid-cols-2">
                {recipientFields.map((field) => (
                  <div key={field}>
                    <label className="mb-2 block text-xs font-bold text-slate-500">{RECIPIENT_FIELD_COPY[field].label}</label>
                    <input
                      value={directRecipients[field]}
                      onChange={(event) => setDirectRecipients({ ...directRecipients, [field]: event.target.value })}
                      placeholder={RECIPIENT_FIELD_COPY[field].placeholder}
                      disabled={Boolean(userId.trim())}
                      className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500 disabled:bg-slate-100 disabled:text-slate-400"
                    />
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                These boxes follow this client&apos;s preferred channels. They are used only when the user id is blank.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={runPipeline}
                disabled={running}
                className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-bold text-white transition hover:-translate-y-0.5 disabled:opacity-70"
              >
                {running ? "Processing..." : "Run Pipeline"}
              </button>
              <button
                onClick={resetWorkspace}
                className="rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
              >
                Clear
              </button>
            </div>
          </div>
        </section>

        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Pipeline Activity</p>

          {(stage > 0 || result || error) && (
            <div className="space-y-3">
              {[
                "Analyzing content...",
                "Selecting template...",
                "Determining priority...",
                "Sending notification...",
              ].map((label, index) => {
                const stageIndex = index + 1;
                const state =
                  stage === -1 && stageIndex === 4
                    ? "error"
                    : stage >= 5 || stage > stageIndex
                      ? "complete"
                      : stage === stageIndex
                        ? "active"
                        : "idle";

                return (
                  <div
                    key={label}
                    className={`rounded-2xl border-l-4 px-4 py-4 ${
                      state === "complete"
                        ? "border-emerald-500 bg-emerald-50 text-emerald-900"
                        : state === "active"
                          ? "border-amber-400 bg-indigo-50 text-slate-900"
                          : state === "error"
                            ? "border-red-500 bg-red-50 text-red-900"
                            : "border-slate-200 bg-slate-50 text-slate-500"
                    }`}
                  >
                    <p className="text-sm font-semibold">{label}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.18em]">
                      {state === "complete"
                        ? "Completed"
                        : state === "active"
                          ? "Running"
                          : state === "error"
                            ? "Error"
                            : "Pending"}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {!stage && !result && !error ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
              Start the pipeline to see orchestration progress and delivery output here.
            </div>
          ) : null}

          {error ? (
            <div className="mt-5 rounded-2xl border-l-4 border-red-500 bg-red-50 p-5 text-red-700">
              <p className="mb-2 text-sm font-bold">Pipeline Error</p>
              <p className="text-sm">{error}</p>
            </div>
          ) : null}

          {result ? (
            <div className="mt-5 space-y-4">
              <ResultCard title="Delivery Status">
                <p className="text-sm">
                  <strong>Status:</strong> {result.delivery_status}
                </p>
                <p className="text-sm">
                  <strong>Channel:</strong> {result.channel_used || "N/A"}
                </p>
                <p className="text-sm">
                  <strong>Processing Time:</strong> {result.processing_time_ms}ms
                </p>
              </ResultCard>

              {result.urgency ? (
                <ResultCard title="Urgency Analysis">
                  <p className="text-lg font-bold uppercase text-slate-800">{result.urgency}</p>
                </ResultCard>
              ) : null}

              {result.selected_template ? (
                <ResultCard title="Template Selection">
                  <p className="text-sm">
                    <strong>Template:</strong> {result.selected_template.template_name || "None"}
                  </p>
                  <p className="text-sm">
                    <strong>Template ID:</strong> {result.selected_template.template_id || "None"}
                  </p>
                  <p className="text-sm">
                    <strong>Confidence:</strong> {(((result.selected_template.confidence_score || 0) * 100).toFixed(0))}%
                  </p>
                  <p className="text-sm italic text-slate-500">{result.selected_template.reasoning || ""}</p>
                </ResultCard>
              ) : null}

              {result.priority_order?.length ? (
                <ResultCard title="Channel Priority Order">
                  <div className="flex flex-wrap gap-2">
                    {result.priority_order.map((channel, index) => (
                      <span key={channel} className="rounded-full bg-indigo-600 px-3 py-1 text-xs font-bold text-white">
                        {index + 1}. {channel.toUpperCase()}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-sm italic text-slate-500">{result.reasoning?.priority_determination || ""}</p>
                </ResultCard>
              ) : null}

              {result.reasoning?.delivery ? (
                <ResultCard title="AI Reasoning">
                  <p className="text-sm">{result.reasoning.delivery}</p>
                </ResultCard>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function ResultCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border-l-4 border-indigo-400 bg-slate-50 px-5 py-5">
      <p className="mb-3 text-sm font-bold text-indigo-700">{title}</p>
      <div className="space-y-2 text-slate-700">{children}</div>
    </section>
  );
}
