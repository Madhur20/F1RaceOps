"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, RaceStateSnapshot } from "@/lib/api";
import { CompoundPill } from "@/components/CompoundPill";

function formatGap(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds === 0) return "LEADER";
  return `+${seconds.toFixed(3)}`;
}

export function TimingTower({
  raceId,
  totalLaps,
  fieldSize,
}: {
  raceId: number;
  totalLaps: number | null;
  fieldSize: number | null;
}) {
  const maxLap = totalLaps ?? 1;
  const [lap, setLap] = useState(Math.min(20, maxLap));
  const [snapshot, setSnapshot] = useState<RaceStateSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [maxDriversSeen, setMaxDriversSeen] = useState(fieldSize ?? 0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // fieldSize (from a reliable server-side lap-1 fetch) is the primary
  // reference. maxDriversSeen only matters as a fallback for the rare case
  // where that fetch failed — see the page.tsx caller.
  const referenceFieldSize = fieldSize ?? maxDriversSeen;

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .getRaceState(raceId, lap)
        .then((s) => {
          setSnapshot(s);
          setMaxDriversSeen((prev) => Math.max(prev, s.drivers.length));
        })
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load race state."))
        .finally(() => setLoading(false));
    }, 120);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [raceId, lap]);

  return (
    <div>
      {/* Lap scrubber */}
      <div className="panel mb-4 flex items-center gap-4 px-5 py-4">
        <button
          onClick={() => setLap((l) => Math.max(1, l - 1))}
          className="font-mono text-lg text-muted hover:text-fastest"
          aria-label="Previous lap"
        >
          &minus;
        </button>
        <input
          type="range"
          min={1}
          max={maxLap}
          value={lap}
          onChange={(e) => setLap(Number(e.target.value))}
          className="h-1 flex-1 accent-fastest"
          aria-label="Lap"
        />
        <button
          onClick={() => setLap((l) => Math.min(maxLap, l + 1))}
          className="font-mono text-lg text-muted hover:text-fastest"
          aria-label="Next lap"
        >
          +
        </button>
        <div className="font-display text-2xl font-semibold tabular-nums text-text">
          LAP {lap}
          <span className="ml-1 font-mono text-sm font-normal text-muted">/ {maxLap}</span>
        </div>
      </div>

      {/* Weather strip */}
      {snapshot?.weather && (
        <div className="mb-4 flex flex-wrap gap-4 font-mono text-xs text-muted">
          <span>AIR {snapshot.weather.air_temp?.toFixed(1) ?? "—"}&deg;C</span>
          <span>TRACK {snapshot.weather.track_temp?.toFixed(1) ?? "—"}&deg;C</span>
          <span>HUMIDITY {snapshot.weather.humidity?.toFixed(0) ?? "—"}%</span>
          <span>WIND {snapshot.weather.wind_speed?.toFixed(1) ?? "—"} m/s</span>
          {snapshot.weather.rainfall && <span className="text-wet">RAIN</span>}
        </div>
      )}

      {error && <div className="panel px-4 py-3 text-sm text-soft">{error}</div>}

      {snapshot && referenceFieldSize > 0 && snapshot.drivers.length < referenceFieldSize && (
        <div className="panel mb-4 px-4 py-3 font-mono text-xs text-muted">
          Showing {snapshot.drivers.length} of {referenceFieldSize} drivers on this lap. This tool
          matches drivers by their own lap count, so cars a lap or more behind the leader
          (lapped, not retired) won&apos;t appear here until you scrub back to a lap they were
          actually on — check a driver&apos;s race result for their real finishing status.
        </div>
      )}

      {/* Timing tower */}
      <div className="panel overflow-hidden">
        <div className="grid grid-cols-[3rem_5rem_1fr_5rem_5rem_3rem_3rem] gap-2 border-b border-border px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-muted">
          <span>Pos</span>
          <span>Driver</span>
          <span></span>
          <span className="text-right">Gap</span>
          <span className="text-right">Interval</span>
          <span className="text-center">Tyre</span>
          <span className="text-right">Age</span>
        </div>
        <div className={loading ? "opacity-40 transition-opacity" : "transition-opacity"}>
          {snapshot?.drivers.map((driver) => (
            <div
              key={driver.driver_code}
              className="grid grid-cols-[3rem_5rem_1fr_5rem_5rem_3rem_3rem] items-center gap-2 border-b border-border/50 px-4 py-2 last:border-b-0 hover:bg-surfaceRaised"
            >
              <span className="font-display text-lg font-semibold tabular-nums text-text">
                {driver.position ?? "—"}
              </span>
              <Link
                href={`/races/${raceId}/strategy?driver=${driver.driver_code}&lap=${lap}&tyreAge=${driver.tyre_age ?? 0}&compound=${driver.compound ?? "MEDIUM"}`}
                className="font-mono text-sm font-medium text-text hover:text-fastest"
              >
                {driver.driver_code}
              </Link>
              <span />
              <span className="text-right font-mono text-sm tabular-nums text-muted">
                {formatGap(driver.gap_to_leader_seconds)}
              </span>
              <span className="text-right font-mono text-sm tabular-nums text-muted">
                {driver.gap_ahead_seconds !== null ? `+${driver.gap_ahead_seconds.toFixed(3)}` : "—"}
              </span>
              <span className="flex justify-center">
                <CompoundPill compound={driver.compound} />
              </span>
              <span className="text-right font-mono text-sm tabular-nums text-muted">
                {driver.tyre_age ?? "—"}
              </span>
            </div>
          ))}
        </div>
      </div>

      <p className="mt-3 font-mono text-[10px] text-muted">
        Click a driver code to plan a pit strategy from this point in the race.
      </p>
    </div>
  );
}