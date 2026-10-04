# Glue4Glu pitch speaker notes

These notes correspond to the final seven-slide deck. Slide 7 is an appendix
and is not part of the timed pitch.

## 1. Glue4Glu — 18 seconds

Glue4Glu gives wearable signals daily metabolic context. We combine current
readings with 24-hour features and a week of trends. An experimental score
compares those patterns with the higher-HbA1c study group.

## 2. Data at research scale — 22 seconds

This is our actual Databricks pilot pipeline. Expanded local preparation
processed over three billion acceleration samples into compact summaries. Our
demo includes all 66 participants from two independent studies, without
matching people across datasets.

## 3. System architecture — 24 seconds

Databricks storage holds prepared history for the replay. The sender writes
into Tiger Data, and the backend reads the same database directly. Databricks
runs a separate analytics loop, reading minute events and publishing rolling
features and scores every five minutes, plus processing time.

## 4. Experimental metabolic score — 28 seconds

Our random forest uses 12 movement and skin-temperature features. We held out
whole participants across 660 real windows from 15 people.
Participant-weighted window accuracy reached 60.4%, versus 53.3% for the
baseline. The score measures cohort similarity. Synthetic data stays out of
training, and clinical validation is future work.

## 5. Streaming and agentic AI — 32 seconds

Tiger Data is our live serving layer. It refreshes current values every second
for 66 people and keeps minute history in Timescale hypertables. The backend
reads published metrics and trends without triggering analytics. For the AI
explanation flow, the OpenAI Agents SDK coordinates the agent and guardrails,
while the Gemini API generates a contextual response. That explanation uses
the computed results. Databricks still produces the metabolic score.

## 6. See it live — 13 seconds

Now we will show the live dashboard. Watch readings update each second, compare
the score with its seven-day trend, and ask the AI to explain that
participant's recent context.

Speaking target: about 137 seconds, plus 15–20 seconds for the live demo.

## 7. References — appendix

- Cho, P., Kim, J., Bent, B., & Dunn, J. (2026). *BIG IDEAs Lab Glycemic
  Variability and Wearable Device Data* (version 1.1.3). PhysioNet.
  [doi:10.13026/aw6y-fc44](https://doi.org/10.13026/aw6y-fc44)
- La Fratta, I., et al. (2026). *IMU50: A high-frequency multi-modal wrist-worn
  IMU dataset of 50 subjects over 5 continuous days for supervised and
  self-supervised learning in free-living conditions* (v1). Zenodo.
  [doi:10.5281/zenodo.21468410](https://doi.org/10.5281/zenodo.21468410)
- Bent, B., et al. (2021). Engineering digital biomarkers of interstitial
  glucose from noninvasive smartwatches. *npj Digital Medicine, 4*, 89.
  [doi:10.1038/s41746-021-00465-w](https://doi.org/10.1038/s41746-021-00465-w)
- Pollard, T., et al. (2026). PhysioNet as a global platform for biomedical
  research. *Nature Health, 1*, 792–795.
  [doi:10.1038/s44360-026-00096-z](https://doi.org/10.1038/s44360-026-00096-z)
