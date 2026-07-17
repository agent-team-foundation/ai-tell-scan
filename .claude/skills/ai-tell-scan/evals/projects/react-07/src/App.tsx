export function App() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 to-indigo-950 p-12">
      <h1 className="text-5xl">One place for launch work</h1>
      <button type="button">Open workspace</button>
      <div className="mt-12 grid grid-cols-2 gap-6">
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">Roadmap</section>
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">Reviews</section>
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">Decisions</section>
        <section className="rounded-2xl border bg-white/10 p-6 shadow backdrop-blur-xl">Releases</section>
      </div>
    </main>
  );
}
