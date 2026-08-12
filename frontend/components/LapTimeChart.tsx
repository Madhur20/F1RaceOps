"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, LapOut } from "@/lib/api";

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#F02D2D",
  MEDIUM: "#F5C51D",
  HARD: "#F2F2F0",
  INTERMEDIATE: "#3DAA35",
  WET: "#1E7FD1",
};

function CompoundDot(props: any) {
  const { cx, cy, payload } = props;
  const color = COMPOUND_COLORS[payload.compound as string] ?? "#8890A0";
  if (cx === undefined || cy === undefined) return null;
  return <circle cx={cx} cy={cy} r={3} fill={color} stroke="#0B0D10" strokeWidth={1} />;
}

export function LapTimeChart({ raceId, driverCodes }: { raceId: number; driverCodes: string[] }) {
  const [driver, setDriver] = useState(driverCodes[0] ?? "");
  const [laps, setLaps] = useState<LapOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!driver) return;
    setLoading(true);
    setError(null);
    api
      .getRaceLaps(raceId, driver)
      .then((allLaps) => setLaps(allLaps.filter((l) => l.lap_time_seconds !== null)))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load laps."))
      .finally(() => setLoading(false));
  }, [raceId, driver]);

  // pit stops: laps where the compound differs from the previous lap
  const pitLaps = laps
    .filter((l, i) => i > 0 && l.compound !== laps[i - 1].compound)
    .map((l) => l.lap_number);

  return (
    <div className="panel p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Lap time progression — dot color shows tyre compound, dashed lines mark pit stops
        </p>
        <select
          value={driver}
          onChange={(e) => setDriver(e.target.value)}
          className="rounded-sm border border-border bg-surfaceRaised px-2 py-1 font-mono text-xs text-text"
        >
          {driverCodes.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-sm text-soft">{error}</p>}

      <div className={`h-72 w-full ${loading ? "opacity-40" : ""} transition-opacity`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={laps} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#262B33" />
            <XAxis
              dataKey="lap_number"
              stroke="#8890A0"
              fontSize={11}
              fontFamily="var(--font-mono)"
              label={{ value: "Lap", position: "insideBottom", offset: -2, fill: "#8890A0", fontSize: 11 }}
            />
            <YAxis
              stroke="#8890A0"
              fontSize={11}
              fontFamily="var(--font-mono)"
              domain={["dataMin - 1", "dataMax + 1"]}
              tickFormatter={(v: number) => v.toFixed(0)}
            />
            <Tooltip
              contentStyle={{
                background: "#15181D",
                border: "1px solid #262B33",
                fontFamily: "var(--font-mono)",
                fontSize: 12,
              }}
              labelFormatter={(lap) => `Lap ${lap}`}
              formatter={(value: number) => [`${value.toFixed(3)}s`, "Lap time"]}
            />
            {pitLaps.map((lap) => (
              <ReferenceLine key={lap} x={lap} stroke="#8890A0" strokeDasharray="3 3" />
            ))}
            <Line
              type="monotone"
              dataKey="lap_time_seconds"
              stroke="#E9EBEE"
              strokeWidth={1.5}
              dot={<CompoundDot />}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}