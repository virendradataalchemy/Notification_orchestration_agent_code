"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { clientPortalUrl } from "@/lib/client-routes";
import { supabase } from "@/lib/supabase";

type AdminProfile = {
  id: number | string;
  name?: string | null;
  email?: string | null;
};

type ClientRow = {
  id: number;
  name: string;
  client_slug?: string | null;
  status?: string;
  notification_count?: number;
  provider_configs?: number;
};

type ManagedAdmin = {
  id: number | string;
  supabase_uid?: string | null;
  email?: string | null;
  name?: string | null;
  is_active?: boolean;
  created_at?: string | null;
};

export default function AdminPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [admin, setAdmin] = useState<AdminProfile | null>(null);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [admins, setAdmins] = useState<ManagedAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const [error, setError] = useState("");
  const [createAdminEmail, setCreateAdminEmail] = useState("");
  const [createAdminPassword, setCreateAdminPassword] = useState("");
  const [createAdminName, setCreateAdminName] = useState("");
  const [creatingAdmin, setCreatingAdmin] = useState(false);
  const [createAdminMessage, setCreateAdminMessage] = useState("");

  useEffect(() => {
    const bootstrap = async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        setLoading(false);
        return;
      }

      await loadAdminWorkspace(session.access_token);
    };

    bootstrap();
  }, []);

  const loadAdminWorkspace = async (accessToken: string) => {
    try {
      setLoading(true);
      setError("");

      const [profileRes, clientsRes, adminsRes] = await Promise.all([
        fetch("/admin/api/me", {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }),
        fetch("/admin/api/clients", {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }),
        fetch("/admin/api/admins", {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }),
      ]);

      if (!profileRes.ok) {
        throw new Error("This account is not authorized as an admin.");
      }
      if (!clientsRes.ok) {
        throw new Error("Failed to load admin client list.");
      }
      if (!adminsRes.ok) {
        throw new Error("Failed to load admins.");
      }

      const profile = await profileRes.json();
      const clientsData = await clientsRes.json();
      const adminsData = await adminsRes.json();
      setAdmin(profile);
      setClients(clientsData);
      setAdmins(adminsData);
    } catch (err) {
      setAdmin(null);
      setClients([]);
      setAdmins([]);
      setError(err instanceof Error ? err.message : "Admin access failed.");
    } finally {
      setLoading(false);
      setSigningIn(false);
    }
  };

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setSigningIn(true);
    setError("");

    try {
      const { data, error: authError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (authError) {
        throw authError;
      }

      if (!data.session?.access_token) {
        throw new Error("Admin session could not be created.");
      }

      await loadAdminWorkspace(data.session.access_token);
    } catch (err) {
      setSigningIn(false);
      setError(err instanceof Error ? err.message : "Admin login failed.");
    }
  };

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    setAdmin(null);
    setClients([]);
    setAdmins([]);
    setEmail("");
    setPassword("");
    setError("");
    setCreateAdminMessage("");
  };

  const handleCreateAdmin = async (event: React.FormEvent) => {
    event.preventDefault();
    setCreatingAdmin(true);
    setCreateAdminMessage("");
    setError("");

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        throw new Error("Admin session expired. Please sign in again.");
      }

      const response = await fetch("/admin/api/admins", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          email: createAdminEmail,
          password: createAdminPassword,
          name: createAdminName || null,
          is_active: true,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to create admin.");
      }

      setCreateAdminEmail("");
      setCreateAdminPassword("");
      setCreateAdminName("");
      setCreateAdminMessage("Admin created successfully.");
      await loadAdminWorkspace(session.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create admin.");
    } finally {
      setCreatingAdmin(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[radial-gradient(circle_at_top,_#f8fbff,_#ffffff_55%)] text-slate-900">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-900 border-t-transparent" />
          <p className="text-sm font-semibold text-slate-500">Preparing admin workspace...</p>
        </div>
      </div>
    );
  }

  if (!admin) {
    return (
      <div className="min-h-screen bg-[linear-gradient(180deg,#f8fbff_0%,#ffffff_28%,#ffffff_100%)] text-slate-900">
        <header className="border-b border-slate-200/80 bg-white/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
            <Link href="/" className="text-lg font-bold tracking-tight">
              Orchestrator
            </Link>
            <Link href="/login" className="text-sm font-semibold text-slate-600 hover:text-slate-900">
              Client Login
            </Link>
          </div>
        </header>

        <main className="mx-auto flex min-h-[calc(100vh-73px)] max-w-7xl items-center px-6 py-12">
          <div className="grid w-full gap-10 lg:grid-cols-[0.95fr_1.05fr]">
            <section className="rounded-[32px] border border-slate-200/80 bg-white p-8 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.35)]">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Admin Access</p>
              <h1 className="text-4xl font-bold tracking-tight text-slate-950">Admin Login</h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
                Sign in with an admin account that already exists in Supabase Auth and is registered in the
                `admins` table.
              </p>

              <form onSubmit={handleLogin} className="mt-8 space-y-5">
                <label className="block">
                  <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Email</span>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className={inputClassName}
                    placeholder="admin@company.com"
                  />
                </label>

                <label className="block">
                  <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Password</span>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className={inputClassName}
                    placeholder="Enter your password"
                  />
                </label>

                <button
                  type="submit"
                  disabled={signingIn}
                  className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-bold text-white transition hover:bg-slate-800 disabled:opacity-70"
                >
                  {signingIn ? "Signing in..." : "Sign In as Admin"}
                </button>

                {error ? <p className="text-sm font-semibold text-red-700">{error}</p> : null}
              </form>
            </section>

            <section className="rounded-[32px] border border-slate-200/80 bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] p-8 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.25)]">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Setup Process</p>
              <h2 className="text-2xl font-bold tracking-tight text-slate-950">How admins are created</h2>
              <div className="mt-5 space-y-4 text-sm leading-6 text-slate-600">
                <p>Create the admin user in Supabase Auth first.</p>
                <p>Add the same user to the `admins` table with their `supabase_uid` and email.</p>
                <p>After that, they can sign in here and access the protected admin dashboard.</p>
              </div>
            </section>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#f8fbff_0%,#ffffff_38%,#ffffff_100%)] text-slate-900 pb-12 selection:bg-slate-900 selection:text-white">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3 text-slate-900">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            <span className="font-bold tracking-tight text-lg">System Dashboard</span>
          </div>
          <nav className="flex items-center space-x-6 text-sm font-medium text-slate-500">
            <span className="text-slate-900">Admin: {admin.name || admin.email || "Authorized User"}</span>
            <button onClick={handleSignOut} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-700 transition hover:border-slate-300 hover:text-red-600">Sign Out</button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 mt-12">
        <div className="mb-10 flex flex-col gap-5 rounded-[32px] border border-slate-200/80 bg-white px-8 py-8 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.22)] md:flex-row md:items-end md:justify-between">
          <div>
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Admin Workspace</p>
            <h1 className="mb-2 text-3xl font-semibold tracking-tight text-slate-900">Registered Clients</h1>
            <p className="max-w-2xl text-sm text-slate-500">Monitor organizations, manage platform access, and open each client workspace from one clean control center.</p>
          </div>
          <Link href="/signup" className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-slate-800">
            <span>+</span> New Client
          </Link>
        </div>

        <div className="mb-10 grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <section className="rounded-[32px] border border-slate-200/80 bg-white p-6 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.25)]">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Admin Management</p>
            <h2 className="text-2xl font-bold tracking-tight text-slate-950">Create Admin</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Create a new Supabase Auth user and register it in the `admins` table in one step.
            </p>

            <form onSubmit={handleCreateAdmin} className="mt-6 space-y-4">
              <label className="block">
                <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Name</span>
                <input
                  value={createAdminName}
                  onChange={(event) => setCreateAdminName(event.target.value)}
                  className={inputClassName}
                  placeholder="Platform Admin"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Email</span>
                <input
                  type="email"
                  required
                  value={createAdminEmail}
                  onChange={(event) => setCreateAdminEmail(event.target.value)}
                  className={inputClassName}
                  placeholder="admin@example.com"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Password</span>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={createAdminPassword}
                  onChange={(event) => setCreateAdminPassword(event.target.value)}
                  className={inputClassName}
                  placeholder="Minimum 8 characters"
                />
              </label>

              <button
                type="submit"
                disabled={creatingAdmin}
                className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-bold text-white transition hover:bg-slate-800 disabled:opacity-70"
              >
                {creatingAdmin ? "Creating Admin..." : "Create Admin"}
              </button>

              {createAdminMessage ? <p className="text-sm font-semibold text-emerald-700">{createAdminMessage}</p> : null}
            </form>
          </section>

          <section className="rounded-[32px] border border-slate-200/80 bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] p-6 shadow-[0_24px_70px_-40px_rgba(15,23,42,0.2)]">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-slate-400">Authorized Admins</p>
            <h2 className="text-2xl font-bold tracking-tight text-slate-950">Current Admins</h2>
            <div className="mt-5 space-y-3">
              {admins.map((item) => (
                <div key={String(item.id)} className="rounded-[24px] border border-slate-200 bg-white px-4 py-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-slate-900">{item.name || item.email || "Admin"}</p>
                      <p className="text-sm text-slate-600">{item.email || "No email"}</p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-[11px] font-bold uppercase ${item.is_active ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                      {item.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {clients.map((client) => {
            const isActive = client.status?.toLowerCase() === "active";
            return (
              <div
                key={client.id}
                onClick={() => router.push(clientPortalUrl(client.client_slug || client.id))}
                className="group flex min-h-[240px] cursor-pointer flex-col justify-between rounded-[30px] border border-slate-200/80 bg-white p-6 shadow-[0_20px_60px_-42px_rgba(15,23,42,0.28)] transition-all hover:-translate-y-1 hover:border-slate-300 hover:shadow-[0_26px_80px_-38px_rgba(15,23,42,0.28)]"
              >
                <div>
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <span className="mb-3 inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        {client.client_slug || `ID: ${client.id}`}
                      </span>
                      <h3 className="text-xl font-bold leading-none tracking-tight text-slate-900 transition-colors group-hover:text-blue-600">
                        {client.name}
                      </h3>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.16em] ${isActive ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                      {client.status || "ACTIVE"}
                    </span>
                  </div>
                  <div className="mt-8 grid grid-cols-2 gap-4">
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                      <p className="text-2xl font-semibold text-slate-900">{(client.notification_count || 0).toLocaleString()}</p>
                      <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Outbound</p>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                      <p className="text-2xl font-semibold text-slate-900">{client.provider_configs || 0}</p>
                      <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Providers</p>
                    </div>
                  </div>
                </div>
                <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
                  <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Open Workspace</span>
                  <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white transition group-hover:bg-blue-600">
                    View
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}

const inputClassName =
  "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";
