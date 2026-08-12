export function HeadToHeadBar({
  bestFixedWinProb,
  reactiveWinProb,
  tieProb,
}: {
  bestFixedWinProb: number;
  reactiveWinProb: number;
  tieProb: number;
}) {
  return (
    <div>
      <div className="flex h-6 w-full overflow-hidden rounded-sm border border-border">
        <div className="bg-hard/60" style={{ width: `${bestFixedWinProb * 100}%` }} />
        <div className="bg-fastest" style={{ width: `${reactiveWinProb * 100}%` }} />
        <div className="bg-border" style={{ width: `${tieProb * 100}%` }} />
      </div>
      <div className="mt-2 flex justify-between font-mono text-xs">
        <span className="text-hard">Best Fixed {(bestFixedWinProb * 100).toFixed(1)}%</span>
        <span className="text-muted">Ties {(tieProb * 100).toFixed(1)}%</span>
        <span className="text-fastest">Reactive {(reactiveWinProb * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}