# WolfHacks26 repository outline

## Project

**PulseCast** is a frontend-focused software prototype that turns prerecorded or replayed PPG and accelerometer data into an understandable metabolic-rise risk experience. It does not require building a physical watch or sensor.

## Repository map

```text
WolfHacks26/
├── README.md                 # Project entry point
├── SPECS.md                  # Event context, references, candidate directions
├── PROJECT_OUTLINE.md        # Current PulseCast concept and demo structure
├── REPO_OUTLINE.md           # This repository and implementation plan
├── LICENSE                   # Repository license
└── .gitignore                # Ignored local and generated files
```

As implementation begins, organize new code around the frontend, data contract, and demo assets:

```text
src/
├── components/               # Reusable UI pieces
├── views/                    # Main dashboard and explanation views
├── data/                     # Demo fixtures or replay adapters
├── services/                 # API and streaming-data clients
├── charts/                   # Risk and signal visualizations
└── styles/                   # Shared visual styling and theme
public/                       # Static assets
```

The initial scaffold now includes these directories and placeholder headers.
The shared TypeScript contracts in `src/types/sensor.ts` define synchronized
sensor samples, rolling features, model risk points, and replay sessions.

## User experience

1. The user opens the PulseCast dashboard.
2. The app loads a prerecorded session or starts a replay.
3. Sensor values and model outputs update over time.
4. The dashboard shows current risk, risk trend, signal quality, and supporting metrics.
5. The user selects “Explain this change.”
6. The app displays a plain-language explanation tied to the recent feature history.

## Frontend screens

### Dashboard

- Current metabolic-rise risk from 0–100%.
- Risk label and risk velocity.
- Rolling risk chart.
- Heart rate, HRV, movement, and signal quality cards.
- Replay controls and current session time.

### Explanation panel

- Recent risk change.
- Main contributing signal trends.
- Signal-quality caveat when movement may affect PPG.
- Clear statement that the output is a model estimate, not an exact glucose reading or medical diagnosis.

## Data contract

The frontend should be able to consume a time-ordered record similar to:

```json
{
  "timestamp": "2026-01-01T14:02:00Z",
  "risk": 0.82,
  "risk_velocity": 0.31,
  "heart_rate_bpm": 84,
  "hrv_rmssd": 42,
  "movement_level": "low",
  "signal_quality": 0.96,
  "explanation": "Heart rate increased while HRV decreased over the last 14 minutes."
}
```

The initial demo may use local fixture data. A backend or live model can replace the fixture without requiring a redesign of the UI.

## Implementation stages

### Stage 1 — Frontend shell

- Choose the frontend framework and styling approach.
- Build the dashboard layout with mock values.
- Add responsive behavior and a clear visual hierarchy.

### Stage 2 — Replay experience

- Add a small, documented demo dataset.
- Implement play, pause, reset, and replay speed controls.
- Update dashboard cards and chart as the replay advances.

### Stage 3 — Explanations and confidence

- Add the explanation panel.
- Show signal quality separately from metabolic-rise risk.
- Suppress or qualify predictions when motion makes the signal unreliable.

### Stage 4 — Integration and polish

- Replace fixtures with the selected API or Databricks output.
- Validate timestamps, units, and missing-data behavior.
- Add a short demo flow and presentation-ready copy.

## Scope guardrails

- Do not build hardware.
- Do not present the model as an exact glucose estimator.
- Do not imply medical diagnosis or clinical validation.
- Keep the first working demo functional with local data.
- Prefer a polished end-to-end interaction over a broad set of incomplete features.

## Open implementation decisions

- Frontend framework and hosting target.
- Whether the first integration uses a local JSON replay, a small API, or Databricks output.
- Final charting and component libraries.
- Which session and features make the clearest demo.
