export default function Page() {
  return (
    <section className="flex gap-4">
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">Healthy</div>
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-900">Waiting</div>
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-900">Failed</div>
    </section>
  );
}
