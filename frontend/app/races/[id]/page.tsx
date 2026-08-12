import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { TimingTower } from "@/components/TimingTower";

export const dynamic = "force-dynamic";

export default async function RacePage({ params }: { params: { id: string } }) {
  const raceId = Number(params.id);
  if (Number.isNaN(raceId)) notFound();

  let race;
  try {
    race = await api.getRace(raceId);
  } catch {
    notFound();
  }
  if (!race) notFound();

  let fieldSize: number | null = null;
  try {
    const openingLapState = await api.getRaceState(raceId, 1);
    fieldSize = openingLapState.drivers.length;
  } catch {
    // non-fatal — TimingTower falls back to its own session-based tracking
  }

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <Link href="/" className="font-mono text-xs uppercase tracking-wider text-muted hover:text-fastest">
        &larr; All races
      </Link>
      <span className="mx-4 text-muted/50" aria-hidden="true">|</span>
      <Link
        href={`/races/${raceId}/results`}
        className="ml-4 font-mono text-xs uppercase tracking-wider text-muted hover:text-fastest"
      >
        Results &amp; lap times &rarr;
      </Link>

      <header className="mb-8 mt-4 border-b border-border pb-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
          {race.season} &middot; Round {race.round} &middot; {race.circuit_name}
          {race.circuit_country ? `, ${race.circuit_country}` : ""}
        </p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-text md:text-5xl">
          {race.name}
        </h1>
      </header>

      <TimingTower raceId={race.id} totalLaps={race.total_laps} fieldSize={fieldSize} />
    </main>
  );
}