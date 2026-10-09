export function Placeholder({ title, phase }: { title: string; phase: number }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-slate-500">Built in Phase {phase}.</p>
    </div>
  );
}
