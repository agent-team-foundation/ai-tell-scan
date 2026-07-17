export function App() {
  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center py-24 text-center">
      <div className="absolute inset-x-20 top-10 h-64 bg-gradient-to-r from-purple-500 to-blue-500 blur-3xl" />
      <h1 className="text-6xl font-bold">A calmer release day</h1>
      <a href="/start" className="mt-8 rounded-lg px-5 py-3">
        Start now
      </a>
    </section>
  );
}
