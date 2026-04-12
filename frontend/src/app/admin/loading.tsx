export default function Loading() {
  return (
    <div className="min-h-screen bg-white pb-12">
      <div className="sticky top-0 z-40 border-b border-slate-200 bg-white h-16 flex items-center px-6">
        <div className="h-5 w-40 animate-pulse rounded bg-slate-200" />
      </div>
      <main className="max-w-7xl mx-auto px-6 mt-12">
        <div className="mb-10 rounded-[32px] border border-slate-200 bg-white px-8 py-8">
          <div className="h-8 w-56 animate-pulse rounded bg-slate-200 mb-3" />
          <div className="h-4 w-80 animate-pulse rounded bg-slate-100" />
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-60 animate-pulse rounded-[30px] border border-slate-200 bg-slate-50" />
          ))}
        </div>
      </main>
    </div>
  );
}
