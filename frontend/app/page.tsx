import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic"; // always fetch fresh data, this is a live tool not a static site

export default async function HomePage() {
  let races;
  let error: string | null = null;
  try {
    races = await api.listRaces();
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load races.";
  }

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <header className="mb-10 border-b border-border pb-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">Race Strategy Platform</p>
        <h1 className="font-display text-5xl font-semibold tracking-tight text-text md:text-6xl">
          F1RaceOps
        </h1>
        <p className="mt-2 max-w-xl font-body text-sm text-muted">
          Real telemetry, validated tire models, and a Monte Carlo pit-strategy simulator.
          Pick a race to see the timing tower or run a strategy simulation.
        </p>
      </header>

      {error && (
        <div className="panel px-4 py-3 text-sm text-soft">
          Couldn&apos;t reach the API ({error}). Is the backend running on port 8000?
        </div>
      )}

      {races && races.length === 0 && (
        <div className="panel px-4 py-3 text-sm text-muted">
          No races ingested yet — run <code className="font-mono text-text">python scripts/ingest_all_races.py</code>.
        </div>
      )}

      {races && races.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {races.map((race) => (
            <Link
              key={race.id}
              href={`/races/${race.id}`}
              className="panel group flex flex-col justify-between p-5 transition-colors hover:border-fastest/50"
            >
              <div>
                <p className="font-mono text-xs uppercase tracking-wider text-muted">
                  {race.season} &middot; Round {race.round}
                </p>
                <h2 className="mt-1 font-display text-2xl font-semibold text-text group-hover:text-fastest">
                  {race.name}
                </h2>
                <p className="mt-1 font-body text-sm text-muted">{race.circuit_name}</p>
              </div>
              <p className="mt-4 font-mono text-xs text-muted">
                {race.total_laps ? `${race.total_laps} laps` : "Lap count unknown"}
              </p>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}