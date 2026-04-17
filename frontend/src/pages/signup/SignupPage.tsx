import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { supabase } from "@/lib/supabase";

const PENDING_SIGNUP_KEY = "pending_client_signup";
const PENDING_API_KEY_STORAGE = "pending_client_api_key";

export default function SignupPage() {
  const navigate = useNavigate();
  const availableChannels = ["email", "sms", "whatsapp", "voice", "push", "slack", "inapp"];
  
  // Step 1 State
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agree, setAgree] = useState(false);
  
  // Supabase User State
  const [supabaseUserId, setSupabaseUserId] = useState<string | null>(null);
  
  // Step 2 State
  const [clientSlug, setClientSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [brandColor, setBrandColor] = useState("#3b82f6");
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState("22");
  const [quietEnd, setQuietEnd] = useState("08");
  const [activeQuietTime, setActiveQuietTime] = useState<"start" | "end">("start");
  const [channels, setChannels] = useState<{ [key: string]: boolean }>({
    email: true,
    sms: false,
    whatsapp: false,
    voice: false,
    push: false,
    slack: false,
    inapp: false,
  });
  const [language, setLanguage] = useState("en");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<string | null>(null);
  const [revealedApiKey, setRevealedApiKey] = useState<string | null>(null);
  const [apiKeyPrefix, setApiKeyPrefix] = useState<string | null>(null);
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");

  const getErrorMessage = (err: unknown, fallback: string) => {
    if (err instanceof Error && err.message) {
      return err.message;
    }
    return fallback;
  };

  const generateSlug = (value: string) =>
    value.toLowerCase().trim().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");

  const formatQuietHour = (hour: string) => `${hour.padStart(2, "0")}:00`;

  const parseQuietHour = (value: string) => {
    const hour = Number.parseInt(value.split(":")[0] || "0", 10);
    if (Number.isNaN(hour)) {
      return "0";
    }
    return String(Math.min(23, Math.max(0, hour)));
  };

  const selectQuietTime = (field: "start" | "end") => {
    setQuietHoursEnabled(true);
    setActiveQuietTime(field);
  };

  const setSelectedQuietHour = (hour: string, field = activeQuietTime) => {
    if (field === "start") {
      setQuietStart(hour);
    } else {
      setQuietEnd(hour);
    }
  };

  useEffect(() => {
    if (!slugEdited) {
      setClientSlug(generateSlug(name));
    }
  }, [name, slugEdited]);

  useEffect(() => {
    // Check if we are resuming from OAuth
    const params = new URLSearchParams(window.location.search);
    if (params.get("step") === "2") {
      setStep(2);
      const pendingSignup = window.sessionStorage.getItem(PENDING_SIGNUP_KEY);
      if (pendingSignup) {
        try {
          const parsed = JSON.parse(pendingSignup);
          if (parsed.supabaseUserId) setSupabaseUserId(parsed.supabaseUserId);
          if (parsed.email) setEmail(parsed.email);
          if (parsed.name) setName(parsed.name);
        } catch {
          // Ignore invalid cached signup state.
        }
      }
      supabase.auth.getUser().then(({ data: { user } }) => {
        if (user) {
          setSupabaseUserId(user.id);
          if (user.email) setEmail(user.email);
          if (user.user_metadata?.full_name) setName(user.user_metadata.full_name);
        }
      });
    }

    const pendingApiKey = window.sessionStorage.getItem(PENDING_API_KEY_STORAGE);
    if (pendingApiKey) {
      try {
        const parsed = JSON.parse(pendingApiKey);
        if (parsed.apiKey) {
          setRevealedApiKey(parsed.apiKey);
          setApiKeyPrefix(parsed.apiKeyPrefix || null);
        }
      } catch {
        // Ignore invalid pending API key state.
      }
    }
  }, []);

  const persistPendingApiKey = (apiKey?: string | null, keyPrefix?: string | null) => {
    if (!apiKey) return;
    window.sessionStorage.setItem(
      PENDING_API_KEY_STORAGE,
      JSON.stringify({ apiKey, apiKeyPrefix: keyPrefix || null })
    );
    setRevealedApiKey(apiKey);
    setApiKeyPrefix(keyPrefix || null);
  };

  const clearPendingApiKey = () => {
    window.sessionStorage.removeItem(PENDING_API_KEY_STORAGE);
  };

  const handleProvisioningResponse = (data: any) => {
    if (data?.api_key) {
      persistPendingApiKey(data.api_key, data.api_key_prefix || null);
    }
    return data;
  };

  const handleCopyApiKey = async () => {
    if (!revealedApiKey) return;
    try {
      await navigator.clipboard.writeText(revealedApiKey);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  };

  const closeApiKeyModal = () => {
    setShowApiKeyModal(false);
    setCopyStatus("idle");
    clearPendingApiKey();
    navigate("/login");
  };

  const provisionClientProfile = async (payload: {
    name: string;
    supabase_uid: string;
    default_language?: string;
    preferred_channels?: string[];
    client_slug?: string;
    brand_color?: string;
    quiet_hours?: { start: string; end: string };
  }) => {
    const res = await fetch("/api/v1/clients/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: payload.name,
        default_language: payload.default_language ?? "en",
        preferred_channels: payload.preferred_channels,
        client_slug: payload.client_slug,
        brand_color: payload.brand_color,
        is_active: true,
        supabase_uid: payload.supabase_uid,
        quiet_hours: payload.quiet_hours,
      }),
    });

    if (!res.ok) {
      let message = `Failed to provision account profile (${res.status}).`;
      try {
        const err = await res.json();
        message = err.detail || err.message || message;
      } catch {
        // Keep fallback message.
      }
      throw new Error(message);
    }

    return handleProvisioningResponse(await res.json());
  };

  const handleNext = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
        setError("Passwords do not match.");
        return;
    }
    if (!agree) {
        setError("You must agree to the Terms & Conditions.");
        return;
    }
    
    setLoading(true);
    try {
      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: name,
          }
        }
      });

      if (authError) throw authError;

      if (data.user) {
        window.sessionStorage.setItem(
          PENDING_SIGNUP_KEY,
          JSON.stringify({
            supabaseUserId: data.user.id,
            email,
            name,
          })
        );
        setSupabaseUserId(data.user.id);
        setStep(2);
        try {
          await provisionClientProfile({
            name,
            supabase_uid: data.user.id,
            default_language: "en",
          });
        } catch (err: unknown) {
          setError(getErrorMessage(err, "Account created, but profile provisioning will be retried on the next step."));
        }
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to create account."));
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabaseUserId) {
        setError("Session lost. Please restart signup.");
        return;
    }
    
    setLoading(true);
    setError("");
    
    const preferred_channels = Object.keys(channels).filter(c => channels[c]);

    try {
      const provisioned = await provisionClientProfile({
        name,
        default_language: language,
        preferred_channels,
        client_slug: clientSlug || generateSlug(name),
        brand_color: brandColor,
        supabase_uid: supabaseUserId,
        quiet_hours: quietHoursEnabled ? { start: formatQuietHour(quietStart), end: formatQuietHour(quietEnd) } : undefined,
      });
      window.sessionStorage.removeItem(PENDING_SIGNUP_KEY);
      if (provisioned?.api_key || revealedApiKey) {
        if (provisioned?.api_key) {
          persistPendingApiKey(provisioned.api_key, provisioned.api_key_prefix || null);
        }
        setSuccess("Account provisioned successfully. Copy your API key before continuing.");
        setShowApiKeyModal(true);
        return;
      }
      setSuccess("Welcome aboard! Account provisioned. Routing you in 2 seconds...");
      setTimeout(() => navigate('/login'), 2000);
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Network error connecting to API."));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  };

  return (
    <div className="min-h-screen flex text-slate-900 bg-white selection:bg-indigo-600 selection:text-white">
      {/* Left side Form */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center px-8 sm:px-16 lg:px-24 xl:px-32 relative py-12">
        <Link to="/" className="absolute top-8 left-8 sm:left-12 font-bold text-xl tracking-tight flex items-center gap-2">
            <div className="w-8 h-8 flex items-center justify-center text-indigo-600 text-2xl">✦</div>
            Orchestrator
        </Link>
        
        <div className="max-w-md w-full mx-auto">
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 mb-2">Join Orchestrator 🤝</h2>
          <p className="text-slate-500 text-sm mb-8 leading-relaxed font-medium">
             {step === 1 ? "Start routing your notifications seamlessly. Register your organization below." : "Customize your routing preferences and quiet hour thresholds."}
          </p>

          {error && <div className="p-3 bg-red-50 text-red-700 text-sm font-medium rounded-md mb-6 border border-red-100">{error}</div>}
          {success && <div className="p-4 bg-indigo-50 text-indigo-800 text-sm font-medium rounded-md mb-6 border border-indigo-100">{success}</div>}

          {step === 1 && (
            <form onSubmit={handleNext} className="space-y-5">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Email Address</label>
                <div className="relative">
                   <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.206" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"></path></svg>
                   </span>
                   <input 
                     type="email" 
                     required 
                     value={email}
                     onChange={(e) => setEmail(e.target.value)}
                     className="block w-full pl-9 py-3 border border-slate-200 focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-all text-sm rounded-md placeholder-slate-400" 
                     placeholder="you@example.com"
                   />
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Client Name (Organization)</label>
                <div className="relative">
                   <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-bold">@</span>
                   <input 
                     type="text" 
                     required 
                     value={name}
                     onChange={(e) => setName(e.target.value)}
                     className="block w-full pl-9 py-3 border border-slate-200 focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-all text-sm rounded-md placeholder-slate-400" 
                     placeholder="Organization Name"
                   />
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Password</label>
                <div className="relative">
                   <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                   </span>
                   <input 
                     type="password" 
                     required
                     value={password}
                     onChange={(e) => setPassword(e.target.value)}
                     className="block w-full pl-9 py-3 border border-slate-200 focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-all text-sm rounded-md placeholder-slate-400" 
                     placeholder="Password (min. 8 character)"
                   />
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Confirm Password</label>
                <div className="relative">
                   <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 15v2m-6 4h12a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                   </span>
                   <input 
                     type="password" 
                     required
                     value={confirmPassword}
                     onChange={(e) => setConfirmPassword(e.target.value)}
                     className="block w-full pl-9 py-3 border border-slate-200 focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-all text-sm rounded-md placeholder-slate-400" 
                     placeholder="Retype password"
                   />
                </div>
              </div>

              <div className="flex items-center mt-2 mb-6">
                  <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-slate-300 rounded cursor-pointer accent-indigo-600" />
                  <label className="ml-2 block text-sm text-slate-600 font-medium">I agree to the <span className="text-indigo-600 font-bold">Terms & Conditions</span></label>
              </div>

              <button 
                type="submit" 
                className="w-full flex justify-center py-3.5 px-4 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none transition-all shadow-md hover:shadow-lg rounded-md"
              >
                Continue Setup &rarr;
              </button>
              
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200"></div></div>
                <div className="relative flex justify-center text-xs"><span className="px-2 bg-white text-slate-400 font-medium lowercase">or</span></div>
              </div>
              
              <button 
                type="button" 
                onClick={handleGoogleSignup}
                className="w-full flex justify-center items-center py-3.5 px-4 text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-all rounded-md shadow-sm gap-2"
              >
                  <svg className="w-4 h-4" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" /><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" /><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" /><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" /></svg>
                  Sign up with Google
              </button>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={handleSignup} className="space-y-6">
              <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                <div className="border-b border-slate-100 px-5 py-4">
                  <p className="text-sm font-bold text-slate-900">Basic Information</p>
                  <p className="mt-1 text-xs text-slate-500">Core client details and branding.</p>
                </div>
                <div className="space-y-4 px-5 py-5">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">Client Slug</label>
                    <input
                      type="text"
                      value={clientSlug}
                      onChange={(e) => {
                        setSlugEdited(true);
                        setClientSlug(generateSlug(e.target.value));
                      }}
                      className="block w-full py-3 px-4 border border-slate-200 focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-all text-sm rounded-md placeholder-slate-400"
                      placeholder="acme-technologies"
                    />
                    <p className="mt-1 text-xs text-slate-400">URL-friendly identifier for your client workspace.</p>
                  </div>

                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">Brand Color</label>
                    <div className="flex items-center gap-3">
                      <input
                        type="color"
                        value={brandColor}
                        onChange={(e) => setBrandColor(e.target.value)}
                        className="h-11 w-14 cursor-pointer rounded-md border border-slate-200 bg-white p-1"
                      />
                      <div className="h-11 w-11 rounded-md border border-slate-200" style={{ backgroundColor: brandColor }} />
                      <span className="text-sm font-mono text-slate-500">{brandColor}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Quiet Hours Settings</label>
                <div className="bg-slate-50 p-4 border border-slate-200 flex flex-col space-y-4 rounded-md">
                   <label className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-4 py-3">
                      <span className="text-sm font-semibold text-slate-700">Enable quiet hours for this client</span>
                      <input
                        type="checkbox"
                        checked={quietHoursEnabled}
                        onChange={(e) => setQuietHoursEnabled(e.target.checked)}
                        className="h-4 w-4 rounded accent-indigo-600"
                      />
                   </label>
                   <div>
                      <div className="mb-3 grid grid-cols-2 gap-3">
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => selectQuietTime("start")}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              selectQuietTime("start");
                            }
                          }}
                          className={`rounded-md border px-3 py-2 text-left transition-colors ${activeQuietTime === "start" ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}
                        >
                          <span className="block text-xs font-bold text-slate-500">Start Time (24h)</span>
                          <input
                            type="time"
                            step="3600"
                            value={formatQuietHour(quietStart)}
                            onFocus={() => selectQuietTime("start")}
                            onChange={(event) => setSelectedQuietHour(parseQuietHour(event.target.value), "start")}
                            className="mt-1 w-full bg-transparent text-sm font-bold outline-none"
                          />
                        </div>
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => selectQuietTime("end")}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              selectQuietTime("end");
                            }
                          }}
                          className={`rounded-md border px-3 py-2 text-left transition-colors ${activeQuietTime === "end" ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}
                        >
                          <span className="block text-xs font-bold text-slate-500">End Time (24h)</span>
                          <input
                            type="time"
                            step="3600"
                            value={formatQuietHour(quietEnd)}
                            onFocus={() => selectQuietTime("end")}
                            onChange={(event) => setSelectedQuietHour(parseQuietHour(event.target.value), "end")}
                            className="mt-1 w-full bg-transparent text-sm font-bold outline-none"
                          />
                        </div>
                      </div>
                      <div className="flex justify-between text-xs font-bold text-slate-500 mb-2">
                          <span>{activeQuietTime === "start" ? "Adjust start time" : "Adjust end time"}</span>
                          <span className="text-indigo-600">{formatQuietHour(activeQuietTime === "start" ? quietStart : quietEnd)}</span>
                      </div>
                      <input
                        type="range"
                        min="0"
                        max="23"
                        value={activeQuietTime === "start" ? quietStart : quietEnd}
                        onChange={e => setSelectedQuietHour(e.target.value)}
                        disabled={!quietHoursEnabled}
                        className="w-full accent-indigo-600 disabled:opacity-40"
                      />
                   </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-3">Preferred Output Channels</label>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {availableChannels.map((ch) => (
                    <label key={ch} className={`flex items-center space-x-3 p-3 border rounded-md cursor-pointer transition-colors ${channels[ch] ? 'border-indigo-600 bg-indigo-50/30' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
                      <input type="checkbox" checked={channels[ch]} onChange={() => setChannels({...channels, [ch]: !channels[ch]})} className="h-4 w-4 text-indigo-600 rounded accent-indigo-600" />
                      <span className="text-sm font-bold text-slate-700 capitalize">{ch}</span>
                    </label>
                  ))}
                </div>
                <p className="mt-2 text-xs text-slate-400">Select the channels your client should use by default.</p>
              </div>

              <div>
                 <label className="block text-sm font-bold text-slate-700 mb-1.5">Agent Default Localization</label>
                 <select value={language} onChange={e=>setLanguage(e.target.value)} className="w-full py-3 px-4 bg-slate-50 border border-slate-200 text-sm font-medium rounded-md focus:outline-none focus:border-indigo-600">
                    <option value="en">English (US)</option>
                    <option value="hi">Hindi</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                 </select>
              </div>

              <div className="flex space-x-4 pt-4 border-t border-slate-100">
                  <button type="button" onClick={() => setStep(1)} className="w-1/3 py-3.5 px-4 text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-all rounded-md shadow-sm">
                      Back
                  </button>
                  <button type="submit" disabled={loading} className="w-2/3 py-3.5 px-4 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none transition-all shadow-md hover:shadow-lg disabled:opacity-50 rounded-md">
                      {loading ? 'Processing...' : 'Complete Signup'}
                  </button>
              </div>
            </form>
          )}

          {step === 1 && (
              <div className="mt-8 text-center text-sm font-medium">
                <span className="text-slate-500">Already have an account? </span>
                <Link to="/login" className="text-indigo-600 hover:text-indigo-800 font-bold">Login now</Link>
              </div>
          )}
        </div>
      </div>

      {/* Right side Info Block */}
      <div className="hidden lg:flex w-1/2 bg-slate-50 relative items-center justify-center p-12 overflow-hidden">
         <div className="absolute top-[10%] left-[10%] w-[60%] h-[60%] rounded-full bg-blue-100 opacity-60 blur-3xl pointer-events-none"></div>
         
         <div className="relative z-10 w-full max-w-lg">
             <div className="bg-white rounded-xl shadow-2xl p-6 mb-8 border border-white/50 relative transform -rotate-1 hover:rotate-0 transition-transform duration-500">
                 <div className="flex justify-between items-center mb-6">
                    <h4 className="font-extrabold text-slate-900">Traffic Sources</h4>
                    <span className="text-xs font-bold text-slate-400">Last 7 Days &darr;</span>
                 </div>
                 <div className="space-y-4">
                     <div>
                        <div className="flex justify-between text-xs font-bold text-slate-500 mb-2">
                             <span>Direct</span><span>1,43,382</span>
                        </div>
                        <div className="w-full bg-slate-100 h-1.5 rounded-full"><div className="bg-indigo-500 h-full rounded-full w-[80%]"></div></div>
                     </div>
                     <div>
                        <div className="flex justify-between text-xs font-bold text-slate-500 mb-2">
                             <span>Referral</span><span>84,120</span>
                        </div>
                        <div className="w-full bg-slate-100 h-1.5 rounded-full"><div className="bg-indigo-300 h-full rounded-full w-[40%]"></div></div>
                     </div>
                 </div>
             </div>

             <div className="text-center mt-12 bg-white/50 backdrop-blur-sm py-6 rounded-2xl border border-white/50">
                 <h3 className="text-2xl font-extrabold text-slate-900 mb-3">92+ Ready Coded Blocks</h3>
                 <p className="text-sm text-slate-500 font-medium leading-relaxed px-6">
                    Enjoy out of the box AI orchestration integrations and immediate cross-channel distribution protocols natively.
                 </p>
                 <div className="flex justify-center space-x-2 mt-6">
                     <span className="w-2 h-2 rounded-full bg-slate-800"></span>
                     <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                     <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                 </div>
             </div>
         </div>
      </div>

      {showApiKeyModal && revealedApiKey ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-6">
          <div className="w-full max-w-xl rounded-[28px] border border-slate-200 bg-white p-7 shadow-2xl">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-indigo-500">One-Time API Key</p>
            <h3 className="text-2xl font-extrabold tracking-tight text-slate-950">Copy this key now</h3>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              This is the only time the full API key will be shown. Save it somewhere secure before continuing.
            </p>

            <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              {apiKeyPrefix ? (
                <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Prefix: {apiKeyPrefix}</p>
              ) : null}
              <pre className="whitespace-pre-wrap break-all text-sm font-semibold text-slate-900">{revealedApiKey}</pre>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleCopyApiKey}
                className="rounded-2xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-indigo-700"
              >
                Copy API Key
              </button>
              <button
                type="button"
                onClick={closeApiKeyModal}
                className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
              >
                I have saved it
              </button>
            </div>

            {copyStatus === "copied" ? (
              <p className="mt-3 text-sm font-semibold text-emerald-600">API key copied to clipboard.</p>
            ) : null}
            {copyStatus === "failed" ? (
              <p className="mt-3 text-sm font-semibold text-red-600">Clipboard copy failed. Please copy it manually.</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
