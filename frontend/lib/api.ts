const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface Race {
  id: number;
  season: number;
  round: number;
  name: string;
  race_date: string | null;
  total_laps: number | null;
  circuit_name: string | null;
}

export interface RaceDetail extends Race {
  circuit_name: string | null;
  circuit_country: string | null;
}

export interface LapOut {
  lap_number: number;
  driver_code: string | null;
  lap_time_seconds: number | null;
  position: number | null;
  compound: string | null;
  tyre_life: number | null;
  stint_number: number | null;
  is_accurate: boolean;
}

export interface DriverState {
  driver_code: string;
  position: number | null;
  gap_to_leader_seconds: number | null;
  gap_ahead_seconds: number | null;
  compound: string | null;
  tyre_age: number | null;
  stint_number: number | null;
  estimated_fuel_remaining_pct: number | null;
}

export interface WeatherSnapshot {
  air_temp: number | null;
  track_temp: number | null;
  humidity: number | null;
  rainfall: boolean;
  wind_speed: number | null;
}

export interface RaceStateSnapshot {
  race_id: number;
  lap_number: number;
  total_laps: number | null;
  weather: WeatherSnapshot | null;
  drivers: DriverState[];
}

export interface RaceResult {
  driver_code: string | null;
  constructor_name: string | null;
  grid_position: number | null;
  finish_position: number | null;
  status: string | null;
  points: number | null;
}

export interface StrategySimulationRequest {
  race_id: number;
  driver_code: string;
  current_lap: number;
  current_tyre_age: number;
  compound: string;
  n_trials?: number;
  sweep_max_offset?: number;
  reactive_window?: number;
  reactive_fallback_offset?: number | null;
  n_remaining_stops?: number;
  allowed_compounds?: string[] | null;
  seed?: number | null;
}

export interface SweepPoint {
  offset: number;
  mean_seconds: number;
}

export interface ReactiveStrategyResult {
  window: number;
  fallback_offset: number;
  mean_seconds: number;
}

export interface HeadToHeadResult {
  best_fixed_win_probability: number;
  reactive_win_probability: number;
  tie_probability: number;
}

export interface MultiStopResult {
  n_stops: number;
  pit_laps: number[];
  stint_compounds: string[];
  mean_seconds: number;
  p10_seconds: number;
  p90_seconds: number;
}

export interface StrategySimulationResponse {
  race_id: number;
  driver_code: string;
  current_lap: number;
  current_tyre_age: number;
  compound: string;
  n_trials: number;
  n_remaining_stops: number;
  base_pace_seconds: number;
  base_pace_n_laps_used: number;
  circuit_name: string;
  pit_loss_mean_seconds: number;
  pit_loss_std_seconds: number;
  pit_loss_model_source: string;
  degradation_slope: number;
  degradation_model_available: boolean;
  sweep: SweepPoint[] | null;
  best_fixed_offset: number | null;
  best_fixed_mean_seconds: number | null;
  reactive: ReactiveStrategyResult | null;
  head_to_head: HeadToHeadResult | null;
  multi_stop: MultiStopResult | null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listRaces: (season?: number) =>
    apiFetch<Race[]>(`/races${season ? `?season=${season}` : ""}`),

  getRace: (raceId: number) => apiFetch<RaceDetail>(`/races/${raceId}`),

  getRaceResults: (raceId: number) => apiFetch<RaceResult[]>(`/races/${raceId}/results`),

  getRaceLaps: (raceId: number, driver?: string, accurateOnly = false) => {
    const params = new URLSearchParams();
    if (driver) params.set("driver", driver);
    if (accurateOnly) params.set("accurate_only", "true");
    const qs = params.toString();
    return apiFetch<LapOut[]>(`/races/${raceId}/laps${qs ? `?${qs}` : ""}`);
  },

  getRaceState: (raceId: number, lap: number) =>
    apiFetch<RaceStateSnapshot>(`/races/${raceId}/state?lap=${lap}`),

  simulateStrategy: (request: StrategySimulationRequest) =>
    apiFetch<StrategySimulationResponse>(`/strategy/simulate`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
};