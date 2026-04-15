import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { clientPortalUrl } from "@/lib/client-routes";
import { supabase } from "@/lib/supabase";
import { ensureClientProfile } from "@/lib/clientProvisioning";

export default function AuthCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const handleCallback = async () => {
      const { data: { session }, error } = await supabase.auth.getSession();
      
      if (error || !session) {
        navigate("/login?error=Session initialization failed");
        return;
      }

      const user = session.user;
      
      try {
        const clientData = await ensureClientProfile(user);
        localStorage.setItem("access_token", session.access_token);
        localStorage.setItem("client_id", clientData.id.toString());
        navigate(clientPortalUrl(clientData.client_slug || clientData.id));
      } catch {
        navigate("/login?error=Backend sync failed while provisioning client profile");
      }
    };

    handleCallback();
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-sm font-bold text-slate-500 uppercase tracking-widest">Finalizing Session...</p>
      </div>
    </div>
  );
}
