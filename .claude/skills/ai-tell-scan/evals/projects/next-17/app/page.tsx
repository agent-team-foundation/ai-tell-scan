export default function Page() {
  return (
    <main>
      <h1>Quarterly reliability study</h1>
      <section aria-label="Audited Q2 2026 results" className="grid grid-cols-3 text-center">
        <div>
          <strong>64k+</strong>
          <span>anonymized sessions</span>
        </div>
        <div>
          <strong>98%</strong>
          <span>task completion</span>
        </div>
        <div>
          <strong>7x</strong>
          <span>median throughput</span>
        </div>
      </section>
      <p>
        Audited 30 June 2026. <a href="/research/q2-2026-methodology">Read the sample and methodology</a>.
      </p>
    </main>
  );
}
