# WolfHacks26
## PulseCast

Frontend research explorer for wearable-based metabolic phenotype similarity.

### Run locally

```sh
npm install
npm run dev
```

`npm test` checks cohort labels and replay boundaries. `npm run build` creates the production site.

### Data and model status

The app includes actual HbA1c labels from [PhysioNet BIG IDEAs v1.1.3](https://physionet.org/content/big-ideas-glycemic-wearable/1.1.3/). The source demographics are in `data/raw/physionet-demographics.csv`. Wearable values, quality, feature differences, and similarity scores are synthetic demonstration fixtures in `src/data/cohort.js`. A trained classifier, measured accuracy, CGM validation, and an external AI service are not implemented. The UI labels these boundaries explicitly.

The latest direction supersedes the earlier near-term glucose-rise proposal: predict cohort similarity from wearable-only features, use HbA1c as labels, and reserve CGM for independent validation. Fit all preprocessing within participant-held-out folds. See the app's Methodology view for the integration plan.

### Publishing

The Pages workflow builds and deploys pushes to `main`. Site: https://pparkkila.github.io/WolfHacks26/

See [SPECS.md](SPECS.md) for the project context, references, candidate directions, technical requirements, and communication plan.

See [PROJECT_OUTLINE.md](PROJECT_OUTLINE.md) for the current PulseCast concept and demo structure.

See [REPO_OUTLINE.md](REPO_OUTLINE.md) for the repository map, frontend flow, data contract, implementation stages, and scope guardrails.
