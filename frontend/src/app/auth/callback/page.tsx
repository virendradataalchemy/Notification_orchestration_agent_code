"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    const handleCallback = async () => {
      const { data: { session }, error } = await supabase.auth.getSession();
      
      if (error || !session) {
        router.push("/login?error=Session initialization failed");
        return;
      }

      const user = session.user;
      
      // Check if user has a tenant profile
      try {
        const res = await fetch(`/api/v1/clients/by-supabase/${user.id}`);
        if (res.ok) {
           const tenantData = await res.json();
           localStorage.setItem("access_token", session.access_token);
           localStorage.setItem("client_id", tenantData.id.toString());
           router.push(`/client/${tenantData.id}`);
        } else {
           // New user from OAuth - redirect to complete setup (Step 2)
           // We might need to store the user id temp or just rely on supabase.auth.getUser() on the signup page
           router.push("/signup?step=2");
        }
      } catch (err) {
        router.push("/login?error=Backend sync failed");
      }
    };

    handleCallback();
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-sm font-bold text-slate-500 uppercase tracking-widest">Finalizing Session...</p>
      </div>
    </div>
  );
}
