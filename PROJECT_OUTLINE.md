# PulseCast

## Real-Time Metabolic Rise Risk from Wearables

### 1. Product goal

Estimate the probability of a substantial glucose rise in the next 30 minutes using recent wearable sensor data. The project is a software dashboard and model prototype; it does not require building a physical watch or sensor.

### 2. Core workflow

```text
PPG + accelerometer
        ↓
Rolling 15-minute window
        ↓
Feature extraction
        ↓
XGBoost risk model
        ↓
Smoothed 0–100% risk
        ↓
AI explanation
```

### 3. Training target

- Use CGM data from the BIG IDEAs dataset only as the training label.
- At time `t`, calculate the glucose change at `t + 30 minutes`.
- Label an event when the future change is at least 20 units.
- Present the result as: “Estimated likelihood of a substantial rise,” rather than an exact glucose prediction.

### 4. Rolling features

- **PPG:** mean heart rate, heart-rate slope, HRV/RMSSD, pulse interval variability, PPG amplitude, and amplitude slope.
- **Accelerometer:** movement magnitude, mean and variance, maximum movement, movement slope, and time spent in high movement.
- **Trend signals:** 5-minute and 15-minute changes, plus PPG–motion correlation.

### 5. Risk presentation

- Smooth raw predictions into a rolling risk score.
- Show risk velocity: the change in risk over the last five minutes.
- Display a current risk percentage, a rolling trend chart, and a trend label such as “stable” or “rapidly rising.”

### 6. Signal confidence

Show a separate confidence score based on signal quality. During heavy movement, suppress the prediction or mark it unavailable and explain that motion may be corrupting the PPG signal.

### 7. AI explanation

When asked “Why did the risk increase?”, the agent should inspect the feature history and explain the strongest contributing trends, such as rising heart rate, falling HRV, changing PPG morphology, or high motion artifact.

### 8. Databricks architecture

```text
Raw data → Bronze streams → Silver cleaned signals
         → 15-minute windows → Gold features
         → XGBoost model → Risk stream → AI agent → Dashboard
```

Historical sessions can be replayed as a stream so the software demo behaves like a live data feed.

### 9. Demo screen

**PulseCast — Live Sensor Data Dashboard**

- Current risk: `82% — High risk`
- Risk trend: `↑ rapidly rising`
- Heart rate: `84 BPM`
- Movement: `Low`
- Signal quality: `96%`
- Rolling risk chart
- “Explain this increase” action

### 10. Open decisions

- Confirm the available CGM labels, units, and event threshold.
- Choose the final Databricks serving and dashboard components.
- Validate which feature set can be computed reliably during the hackathon.
- Decide whether the first demo prioritizes the live replay, the explanation agent, or both.
