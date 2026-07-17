export default function Page() {
  return (
    <section className="grid grid-cols-3 gap-6">
      <article className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-emerald-900">
        <h3>Plan</h3>
      </article>
      <article className="rounded-2xl border border-violet-200 bg-violet-50 p-6 text-violet-900">
        <h3>Build</h3>
      </article>
      <article className="rounded-2xl border border-orange-200 bg-orange-50 p-6 text-orange-900">
        <h3>Ship</h3>
      </article>
    </section>
  );
}
