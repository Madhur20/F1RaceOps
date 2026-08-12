"use client";

import { useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, StrategySimulationResponse } from "@/lib/api";
import { CompoundPill } from "@/components/CompoundPill";
import { SweepChart } from "@/components/SweepChart";
import { HeadToHeadBar } from "@/components/HeadToHeadBar";

const COMPOUNDS = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"];

export default function StrategyPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const raceId = Number(params.id);

  const [driverCode, setDriverCode] = useState(searchParams.get("driver") ?? "VER");
  const [currentLap, setCurrentLap] = useState(Number(searchParams.get("lap") ?? 20));
  const [tyreAge, setTyreAge] = useState(Number(searchParams.get("tyreAge") ?? 10));
  const [compound, setCompound] = useState(searchParams.get("compound") ?? "MEDIUM");
  const [nStops, setNStops] = useState(1);

  const [result, setResult] = useState<StrategySimulationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSimulation() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.simulateStrategy({
        race_id: raceId,
        driver_code: driverCode.toUpperCase(),
        current_lap: currentLap,
        current_tyre_age: tyreAge,
        compound,
        n_remaining_stops: nStops,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-6 py-10 md:px-12">
      <Link
        href={`/races/${raceId}`}
        className="font-mono text-xs uppercase tracking-wider text-muted hover:text-fastest"
      >
        &larr; Back to timing tower
      </Link>

      <header className="mb-8 mt-4 border-b border-border pb-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">Strategy Simulator</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight text-text md:text-5xl">
          Pit Strategy
        </h1>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[20rem_1fr]">
        {/* --- Form panel --- */}
        <div className="panel h-fit space-y-4 p-5">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-wider text-muted">Driver</label>
            <input
              value={driverCode}
              onChange={(e) => setDriverCode(e.target.value)}
              maxLength={3}
              className="mt-1 w-full rounded-sm border border-border bg-surfaceRaised px-3 py-2 font-mono uppercase text-text"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-wider text-muted">Current lap</label>
            <input
              type="number"
              value={currentLap}
              onChange={(e) => setCurrentLap(Number(e.target.value))}
              className="mt-1 w-full rounded-sm border border-border bg-surfaceRaised px-3 py-2 font-mono text-text"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-wider text-muted">Current tyre age</label>
            <input
              type="number"
              value={tyreAge}
              onChange={(e) => setTyreAge(Number(e.target.value))}
              className="mt-1 w-full rounded-sm border border-border bg-surfaceRaised px-3 py-2 font-mono text-text"
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-wider text-muted">Current compound</label>
            <select
              value={compound}
              onChange={(e) => setCompound(e.target.value)}
              className="mt-1 w-full rounded-sm border border-border bg-surfaceRaised px-3 py-2 font-mono text-text"
            >
              {COMPOUNDS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-wider text-muted">
              Remaining stops
            </label>
            <select
              value={nStops}
              onChange={(e) => setNStops(Number(e.target.value))}
              className="mt-1 w-full rounded-sm border border-border bg-surfaceRaised px-3 py-2 font-mono text-text"
            >
              <option value={1}>1 (sweep + reactive)</option>
              <option value={2}>2 (multi-stop search)</option>
              <option value={3}>3 (multi-stop search)</option>
            </select>
          </div>
          <button
            onClick={runSimulation}
            disabled={loading}
            className="w-full rounded-sm bg-fastest px-4 py-2 font-display text-lg font-semibold text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Simulating…" : "Run Simulation"}
          </button>
        </div>

        {/* --- Results panel --- */}
        <div className="space-y-4">
          {error && <div className="panel px-4 py-3 text-sm text-soft">{error}</div>}

          {!result && !error && (
            <div className="panel px-4 py-8 text-center font-mono text-sm text-muted">
              Set the scenario and run a simulation.
            </div>
          )}

          {result && (
            <>
              <div className="panel grid grid-cols-2 gap-4 p-5 font-mono text-xs sm:grid-cols-4">
                <div>
                  <p className="text-muted">Base pace</p>
                  <p className="text-lg text-text">{result.base_pace_seconds.toFixed(2)}s</p>
                </div>
                <div>
                  <p className="text-muted">Pit loss ({result.pit_loss_model_source})</p>
                  <p className="text-lg text-text">{result.pit_loss_mean_seconds.toFixed(2)}s</p>
                </div>
                <div>
                  <p className="text-muted">Deg. slope</p>
                  <p className="text-lg text-text">
                    {result.degradation_slope.toFixed(4)}s/lap
                    {!result.degradation_model_available && (
                      <span className="ml-1 text-soft" title="No fitted model for this compound">
                        !
                      </span>
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-muted">Circuit</p>
                  <p className="text-lg text-text">{result.circuit_name}</p>
                </div>
              </div>

              {result.n_remaining_stops === 1 &&
                result.sweep &&
                result.reactive &&
                result.head_to_head &&
                result.best_fixed_offset !== null && (
                  <>
                    <div className="panel p-5">
                      <p className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted">
                        Cost curve — purple dot is the best fixed offset (+{result.best_fixed_offset}),
                        dashed line is the reactive strategy&apos;s mean
                      </p>
                      <SweepChart
                        sweep={result.sweep}
                        bestOffset={result.best_fixed_offset}
                        reactiveMean={result.reactive.mean_seconds}
                      />
                    </div>
                    <div className="panel p-5">
                      <p className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted">
                        Head-to-head: best fixed vs. reactive (safety-car-aware)
                      </p>
                      <HeadToHeadBar
                        bestFixedWinProb={result.head_to_head.best_fixed_win_probability}
                        reactiveWinProb={result.head_to_head.reactive_win_probability}
                        tieProb={result.head_to_head.tie_probability}
                      />
                    </div>
                  </>
                )}

              {result.n_remaining_stops > 1 && result.multi_stop && (() => {
                const multiStop = result.multi_stop;
                return (
                  <div className="panel p-5">
                    <p className="mb-4 font-mono text-[10px] uppercase tracking-wider text-muted">
                      Best {multiStop.n_stops}-stop strategy found
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      {multiStop.stint_compounds.map((c, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <CompoundPill compound={c} />
                          {i < multiStop.pit_laps.length && (
                            <span className="font-mono text-xs text-muted">
                              &rarr; pit lap {multiStop.pit_laps[i]} &rarr;
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="mt-5 grid grid-cols-3 gap-4 font-mono text-xs">
                      <div>
                        <p className="text-muted">Mean total time</p>
                        <p className="text-lg text-text">{multiStop.mean_seconds.toFixed(2)}s</p>
                      </div>
                      <div>
                        <p className="text-muted">P10</p>
                        <p className="text-lg text-text">{multiStop.p10_seconds.toFixed(2)}s</p>
                      </div>
                      <div>
                        <p className="text-muted">P90</p>
                        <p className="text-lg text-text">{multiStop.p90_seconds.toFixed(2)}s</p>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </>
          )}
        </div>
      </div>
    </main>
  );
}