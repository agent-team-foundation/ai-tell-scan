export default function Page() {
  return (
    <section className="grid grid-cols-3 gap-6">
      <article className="rounded-2xl border p-6 shadow-sm">
        <h3>Solo</h3>
        <p>For one maker.</p>
      </article>
      <article className="rounded-2xl border p-6 shadow-sm">
        <h3>Team</h3>
        <p>For a small team.</p>
      </article>
      <article className="rounded-2xl border p-6 shadow-sm">
        <h3>Studio</h3>
        <p>For several products.</p>
      </article>
    </section>
  );
}
