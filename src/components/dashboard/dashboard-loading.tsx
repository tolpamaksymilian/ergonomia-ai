export function DashboardLoading() {
  return <div className="dashboard-page animate-pulse" aria-busy="true" aria-label="Ładowanie panelu">
    <div className="h-8 w-56 rounded-lg bg-surface-muted" />
    <div className="h-4 w-full max-w-xl rounded bg-surface-muted" />
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <div key={index} className="dashboard-card h-32 bg-surface-muted/60" />)}</div>
    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.6fr]"><div className="dashboard-card h-80 bg-surface-muted/60" /><div className="dashboard-card h-80 bg-surface-muted/60" /></div>
  </div>;
}
