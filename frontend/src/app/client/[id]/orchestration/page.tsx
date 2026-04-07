"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { ClientPortalShell } from "@/components/client-portal-shell";
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

export default function ClientOrchestrationPage() {
  const params = useParams<{ id: string }>();
  const clientId = String(params.id);
  const [message, setMessage] = useState("");
  const [userId, setUserId] = useState("");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(0);
  const [result, setResult] = useState<OrchestrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runPipeline = async () => {
    if (!message.trim()) {
      setError("Please enter message content");
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
          user_id: userId.trim() || "test_user",
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

  return (
    <ClientPortalShell
      clientId={clientId}
      title="Intelligent Orchestration Pipeline"
      description="Use the full frontend orchestration workspace to analyze a message, route it through the best channel mix, and inspect the reasoning returned by the backend."
      actions={
        <Link
          href={`/client/${clientId}`}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
        >
          Back to Dashboard
        </Link>
      }
    >
      <div className="rounded-[30px] border border-slate-200 bg-white/85 p-8 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          {[
            ["Message Input", "Enter the outbound content or instruction you want the AI orchestration pipeline to process."],
            ["Candidate Target", "Supply the user or candidate id so the delivery engine knows who should receive the message."],
            ["AI Delivery", "The backend chooses urgency, template fit, and channel order automatically before dispatch."],
          ].map(([title, body]) => (
            <div key={title} className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
              <p className="mb-2 text-sm font-bold text-slate-800">{title}</p>
              <p className="text-sm leading-6 text-slate-500">{body}</p>
            </div>
          ))}
        </div>

        <div className="space-y-5">
          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Message Content</label>
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Enter your message here..."
              className="min-h-44 w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-4 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
            />
          </div>

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Candidate / User ID</label>
            <input
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="Enter candidate id or user id"
              className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
            />
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
              onClick={() => {
                setMessage("");
                setUserId("");
                setStage(0);
                setResult(null);
                setError(null);
              }}
              className="rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
            >
              Clear
            </button>
          </div>
        </div>

        {(stage > 0 || result || error) && (
          <div className="mt-7 space-y-3">
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
                  className={`flex items-center gap-4 rounded-2xl border-l-4 px-4 py-4 ${
                    state === "complete"
                      ? "border-emerald-500 bg-emerald-50 text-emerald-900"
                      : state === "active"
                        ? "border-amber-400 bg-indigo-50 text-slate-900"
                        : state === "error"
                          ? "border-red-500 bg-red-50 text-red-900"
                          : "border-slate-200 bg-slate-50 text-slate-500"
                  }`}
                >
                  <span className="text-xl">
                    {state === "complete" ? "✅" : state === "active" ? "🔄" : state === "error" ? "❌" : "⏳"}
                  </span>
                  <span className="text-sm font-semibold">{label}</span>
                </div>
              );
            })}
          </div>
        )}

        {error ? (
          <div className="mt-6 rounded-2xl border-l-4 border-red-500 bg-red-50 p-5 text-red-700">
            <p className="mb-2 text-sm font-bold">Pipeline Error</p>
            <p className="text-sm">{error}</p>
          </div>
        ) : null}

        {result ? (
          <div className="mt-6 space-y-4">
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
      </div>
    </ClientPortalShell>
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
