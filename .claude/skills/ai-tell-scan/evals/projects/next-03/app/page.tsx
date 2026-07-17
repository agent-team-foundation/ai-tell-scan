export default function Page() {
  return (
    <main>
      <nav className="fixed top-6 left-1/2 rounded-full border bg-white/70 px-6 py-3 shadow-lg backdrop-blur-xl">
        <a href="/docs">Docs</a>
        <a href="/signup" className="ml-6">
          Join
        </a>
      </nav>
      <h1 className="pt-40 text-5xl">A focused workspace</h1>
    </main>
  );
}
