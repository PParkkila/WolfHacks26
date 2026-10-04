/** Demo dashboard v1. Backend reads Tiger; browser must never receive DB credentials. */
export interface DashboardWindow {
  session_id: string;
  fixture_id: string;
  participant_key: string; // e.g. demo:big_ideas:001, never numeric-only joins
  source_participant_key: string;
  source_dataset: "big_ideas" | "imu50";
  unit_status: string;
  window_end_offset_minutes: number;
  window_end: string; // ISO UTC, exclusive window end in SIMULATED event time
  window_minutes: number; // 1440 in this fixture; includes synthetic minutes
  motion_mean_g: number;
  motion_std_g: number;
  motion_p90_g: number;
  temperature_mean_c_24h: number; // wrist skin temperature, NOT core temperature
  temperature_std_c_24h: number;
  hr_mean_bpm_24h: number | null; // IMU50 is null; never replace with zero
  hr_coverage_fraction: number;
  motion_hr_correlation: number | null;
  synthetic_minutes: number;
  synthetic_fraction: number;
  wearable_risk_indicator: number | null; // null while the rolling model is pending
  risk_status: string;
  demo_only: true;
  training_eligible: false;
  time_basis: "simulated_event_time";
}

export interface DemoDashboardFixture {
  session_id: string;
  continuous_stream_enabled: false;
  transport: "direct_tiger_database_not_http";
  dashboard_rows: number;
  participants: number;
  latest: DashboardWindow[];
  example_trend: DashboardWindow[]; // last 168 hourly windows for BIG IDEAs 001
}
