import { GaugeIcon, RocketIcon, ShieldIcon } from "lucide-react";

export function App() {
  return (
    <section className="grid grid-cols-3 gap-6">
      <article className="rounded-2xl border p-6 shadow-sm">
        <div className="h-10 w-10 rounded-lg bg-blue-100 text-blue-700">
          <RocketIcon />
        </div>
        <h3>Fast setup</h3>
        <p>Start in one command.</p>
      </article>
      <article className="rounded-2xl border p-6 shadow-sm">
        <div className="h-10 w-10 rounded-lg bg-purple-100 text-purple-700">
          <ShieldIcon />
        </div>
        <h3>Safe defaults</h3>
        <p>Review every sensitive action.</p>
      </article>
      <article className="rounded-2xl border p-6 shadow-sm">
        <div className="h-10 w-10 rounded-lg bg-emerald-100 text-emerald-700">
          <GaugeIcon />
        </div>
        <h3>Clear progress</h3>
        <p>See what changed and why.</p>
      </article>
    </section>
  );
}
