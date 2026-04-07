"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";

type ChannelOverview = {
  channel: string;
  total: number;
  sent: number;
  delivered: number;
  failed: number;
  success_rate: number;
};

type ClientOverview = {
  client_name: string;
  tier: string;
  channels: ChannelOverview[];
};

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

export default function ClientDashboardPage() {
  const params = useParams<{ id: string }>();
  const clientId = String(params.id);
  const [overview, setOverview] = useState<ClientOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [messageContent, setMessageContent] = useState("");
  const [userId, setUserId] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<OrchestrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await fetchJson<ClientOverview>(`/api/client-dashboard/client/${clientId}/overview`);
        if (active) setOverview(data);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [clientId]);

  const runPipeline = async () => {
    if (!messageContent.trim()) {
      setError("Please enter message content");
      return;
    }

    setRunning(true);
    setError(null);
    setResult(null);
    setStage(1);

    try {
      await new Promise((resolve) => setTimeout(resolve, 250));
      setStage(2);
      await new Promise((resolve) => setTimeout(resolve, 250));
      setStage(3);
      await new Promise((resolve) => setTimeout(resolve, 250));
      setStage(4);

      const orchestrationResult = await fetchJson<OrchestrationResult>("/api/v1/orchestrate/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Client-Id": clientId,
        },
        body: JSON.stringify({
          message_content: messageContent,
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

  const clearPipeline = () => {
    setMessageContent("");
    setUserId("");
    setStage(0);
    setResult(null);
    setError(null);
  };

  const channels = overview?.channels ?? [];
  const totalNotifications = channels.reduce((sum, item) => sum + item.total, 0);
  const delivered = channels.reduce((sum, item) => sum + item.sent + item.delivered, 0);
  const failed = channels.reduce((sum, item) => sum + item.failed, 0);

  return (
    <ClientPortalShell
      clientId={clientId}
      title={overview?.client_name || `Client ${clientId}`}
      description="Manage your orchestration workspace from the frontend app. Use this dashboard for a quick operational view, then jump into templates, orchestration, and demo flows."
      actions={
        <>
          <Link
            href={`/client/${clientId}/orchestration`}
            className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:-translate-y-0.5"
          >
            Open Full Orchestration
          </Link>
          <Link
            href={`/client/${clientId}/templates`}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
          >
            Manage Templates
          </Link>
        </>
      }
    >
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <section className="rounded-[28px] bg-gradient-to-br from-indigo-600 to-violet-700 p-6 text-white shadow-[0_18px_45px_rgba(79,70,229,0.35)]">
          <div className="mb-6">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-indigo-100">Embedded Orchestration</p>
            <h2 className="text-2xl font-bold tracking-tight">Intelligent Orchestration Pipeline</h2>
            <p className="mt-2 max-w-2xl text-sm text-indigo-100">
              A compact dashboard version of the orchestration flow. For deeper work, open the dedicated orchestration page.
            </p>
          </div>

          <div className="mb-5 grid gap-3 md:grid-cols-3">
            {[
              ["1. Message Input", "Describe the outbound message or instruction you want processed."],
              ["2. Recipient Target", "Provide a candidate or user id for the communication."],
              ["3. AI Delivery", "Let the system choose urgency, template fit, and channel order."],
            ].map(([title, body]) => (
              <div key={title} className="rounded-2xl border border-white/20 bg-white/90 p-4 text-slate-800">
                <p className="mb-2 text-sm font-bold">{title}</p>
                <p className="text-sm leading-6 text-slate-500">{body}</p>
              </div>
            ))}
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-indigo-100">Message Content</label>
              <textarea
                value={messageContent}
                onChange={(event) => setMessageContent(event.target.value)}
                placeholder="Enter your message here..."
                className="min-h-40 w-full rounded-2xl border-2 border-white/20 bg-white/95 px-4 py-4 text-sm text-slate-900 outline-none transition focus:border-white"
              />
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-indigo-100">Candidate / User ID</label>
              <input
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                placeholder="Optional, defaults to test_user"
                className="w-full rounded-2xl border-2 border-white/20 bg-white/95 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-white"
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={runPipeline}
                disabled={running}
                className="rounded-xl bg-white px-5 py-3 text-sm font-bold text-indigo-700 transition hover:bg-slate-100 disabled:opacity-70"
              >
                {running ? "Processing..." : "Run Pipeline"}
              </button>
              <button
                onClick={clearPipeline}
                className="rounded-xl border border-white/25 bg-white/10 px-5 py-3 text-sm font-bold text-white transition hover:bg-white/20"
              >
                Clear
              </button>
            </div>
          </div>

          {(stage > 0 || result || error) && (
            <div className="mt-6 space-y-3">
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
                        ? "border-emerald-500 bg-emerald-100 text-emerald-900"
                        : state === "active"
                          ? "border-amber-400 bg-indigo-100/90 text-slate-900"
                          : state === "error"
                            ? "border-red-500 bg-red-100 text-red-900"
                            : "border-white/20 bg-white/10 text-white"
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
            <div className="mt-6 rounded-2xl border-l-4 border-red-500 bg-white/95 p-5 text-red-700">
              <p className="mb-2 text-sm font-bold">Pipeline Error</p>
              <p className="text-sm">{error}</p>
            </div>
          ) : null}

          {result ? (
            <div className="mt-6 space-y-4">
              <div className="rounded-2xl border-l-4 border-indigo-400 bg-white/95 p-5 text-slate-800">
                <p className="mb-2 text-sm font-bold text-indigo-700">Delivery Status</p>
                <p className="text-sm">
                  <strong>Status:</strong> {result.delivery_status}
                </p>
                <p className="text-sm">
                  <strong>Channel:</strong> {result.channel_used || "N/A"}
                </p>
                <p className="text-sm">
                  <strong>Processing Time:</strong> {result.processing_time_ms}ms
                </p>
              </div>

              {result.priority_order?.length ? (
                <div className="rounded-2xl border-l-4 border-indigo-400 bg-white/95 p-5 text-slate-800">
                  <p className="mb-3 text-sm font-bold text-indigo-700">Channel Priority Order</p>
                  <div className="flex flex-wrap gap-2">
                    {result.priority_order.map((channel, index) => (
                      <span key={channel} className="rounded-full bg-indigo-600 px-3 py-1 text-xs font-bold text-white">
                        {index + 1}. {channel.toUpperCase()}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        <aside className="space-y-5">
          {loading ? (
            <div className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
              <p className="text-sm text-slate-500">Loading dashboard...</p>
            </div>
          ) : (
            <>
              <StatCard label="Total Sent" value={String(totalNotifications)} tone="indigo" />
              <StatCard label="Delivered" value={String(delivered)} tone="emerald" />
              <StatCard label="Failed" value={String(failed)} tone="rose" />
              <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
                <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Channel Health</p>
                <div className="space-y-4">
                  {channels.map((channel) => (
                    <div key={channel.channel}>
                      <div className="mb-2 flex items-center justify-between text-sm">
                        <span className="font-semibold capitalize text-slate-700">{channel.channel}</span>
                        <span className="font-mono text-slate-500">{channel.success_rate}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-100">
                        <div
                          className={`h-2 rounded-full ${
                            channel.success_rate >= 80
                              ? "bg-emerald-500"
                              : channel.success_rate >= 50
                                ? "bg-amber-500"
                                : "bg-rose-500"
                          }`}
                          style={{ width: `${channel.success_rate}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </aside>
      </div>
    </ClientPortalShell>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "indigo" | "emerald" | "rose";
}) {
  const toneMap = {
    indigo: "text-indigo-700",
    emerald: "text-emerald-700",
    rose: "text-rose-700",
  } as const;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white/80 p-6 shadow-sm">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className={`text-4xl font-bold tracking-tight ${toneMap[tone]}`}>{value}</p>
    </section>
  );
}
