export default function Page() {
  return (
    <main>
      <nav className="sticky top-4 rounded-full border bg-white/80 px-6 py-3 shadow backdrop-blur-lg">
        <a href="/home" className="rounded-full px-5 py-2">
          Home
        </a>
        <button type="button" className="rounded-full px-5 py-2">
          Join
        </button>
      </nav>
      <input className="rounded-full px-5 py-3" aria-label="Search" />
      <span className="rounded-full px-3 py-1 text-xs">New</span>
      <span className="rounded-full px-3 py-1 text-xs">Open</span>
      <div className="h-4 w-4 rounded-full bg-green-500" />
      <div className="h-10 w-10 rounded-full bg-gray-200" />
    </main>
  );
}
