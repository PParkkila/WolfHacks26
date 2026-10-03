/**
 * PulseCast sensor and model data contracts.
 *
 * Keep these types independent of the chosen frontend framework so local
 * replay data and a future API can use the same shape.
 */

/** One synchronized sensor sample from a recorded session. */
export interface SensorSample {
  timestamp: string;
  ppg?: number;
  accelerometer: {
    x: number;
    y: number;
    z: number;
  };
}

/** Features calculated over a rolling analysis window. */
export interface WindowFeatures {
  windowStart: string;
  windowEnd: string;
  heartRateBpm?: number;
  heartRateSlope?: number;
  hrvRmssd?: number;
  ppgAmplitude?: number;
  movementMean?: number;
  movementSlope?: number;
  highMovementPercent?: number;
  ppgMotionCorrelation?: number;
}

/** Model output consumed by the dashboard. */
export interface RiskPoint {
  timestamp: string;
  rawRisk: number;
  rollingRisk: number;
  riskVelocity?: number;
  signalQuality: number;
  movementLevel?: "low" | "medium" | "high";
  explanation?: string;
}

/** A complete replay session. */
export interface ReplaySession {
  id: string;
  label: string;
  samples: SensorSample[];
  features?: WindowFeatures[];
  risk?: RiskPoint[];
}
