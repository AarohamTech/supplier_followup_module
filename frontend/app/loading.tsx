export default function Loading() {
  return (
    <div className="page-stack" aria-busy="true" aria-live="polite">
      <div className="page-header">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 animate-pulse rounded-lg bg-red-50" />
          <div className="space-y-2">
            <div className="h-4 w-40 animate-pulse rounded bg-gray-200" />
            <div className="h-3 w-72 max-w-[60vw] animate-pulse rounded bg-gray-100" />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="card h-28 animate-pulse bg-white" />
        <div className="card h-28 animate-pulse bg-white" />
        <div className="card h-28 animate-pulse bg-white" />
      </div>
      <div className="card h-80 animate-pulse bg-white" />
    </div>
  );
}
