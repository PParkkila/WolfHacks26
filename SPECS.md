# WolfHacks 26 project specs

This document collects the shared technical context, references, candidate directions, and coordination plan for the project. It intentionally keeps the project idea open so the team can choose after reviewing the data and hackathon requirements.

## Core data

- **Signals:** accelerometer and PPG (photoplethysmography) data.
- **Primary data resource:** [Zenodo record 21468410](https://zenodo.org/records/21468410).
- **Additional datasets and resources:** [WolfHacks resources portal](https://wolfhacks.org/portal/resources).
- **Expected analysis areas:** heart rate, heart-rate variability, movement intensity, activity state, signal quality, anomalies, and changes relative to a user's own baseline.

The implementation should preserve the relationship between movement and PPG quality. Movement can corrupt PPG-derived measurements, so analyses that use heart-rate or HRV values should be able to identify or communicate when a window may be unreliable.

## Event references

- [Intro slides](https://docs.google.com/presentation/d/1th9wDnOnEHkpBLGgQhIu3eZoxl9gkGMDfkyCOvGtvoo/edit?usp=sharing)
- [MLH WolfHacks prizes](https://www.mlh.com/events/wolfhacks-by-acm-at-nc-state/prizes)
- [WolfHacks datasets and resources](https://wolfhacks.org/portal/resources)
- [Zenodo dataset record](https://zenodo.org/records/21468410)

Before implementation, the team should review the event requirements, available prizes, dataset license and documentation, and any restrictions on using hosted services or external APIs.

## Candidate project directions

These are options for evaluation, not a decision. The team should select one direction after a short data and prize review.

### Lie detector

Explore whether combined accelerometer and PPG features can identify physiological patterns associated with a controlled experiment. This direction needs careful framing: the prototype should present correlations or signals of interest, not claim reliable lie detection.

### Fall detector

Use accelerometer patterns, with PPG as supporting context, to detect possible falls and distinguish them from ordinary movement. A useful demo would replay sessions, show the detected event, and explain which signal features contributed to the alert.

### “Ask Your Wearable” explorer

Build a chat interface over recorded sessions. A user could ask, “Why was my heart rate high during session 3?” The system would translate the question into a query over structured tables, run signal-analysis tools, and return a chart with an explanation.

Potential implementation: a Databricks App with Unity Catalog functions exposed as agent tools.

### Signal-quality-aware health agent

Use the accelerometer to flag motion-corrupted PPG windows. The agent decides whether a heart-rate reading is trustworthy and explains when a spike is more likely to be a motion artifact than a physiological event. This direction highlights the relationship between the two available sensor streams.

### Streaming insight pipeline

Replay sessions as a stream using Structured Streaming or Lakeflow Declarative Pipelines. Compute windowed features such as heart rate, RMSSD, movement intensity, and activity state; detect anomalies or baseline drift; and have an agent triage alerts with explanations.

Suggested data layers: bronze (raw signals), silver (cleaned and windowed features), and gold (events, alerts, and summaries).

### Recovery and stress coach

Combine HRV, resting heart rate, and activity load into a daily readiness or stress score. A multi-step agent compares a user's sessions against their personal baseline and produces a personalized recovery plan.

### Auto-journal of sessions

Segment each session into activities such as rest, walking, and exercise. Generate a narrative timeline such as “10-minute walk, heart rate peaked at 150, recovery took 90 seconds,” then compare sessions to describe changes in recovery or activity load.

## Shared technical requirements

- Ingest and document the accelerometer and PPG data used by the prototype.
- Keep raw data separate from cleaned data and derived features.
- Record the time range and units for every derived signal.
- Make charts and explanations traceable to the session and time window that produced them.
- Surface signal-quality limitations, especially during motion.
- Keep the first demo reproducible from a documented setup and a small sample of the dataset.
- Defer the final architecture and platform choice until the team has reviewed the resources and selected a project direction.

## Communication plan

- **Messages:** use the team messaging channel for quick coordination, decisions that need fast feedback, and time-sensitive updates.
- **GitHub issues:** use issues for scoped work, technical questions, decisions that need a durable record, and links to relevant resources.
- Every implementation task should have a clear owner, a short description of the expected result, and a definition of done.
- Record the selected project direction and major architecture decisions in GitHub issues, then update this document when they become stable.

## Open decisions

- Which candidate direction best matches the data, available time, and MLH prize opportunities?
- Which dataset sessions and labels are usable for a first demo?
- Which platform and model/tooling constraints apply?
- What is the smallest end-to-end demo that can be completed and presented reliably?
