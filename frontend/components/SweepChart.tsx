"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SweepPoint } from "@/lib/api";

export function SweepChart({
  sweep,
  bestOffset,
  reactiveMean,
}: {
  sweep: SweepPoint[];
  bestOffset: number;
  reactiveMean: number;
}) {
  const bestPoint = sweep.find((p) => p.offset === bestOffset);

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={sweep} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#262B33" />
          <XAxis
            dataKey="offset"
            stroke="#8890A0"
            fontSize={11}
            fontFamily="var(--font-mono)"
            label={{ value: "Laps until pit", position: "insideBottom", offset: -2, fill: "#8890A0", fontSize: 11 }}
          />
          <YAxis
            stroke="#8890A0"
            fontSize={11}
            fontFamily="var(--font-mono)"
            domain={["dataMin - 2", "dataMax + 2"]}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <Tooltip
            contentStyle={{ background: "#15181D", border: "1px solid #262B33", fontFamily: "var(--font-mono)", fontSize: 12 }}
            labelFormatter={(offset) => `Pit +${offset} laps`}
            formatter={(value: number) => [`${value.toFixed(2)}s`, "Mean total time"]}
          />
          <ReferenceLine
            y={reactiveMean}
            stroke="#9B4DFF"
            strokeDasharray="4 4"
            label={{ value: "Reactive", position: "insideTopRight", fill: "#9B4DFF", fontSize: 11 }}
          />
          <Line type="monotone" dataKey="mean_seconds" stroke="#E9EBEE" strokeWidth={2} dot={false} />
          {bestPoint && (
            <ReferenceDot
              x={bestPoint.offset}
              y={bestPoint.mean_seconds}
              r={5}
              fill="#9B4DFF"
              stroke="#0B0D10"
              strokeWidth={2}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}