# Glue4Glu

## Inspiration

Metabolic health data is usually fragmented. A wearable may capture movement, heart rate, and skin temperature, while glucose and HbA1c measurements live in separate systems and are reviewed much less often. We wanted to explore whether everyday wearable signals could provide useful context between those clinical measurements—without pretending that a watch can diagnose diabetes.

That idea became **Glue4Glu**: a research prototype that connects wearable history, a live sensor-style feed, and an experimental metabolic-pattern score in one explainable dashboard. The name reflects our goal: to “glue” together data that is normally isolated and make longitudinal patterns easier to understand.

## What It Does

Glue4Glu shows a participant’s current movement, wrist skin temperature, and available heart-rate data beside 24-hour features and seven-day trends. Its experimental score measures how closely the latest wearable pattern resembles the higher-HbA1c cohort in our research dataset. It is deliberately presented as a *cohort-resemblance indicator*, not a glucose reading, diagnosis, or calibrated probability of disease.

For participant $i$, we define the research label

$$
y_i = \mathbf{1}\!\left[\mathrm{HbA1c}_i \geq 5.7\%\right],
$$

and build a 12-feature vector $\mathbf{x}_{i,t}$ from the preceding 24 hours of movement and skin-temperature data. Our dashboard displays

$$
s_{i,t} = 100\,\widehat{p}\!\left(y_i=1\mid\mathbf{x}_{i,t}\right),
$$

as an experimental similarity score from 0 to 100. This mathematical form makes the model easy to communicate, but it does **not** make the score a clinically validated risk probability.

The prototype supports 66 participants across the BIG IDEAs and IMU50 studies. For the live demonstration, a simulated sensor feed advances every second while the dashboard preserves rolling history and clearly labels interpolated or synthetic values.

## How We Built It

We built two connected data paths. The historical path stages research files in Databricks, transforms raw measurements into minute summaries, constructs trailing 24-hour features, and publishes compact dashboard records. The live path uses a versioned, idempotent event contract to send sensor snapshots into Tiger Data, allowing the interface to update quickly without waiting for an analytics job. Processed Databricks results are published back to Tiger, where a read-only backend contract makes them available to the dashboard.

Our pipeline follows a Bronze–Silver–Gold pattern:

**Raw study and sensor data → clean minute features → model scores and dashboard views**

The model uses 12 motion and wrist-temperature features, including averages, quantiles, variability, daily amplitude, and motion–temperature correlation. We compared regularized logistic regression and shallow random-forest candidates using nested, participant-held-out evaluation. All preprocessing and model selection stay inside the training folds so that windows from the held-out person cannot leak into training.

The selected random forest was evaluated on 660 real 24-hour windows from 15 participants. It reached 60.4% participant-weighted window accuracy, compared with a 53.3% prior baseline. We also verified more than 11,000 scored dashboard windows across the 66-participant demonstration cohort. These results establish a working research prototype, not clinical validation.

## Challenges We Faced

The largest challenge was not drawing a chart or fitting a model; it was making very different data sources behave like one trustworthy system. The datasets use different devices, sampling rates, schemas, timestamp conventions, and available signals. Some files contain hundreds of millions of rows, while the expanded IMU50 preparation involved billions of acceleration samples. We had to preserve sample order, audit units, process data incrementally, and reduce high-frequency measurements into reproducible minute-level features.

Motion artifacts created another important challenge. Movement can corrupt PPG and derived heart-rate measurements, so we could not treat every sensor value as equally reliable. We kept signal quality visible, left unavailable heart rate as missing rather than silently converting it to zero, and separated shared cross-device model features from dashboard-only metrics.

We also had to build a demo that felt live without confusing simulation with measurement. Our replay system keeps source time separate from demo time, uses idempotent event identifiers, preserves history across restarts, and labels one-second values as interpolations of minute summaries. Finally, we resisted the temptation to market the score as a diabetes predictor. With a small cohort and cross-device differences, honest boundaries are part of the engineering.

## What We Learned

We learned that leakage prevention matters as much as model choice in wearable machine learning. Randomly splitting windows would allow the same person’s physiology to appear in both training and testing, so participant-level folds are essential. We also learned that window counts are not participant counts: hundreds of samples cannot substitute for a genuinely diverse cohort.

On the systems side, we learned to separate fast operational updates from slower analytics. Tiger Data serves the latest sensor state, while Databricks handles large-scale preparation, rolling features, evaluation, and publication. That separation kept the interface responsive and the computation traceable.

Most importantly, we learned that a responsible health prototype should make uncertainty visible. Glue4Glu is valuable not because it claims to replace a glucose monitor, but because it demonstrates how wearable signals can be placed in context, evaluated honestly, and connected into an understandable research experience.

## What’s Next

Next, we would validate the approach on a larger and more diverse cohort, test device-transfer performance, calibrate the score only after external validation, and compare wearable-only outputs against CGM data kept completely outside model training. We would also add stronger signal-quality detection and explanations that trace every insight back to the exact features and time window that produced it.
