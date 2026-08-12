import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { LapTimeChart } from "@/components/LapTimeChart";

export const dynamic = "force-dynamic";

export default async function ResultsPage({ params }: { params: { id: string } }) {
  const raceId = Number(params.id);
  if (Number.isNaN(raceId)) notFound();

  let race;
  let results;
  try {
    race = await api.getRace(raceId);
    results = await api.getRaceResults(raceId);
  } catch {
    notFound();
  }
  if (!race || !results) notFound();

  const driverCodes = results.map((r) => r.driver_code).filter((c): c is string => c !== null);

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <Link
        href={`/races/${raceId}`}
        className="font-mono text-xs uppercase tracking-wider text-muted hover:text-fastest"
      >
        &larr; Back to timing tower
      </Link>

      <header className="mb-8 mt-4 border-b border-border pb-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
          {race.season} &middot; Round {race.round} &middot; {race.circuit_name}
        </p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-text md:text-5xl">
          Results
        </h1>
      </header>

      <div className="panel mb-6 overflow-hidden">
        <div className="grid grid-cols-[3rem_5rem_1fr_4rem_1fr_4rem] gap-2 border-b border-border px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-muted">
          <span>Pos</span>
          <span>Driver</span>
          <span>Team</span>
          <span className="text-right">Grid</span>
          <span>Status</span>
          <span className="text-right">Pts</span>
        </div>
        {results.map((r, i) => (
          <div
            key={i}
            className="grid grid-cols-[3rem_5rem_1fr_4rem_1fr_4rem] items-center gap-2 border-b border-border/50 px-4 py-2 last:border-b-0 hover:bg-surfaceRaised"
          >
            <span className="font-display text-lg font-semibold tabular-nums text-text">
              {r.finish_position ?? "—"}
            </span>
            <span className="font-mono text-sm font-medium text-text">{r.driver_code ?? "—"}</span>
            <span className="font-body text-sm text-muted">{r.constructor_name ?? "—"}</span>
            <span className="text-right font-mono text-sm tabular-nums text-muted">
              {r.grid_position ?? "—"}
            </span>
            <span className="font-mono text-xs text-muted">{r.status ?? "—"}</span>
            <span className="text-right font-mono text-sm tabular-nums text-text">
              {r.points ?? 0}
            </span>
          </div>
        ))}
      </div>

      {driverCodes.length > 0 && <LapTimeChart raceId={raceId} driverCodes={driverCodes} />}
    </main>
  );
}