"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { clientPortalUrl } from "@/lib/client-routes";
import { ensureClientProfile } from "@/lib/clientProvisioning";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const getErrorMessage = (err: unknown, fallback: string) => {
    if (err instanceof Error && err.message) {
      return err.message;
    }
    return fallback;
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const { data: authData, error: authError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (authError) throw authError;

      if (authData.user) {
        const clientData = await ensureClientProfile(authData.user);
        localStorage.setItem("access_token", authData.session?.access_token || "");
        localStorage.setItem("client_id", clientData.id.toString());
        router.push(clientPortalUrl(clientData.client_slug || clientData.id));
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Invalid login credentials"));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
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
      <div className="w-full lg:w-1/2 flex flex-col justify-center px-8 sm:px-16 lg:px-24 xl:px-32 relative">
        <Link href="/" className="absolute top-8 left-8 sm:left-12 font-bold text-xl tracking-tight flex items-center gap-2">
            <div className="w-8 h-8 flex items-center justify-center text-indigo-600 text-2xl">
                ✦
            </div>
            Orchestrator
        </Link>
        
        <div className="max-w-md w-full mx-auto">
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 mb-2">Welcome Back 🤝</h2>
          <p className="text-slate-500 text-sm mb-8 leading-relaxed font-medium">
            Enter your Client Name to securely access your intelligent orchestration dashboard.
          </p>

          {error && (
            <div className="p-3 bg-red-50 text-red-700 text-sm font-medium rounded-md mb-6 border border-red-100">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-5">
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
              <label className="block text-sm font-bold text-slate-700 mb-1.5">Password</label>
              <div className="relative">
                 <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                 </span>
                 <input 
                   type="password" 
                   value={password}
                   onChange={(e) => setPassword(e.target.value)}
                   className="block w-full pl-9 py-3 border border-slate-200 focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-all text-sm rounded-md placeholder-slate-400" 
                   placeholder="Password (dev bypass active)"
                 />
              </div>
            </div>

            <div className="flex items-center mt-2 mb-6">
                <input type="checkbox" className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-slate-300 rounded cursor-pointer accent-indigo-600" />
                <label className="ml-2 block text-sm text-slate-600 font-medium">Keep me logged in</label>
            </div>

            <button 
              type="submit" 
              disabled={loading}
              className="w-full flex justify-center py-3.5 px-4 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none transition-all shadow-md hover:shadow-lg disabled:opacity-50 rounded-md"
            >
              {loading ? 'Authenticating...' : 'Sign in'}
            </button>
            
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200"></div></div>
              <div className="relative flex justify-center text-xs"><span className="px-2 bg-white text-slate-400 font-medium lowercase">or</span></div>
            </div>
            
            <button 
              type="button" 
              onClick={handleGoogleLogin}
              className="w-full flex justify-center items-center py-3.5 px-4 text-sm font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-all rounded-md shadow-sm gap-2"
            >
                <svg className="w-4 h-4" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" /><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" /><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" /><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" /></svg>
                Sign in with Google
            </button>
          </form>
          
          <div className="mt-8 text-center text-sm font-medium">
             <span className="text-slate-500">Don&apos;t have an account? </span>
             <Link href="/signup" className="text-indigo-600 hover:text-indigo-800 font-bold">Signup now</Link>
          </div>
        </div>
      </div>

      {/* Right side Info Block */}
      <div className="hidden lg:flex w-1/2 bg-slate-50 relative items-center justify-center p-12 overflow-hidden">
         {/* Decorative blurred background shapes matching landing page */}
         <div className="absolute top-[10%] left-[10%] w-[60%] h-[60%] rounded-full bg-blue-100 opacity-60 blur-3xl pointer-events-none"></div>
         
         <div className="relative z-10 w-full max-w-lg">
             <div className="bg-white rounded-xl shadow-2xl p-6 mb-8 border border-white/50 relative transform rotate-1 hover:rotate-0 transition-transform duration-500">
                <div className="flex items-center space-x-3 mb-6 border-b border-slate-100 pb-4">
                    <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center font-bold text-indigo-700">A</div>
                    <div>
                        <h4 className="text-sm font-bold text-slate-900">Hey Acme 👋</h4>
                        <p className="text-xs text-slate-500">Here&apos;s your outbound communication snapshot today</p>
                    </div>
                </div>
                <div className="flex border-b border-slate-100 pb-6 mb-6">
                    <div className="flex-1">
                        <p className="text-3xl font-extrabold text-slate-900">83</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Active Endpoints</p>
                    </div>
                    <div className="flex-1 pl-4 border-l border-slate-100">
                        <p className="text-3xl font-extrabold text-slate-900">14k</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Transmissions</p>
                    </div>
                </div>
                <ul className="space-y-3 text-xs font-semibold text-slate-600">
                    <li className="flex items-center"><span className="w-1.5 h-1.5 rounded-full bg-indigo-600 mr-2"></span> 8 new priority alerts routed</li>
                    <li className="flex items-center"><span className="w-1.5 h-1.5 rounded-full bg-indigo-600 mr-2"></span> Email bounce rate decreased by 1.2%</li>
                </ul>
             </div>

             <div className="text-center mt-12 bg-white/50 backdrop-blur-sm py-6 rounded-2xl border border-white/50">
                 <h3 className="text-2xl font-extrabold text-slate-900 mb-3">Enterprise Grade Routing</h3>
                 <p className="text-sm text-slate-500 font-medium leading-relaxed px-6">
                    Leverage multi-channel failover to confidently deliver your payloads globally.
                 </p>
                 <div className="flex justify-center space-x-2 mt-6">
                     <span className="w-2 h-2 rounded-full bg-slate-800"></span>
                     <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                     <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                 </div>
             </div>
         </div>
      </div>
    </div>
  );
}
