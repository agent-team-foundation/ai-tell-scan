export function App() {
  return (
    <nav>
      <a href="/one" className="rounded-lg transition-all hover:scale-105">
        One
      </a>
      <a href="/two" className="rounded-lg transition-all hover:scale-105">
        Two
      </a>
      <button type="button" className="rounded-lg transition-all hover:-translate-y-1">
        Three
      </button>
      <button type="button" className="rounded-lg transition-all hover:scale-105">
        Four
      </button>
    </nav>
  );
}
