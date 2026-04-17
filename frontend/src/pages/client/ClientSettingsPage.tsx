import { useEffect, useMemo, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";

import { ClientPortalShell } from "@/components/client-portal-shell";
import { fetchJson } from "@/lib/client-portal";

type ClientContext = {
  resolved: { id: string; name: string; slug: string | null };
};

type ClientProfile = {
  id: string | number;
  name: string;
  client_slug?: string | null;
  default_language?: string | null;
  brand_color?: string | null;
  api_key_prefix?: string | null;
};

type ClientPreferences = {
  preferred_channels?: string[] | { default?: string[] } | null;
  quiet_hours?: { start?: string; end?: string } | null;
  language?: string | null;
  timezone?: string | null;
};

const CHANNEL_OPTIONS = [
  { value: "email", label: "Email" },
  { value: "sms", label: "SMS" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "slack", label: "Slack" },
  { value: "voice", label: "Voice" },
  { value: "push", label: "Push" },
];

export default function ClientSettingsPage() {
  const params = useParams<{ id: string }>();
  const context = useOutletContext<ClientContext | null>();
  const clientId = context?.resolved?.id || String(params.id);
  const clientPath = context?.resolved?.slug || context?.resolved?.id || clientId;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [preferredChannels, setPreferredChannels] = useState<string[]>([]);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("07:00");
  const [language, setLanguage] = useState("en");
  const [timezone, setTimezone] = useState("UTC");
  const [revealedApiKey, setRevealedApiKey] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [clientProfile, preferences] = await Promise.all([
          fetchJson<ClientProfile>("/api/v1/clients/me", {
            headers: { "X-Client-Id": clientId },
          }),
          fetchJson<ClientPreferences>("/api/v1/clients/me/preferences", {
            headers: { "X-Client-Id": clientId },
          }),
        ]);

        if (!active) return;

        const channels = Array.isArray(preferences.preferred_channels)
          ? preferences.preferred_channels
          : preferences.preferred_channels?.default || [];

        setProfile(clientProfile);
        setPreferredChannels(channels);
        setQuietHoursEnabled(Boolean(preferences.quiet_hours?.start && preferences.quiet_hours?.end));
        setQuietStart(preferences.quiet_hours?.start || "22:00");
        setQuietEnd(preferences.quiet_hours?.end || "07:00");
        setLanguage(preferences.language || clientProfile.default_language || "en");
        setTimezone(preferences.timezone || "UTC");
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load settings");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      active = false;
    };
  }, [clientId]);

  const integrationExample = useMemo(() => {
    const authValue = profile?.api_key_prefix
      ? `${profile.api_key_prefix}_YOUR_SECRET_SUFFIX`
      : "sk_live_YOUR_CLIENT_ID_YOUR_SECRET_SUFFIX";

    return [
      `curl -X POST "https://yourdomain.com/api/v1/integration/trigger" \\`,
      `  -H "Authorization: Bearer ${authValue}" \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -d '{`,
      `    "message": "Hello from your product",`,
      `    "candidate_id": 123,`,
      `    "overrides": {`,
      `      "email": "customer@example.com"`,
      `    }`,
      `  }'`,
    ].join("\n");
  }, [profile?.api_key_prefix]);

  const toggleChannel = (channel: string) => {
    setPreferredChannels((current) =>
      current.includes(channel) ? current.filter((value) => value !== channel) : [...current, channel]
    );
  };

  const savePreferences = async () => {
    setSaving(true);
    setSaveMessage(null);
    setError(null);
    try {
      const updated = await fetchJson<ClientPreferences>("/api/v1/clients/me/preferences", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Client-Id": clientId,
        },
        body: JSON.stringify({
          preferred_channels: preferredChannels,
          quiet_hours: quietHoursEnabled ? { start: quietStart, end: quietEnd } : null,
          language,
          timezone,
        }),
      });

      const channels = Array.isArray(updated.preferred_channels)
        ? updated.preferred_channels
        : updated.preferred_channels?.default || [];

      setPreferredChannels(channels);
      setQuietHoursEnabled(Boolean(updated.quiet_hours?.start && updated.quiet_hours?.end));
      setQuietStart(updated.quiet_hours?.start || quietStart);
      setQuietEnd(updated.quiet_hours?.end || quietEnd);
      setLanguage(updated.language || language);
      setTimezone(updated.timezone || timezone);
      setSaveMessage("Preferences updated successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const rotateApiKey = async () => {
    setRotating(true);
    setCopied(false);
    setError(null);
    try {
      const updated = await fetchJson<ClientProfile & { api_key: string }>("/api/v1/clients/me/api-key/rotate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Client-Id": clientId,
        },
      });

      setProfile(updated);
      setRevealedApiKey(updated.api_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to regenerate API key");
    } finally {
      setRotating(false);
    }
  };

  const copyApiKey = async () => {
    if (!revealedApiKey) return;
    await navigator.clipboard.writeText(revealedApiKey);
    setCopied(true);
  };

  return (
    <ClientPortalShell
      clientId={clientId}
      clientPath={clientPath}
      title="Client Settings"
      description="Manage developer access, preferred delivery channels, and client-level routing defaults from one place."
    >
      {loading ? (
        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-500">Loading settings...</p>
        </section>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-6">
            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5 flex items-start justify-between gap-4">
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Developer Access</p>
                  <h2 className="text-2xl font-bold tracking-tight text-slate-950">API Key</h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                    For security, the full API key cannot be fetched again after creation. You can see the saved prefix and
                    generate a new key when needed.
                  </p>
                </div>
                <button
                  onClick={rotateApiKey}
                  disabled={rotating}
                  className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-slate-800 disabled:opacity-60"
                >
                  {rotating ? "Generating..." : "Regenerate API Key"}
                </button>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <InfoCard label="Client Name" value={profile?.name || "Unknown"} />
                <InfoCard label="Current Key Prefix" value={profile?.api_key_prefix || "Not generated yet"} mono />
              </div>

              {revealedApiKey ? (
                <div className="mt-5 rounded-3xl border border-amber-200 bg-amber-50 p-5">
                  <p className="text-sm font-bold text-amber-900">New API key generated</p>
                  <p className="mt-2 text-sm leading-6 text-amber-800">
                    Save this now. It will not be shown again after you leave this screen.
                  </p>
                  <div className="mt-4 overflow-x-auto rounded-2xl bg-slate-950 px-4 py-4 font-mono text-sm text-emerald-300">
                    {revealedApiKey}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      onClick={copyApiKey}
                      className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-amber-400"
                    >
                      {copied ? "Copied" : "Copy API Key"}
                    </button>
                    <button
                      onClick={() => setRevealedApiKey(null)}
                      className="rounded-xl border border-amber-300 bg-white px-4 py-2 text-sm font-bold text-amber-900 transition hover:bg-amber-100"
                    >
                      I saved it
                    </button>
                  </div>
                </div>
              ) : null}

              <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-950 px-5 py-5 text-white">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Integration Example</p>
                  <span className="rounded-full bg-emerald-500/20 px-2 py-1 text-[10px] font-bold text-emerald-400">LIVE</span>
                </div>
                <div className="overflow-x-auto rounded-2xl bg-black/40 p-4 font-mono text-xs text-slate-300">
                  <pre><code>{integrationExample}</code></pre>
                </div>
              </div>
            </section>

            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5">
                <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Routing Defaults</p>
                <h2 className="text-2xl font-bold tracking-tight text-slate-950">Preferences</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  These defaults shape which direct recipient fields appear in your workspace and how your orchestration
                  experience starts.
                </p>
              </div>

              <div className="space-y-6">
                <div>
                  <label className="mb-3 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
                    Preferred Channels
                  </label>
                  <div className="flex flex-wrap gap-3">
                    {CHANNEL_OPTIONS.map((channel) => {
                      const selected = preferredChannels.includes(channel.value);
                      return (
                        <button
                          key={channel.value}
                          type="button"
                          onClick={() => toggleChannel(channel.value)}
                          className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                            selected
                              ? "border border-slate-900 bg-slate-900 text-white"
                              : "border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          {channel.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <label className="flex items-center gap-3 text-sm font-semibold text-slate-800">
                    <input
                      type="checkbox"
                      checked={quietHoursEnabled}
                      onChange={(event) => setQuietHoursEnabled(event.target.checked)}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Enable quiet hours
                  </label>
                  {quietHoursEnabled ? (
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      <div>
                        <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Start</label>
                        <input
                          type="time"
                          value={quietStart}
                          onChange={(event) => setQuietStart(event.target.value)}
                          className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">End</label>
                        <input
                          type="time"
                          value={quietEnd}
                          onChange={(event) => setQuietEnd(event.target.value)}
                          className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                        />
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Language</label>
                    <input
                      value={language}
                      onChange={(event) => setLanguage(event.target.value)}
                      className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Timezone</label>
                    <input
                      value={timezone}
                      onChange={(event) => setTimezone(event.target.value)}
                      className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={savePreferences}
                    disabled={saving}
                    className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-bold text-white transition hover:-translate-y-0.5 disabled:opacity-60"
                  >
                    {saving ? "Saving..." : "Save Preferences"}
                  </button>
                  {saveMessage ? <p className="self-center text-sm font-semibold text-emerald-700">{saveMessage}</p> : null}
                </div>
              </div>
            </section>
          </div>

          <aside className="space-y-6">
            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Important</p>
              <div className="space-y-3 text-sm leading-6 text-slate-600">
                <p>Full API keys are intentionally never retrievable after creation.</p>
                <p>Regenerating a key immediately replaces the previous one, so update any external apps using it.</p>
                <p>Preferred channels here also influence direct-recipient fields in the orchestration workspace.</p>
              </div>
            </section>

            {error ? (
              <section className="rounded-[28px] border border-red-200 bg-red-50 p-6 shadow-sm">
                <p className="text-sm font-semibold text-red-700">{error}</p>
              </section>
            ) : null}
          </aside>
        </div>
      )}
    </ClientPortalShell>
  );
}

function InfoCard({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className={mono ? "font-mono text-sm text-slate-900" : "text-sm font-semibold text-slate-900"}>{value}</p>
    </div>
  );
}
