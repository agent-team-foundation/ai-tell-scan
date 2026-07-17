const tags = ["React", "Next.js", "TypeScript", "CSS", "Testing", "Design", "Docs", "Open source"];

export default function Page() {
  return (
    <main>
      {tags.map((tag) => (
        <span className="rounded-full px-3 py-1 text-xs" key={tag}>
          {tag}
        </span>
      ))}
    </main>
  );
}
