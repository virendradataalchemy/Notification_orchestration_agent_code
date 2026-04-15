import { Outlet, useParams } from "react-router-dom";

export default function ClientLayout() {
  const { id: clientId } = useParams();

  if (!clientId) return null;

  return (
    <div className="min-h-screen bg-white text-slate-900 selection:bg-slate-900 selection:text-white">
      <Outlet />
    </div>
  );
}
