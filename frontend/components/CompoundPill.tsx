const COMPOUND_STYLES: Record<string, string> = {
  SOFT: "bg-soft/20 text-soft border border-soft/40",
  MEDIUM: "bg-medium/20 text-medium border border-medium/40",
  HARD: "bg-hard/10 text-hard border border-hard/30",
  INTERMEDIATE: "bg-intermediate/20 text-intermediate border border-intermediate/40",
  WET: "bg-wet/20 text-wet border border-wet/40",
};

const COMPOUND_LABELS: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
  INTERMEDIATE: "I",
  WET: "W",
};

export function CompoundPill({ compound }: { compound: string | null }) {
  if (!compound) {
    return <span className="compound-pill bg-surfaceRaised text-muted border border-border">—</span>;
  }
  const style = COMPOUND_STYLES[compound] ?? "bg-surfaceRaised text-muted border border-border";
  const label = COMPOUND_LABELS[compound] ?? compound.slice(0, 1);
  return (
    <span className={`compound-pill ${style}`} title={compound}>
      {label}
    </span>
  );
}