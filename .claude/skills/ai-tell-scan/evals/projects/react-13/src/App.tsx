import { BookIcon, CodeIcon, RocketIcon } from "lucide-react";

export function App() {
  return (
    <section className="grid grid-cols-3 gap-6">
      <article className="rounded-2xl border border-blue-200 bg-blue-50 p-6 text-blue-900 shadow-sm">
        <div className="h-10 w-10 rounded-lg bg-blue-100 text-blue-700">
          <BookIcon />
        </div>
        <h3>Learn</h3>
        <p>Read the guide.</p>
      </article>
      <article className="rounded-2xl border border-violet-200 bg-violet-50 p-6 text-violet-900 shadow-sm">
        <div className="h-10 w-10 rounded-lg bg-violet-100 text-violet-700">
          <CodeIcon />
        </div>
        <h3>Build</h3>
        <p>Connect the code.</p>
      </article>
      <article className="rounded-2xl border border-orange-200 bg-orange-50 p-6 text-orange-900 shadow-sm">
        <div className="h-10 w-10 rounded-lg bg-orange-100 text-orange-700">
          <RocketIcon />
        </div>
        <h3>Launch</h3>
        <p>Share the result.</p>
      </article>
    </section>
  );
}
