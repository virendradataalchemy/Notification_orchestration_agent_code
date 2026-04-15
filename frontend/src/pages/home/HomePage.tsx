import { Link } from "react-router-dom";

export default function HomePage() {
  return (
    <div className="min-h-[100vh] flex flex-col text-slate-900 selection:bg-indigo-600 selection:text-white relative overflow-hidden bg-white">
      
      {/* Decorative background shapes */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-blue-50 opacity-70 blur-3xl pointer-events-none"></div>
      <div className="absolute top-[20%] right-[-5%] w-[35%] h-[35%] rounded-full bg-indigo-50 opacity-70 blur-3xl pointer-events-none"></div>
      
      <header className="flex items-center justify-between px-8 py-6 relative z-20 w-full">
        <div className="flex items-center space-x-3 font-bold text-xl tracking-tight">
          <div className="w-8 h-8 flex items-center justify-center text-indigo-600 text-2xl">
             ✦
          </div>
          <span className="text-xl font-bold font-sans tracking-tight">Orchestrator</span>
        </div>
        <div className="space-x-4">
          <Link
            to="/admin"
            className="relative z-20 rounded-md px-3 py-2 text-sm font-semibold text-slate-600 transition-all hover:text-indigo-600 hover:bg-slate-50"
          >
            Admin Login
          </Link>
        </div>
      </header>

      <main className="flex-grow flex flex-col items-center justify-center px-6 relative z-10">
        <div className="text-center max-w-4xl mx-auto space-y-8">
           <span className="inline-block text-xs font-bold text-indigo-600 uppercase tracking-widest bg-indigo-50 px-4 py-1.5 rounded-full mb-4">
              Enterprise Notification System
           </span>
           <h1 className="text-5xl sm:text-7xl font-extrabold tracking-tight text-slate-900 leading-[1.1]">
             Multi Tenant <br className="hidden sm:block" /> Orchestration System
           </h1>
           <p className="text-lg text-slate-500 leading-relaxed max-w-2xl mx-auto font-medium mb-8">
             Manage communication workflows for multiple clients from one clean and simple platform.
           </p>
           
           <div className="pt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to="/login" className="px-8 py-3.5 bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-all shadow-md hover:shadow-lg rounded-md min-w-[200px]">
                Client Login
              </Link>
              <Link to="/signup" className="px-8 py-3.5 bg-white text-slate-700 text-sm font-semibold hover:bg-slate-50 transition-all border border-slate-200 shadow-sm rounded-md min-w-[200px]">
                Signup as Client
              </Link>
           </div>
        </div>
      </main>

    </div>
  );
}
