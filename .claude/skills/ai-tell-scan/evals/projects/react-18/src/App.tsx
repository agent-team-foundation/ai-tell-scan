export function App() {
  return (
    <main>
      <h1>Motion response playground</h1>
      <p>Compare the same scale response across four control shapes.</p>
      <button type="button" className="transition-all hover:scale-105">
        Compact
      </button>
      <button type="button" className="transition-all hover:scale-105">
        Standard
      </button>
      <button type="button" className="transition-all hover:scale-105">
        Wide
      </button>
      <button type="button" className="transition-all hover:scale-105">
        Square
      </button>
    </main>
  );
}
