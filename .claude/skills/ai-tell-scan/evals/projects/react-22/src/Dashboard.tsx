export function Dashboard() {
  return (
    <main className="bg-gradient-to-br from-slate-950 to-blue-950 p-8">
      <h1>Analytics dashboard</h1>
      <button type="button">Export</button>
      <section className="grid grid-cols-2 gap-4">
        <div className="rounded-2xl border bg-white/10 p-4 shadow backdrop-blur-xl">Revenue chart</div>
        <div className="rounded-2xl border bg-white/10 p-4 shadow backdrop-blur-xl">Active users</div>
        <div className="rounded-2xl border bg-white/10 p-4 shadow backdrop-blur-xl">Retention table</div>
        <div className="rounded-2xl border bg-white/10 p-4 shadow backdrop-blur-xl">Error rate</div>
      </section>
    </main>
  );
}
