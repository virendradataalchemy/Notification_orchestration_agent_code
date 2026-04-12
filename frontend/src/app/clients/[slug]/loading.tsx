export default function Loading() {
  return (
    <div className="min-h-screen bg-white">
      {/* Header skeleton */}
      <div className="sticky top-0 z-40 border-b border-slate-200 bg-white shadow-sm">
        <div className="flex w-full items-center justify-between gap-4 px-6 py-4 xl:px-10">
          <div className="flex items-center gap-6">
            <div className="h-5 w-28 animate-pulse rounded bg-slate-200" />
            <div className="hidden gap-2 md:flex">
              {[80, 72, 96, 80, 72].map((w, i) => (
                <div key={i} className={`h-7 w-${w} animate-pulse rounded-full bg-slate-100`} style={{ width: w }} />
              ))}
            </div>
          </div>
          <div className="h-7 w-20 animate-pulse rounded-full bg-slate-100" />
        </div>
      </div>

      {/* Content skeleton */}
      <main className="w-full px-6 py-8 xl:px-10">
        <div className="mb-6 rounded-[28px] border border-slate-200 bg-white px-7 py-7 shadow-sm">
          <div className="h-8 w-64 animate-pulse rounded bg-slate-200" />
          <div className="mt-3 h-4 w-96 animate-pulse rounded bg-slate-100" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-48 animate-pulse rounded-[28px] border border-slate-200 bg-slate-50" />
          ))}
        </div>
      </main>
    </div>
  );
}
