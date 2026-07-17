export function App() {
  return (
    <main className="bg-gradient-to-br from-slate-950 to-purple-950 p-12">
      <h1>Choose your next release</h1>
      <button type="button">Open</button>
      <div className="grid grid-cols-2 gap-6">
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">
          <button type="button" className="transition-all hover:scale-105">
            Plan
          </button>
        </section>
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">
          <button type="button" className="transition-all hover:scale-105">
            Build
          </button>
        </section>
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">
          <button type="button" className="transition-all hover:-translate-y-1">
            Review
          </button>
        </section>
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">
          <button type="button" className="transition-all hover:scale-105">
            Ship
          </button>
        </section>
      </div>
    </main>
  );
}
