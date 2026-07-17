export function App() {
  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center py-32 text-center">
      <div className="absolute top-8 h-72 w-72 bg-gradient-to-r from-indigo-500 to-pink-500 blur-3xl" />
      <h1 className="bg-gradient-to-r from-blue-500 via-violet-500 to-pink-500 bg-clip-text text-7xl font-bold text-transparent">
        Build what matters
      </h1>
      <a href="/start">Get started</a>
    </section>
  );
}
