export default function Page() {
  return (
    <main>
      <button type="button" className="rounded-full px-6 py-3">
        Start
      </button>
      <a href="/docs" className="rounded-full px-6 py-3">
        Docs
      </a>
      <input className="rounded-full px-5 py-3" placeholder="Search" />
      <span className="rounded-full px-3 py-1 text-xs">Beta</span>
      <span className="rounded-full px-3 py-1 text-xs">Local</span>
      <div className="h-4 w-4 rounded-full bg-green-500" />
      <div className="h-8 w-8 rounded-full bg-slate-200" />
    </main>
  );
}
