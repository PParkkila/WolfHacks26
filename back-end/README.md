# PulseCast agent layer

Read-only reasoning service over the ML pipeline's risk scores. It never computes a
risk score and never writes to ML-owned tables. The model that produces the scores
(trained on the streamed wearable data) lives on the Databricks side; this layer only
reads its output through the ports in `domain/ports.py`.

## Setup

```bash
cd back-end
source .venv/bin/activate
uv sync
cp .env.example .env   # set AGENT_MODEL and LLM_API_KEY; DATA_BACKEND=mock until the DB is ready
```

## Run

| Task | Command |
| --- | --- |
| API on :8000 (`/chat` SSE, `/health`, `/tools`) | `just run` or `uv run agent serve` |
| API on seeded mock data | `just mock` |
| One question in the terminal, no server | `just ask "Why is P012 flagged?"` |
| Evals (real model) | `just eval` (`--tier 2`, `--only 9 10`, `-v`) |
| Tests, lint, types | `just test`, `just lint` |

## Layout

```
src/agent/
  config.py        Settings; the only reader of env vars
  bootstrap.py     Composition root
  llm.py           LlmConnection: the only module that talks to the provider
                   (config.py holds its default endpoint and key setting)
  assessment.py    Assessor: lookup + data quality + reliability, decided once
  explanation.py   Explainer: cohort-deviation explanation, withheld when unreliable
  domain/          Pydantic records, read-only data Protocols, Contract B events
  data/            mock.py and postgres.py implement the ports; factory.py picks one;
                   cache.py is the shared cohort-stats cache
  analysis/        Pure logic: cohort stats, z-scores, quality and abstention policy,
                   grounding (are an answer's numbers in the tool results?)
  tools/           Tool groups; registry.py is the single list
  factory.py       Builds the Agent;  guardrails.py  input guardrail
  prompts/         system.md
  api/             app.py (FastAPI), sse.py (SDK events -> Contract B -> SSE frames),
                   chat_service.py, sessions.py (SQLite conversation memory)
  observability/   JSONL turn log (SDK tracing is disabled)
evals/             cases.yaml + run.py
```

Adding a tool: write it in a `tools/` module (or a new one), register the module in
`tools/registry.py`. A tool starts with `require_assessment(...)` (unknown people
become a `not_found` payload for free) and builds its payload with `result(...)`;
anything that carries a score goes through `model_output(...)`, which nulls the
numbers when the result is not reliable. Tools receive `ToolDeps`, never the backend.

Swapping the database: edit the column maps at the top of `data/postgres.py`
(`TABLES`, `RISK_COLUMNS`, `FEATURE_COLUMNS`, `STAT_COLUMNS`). Every other numeric
column of the features table is read as a feature value.

## Behaviour worth knowing

- **Unreliable results carry no numbers.** When a window is not scored, has
  insufficient data quality or low confidence, tools return `suppressed: true` with
  null score, label and confidence. `rank_candidates` ranks only reliable people and
  lists the rest under `unranked` with the reason.
- **Numbers are checked against tool results.** After each answer,
  `analysis/grounding.py` looks for numbers no tool returned. It cannot block (the
  answer has already streamed), so the turn log gets `ungrounded_numbers`, the
  `done` event carries the same list when it is non-empty, and `just eval` fails the
  case.
- **Database access.** Sessions are opened read-only with a statement timeout, but
  `DATABASE_URL` should still use a role with SELECT only; startup logs a warning if
  the role could write. Cohort stats are cached for `STATS_TTL_S` (default 300).
- **CORS** allows `ALLOWED_ORIGINS` only (a JSON list; the default is the Vite dev
  server and the GitHub Pages site).
- **Extras beyond the core chat loop**, kept on purpose: `GET /tools` (lists tool
  schemas for the front end), `agent ask` (one question in the terminal),
  `rank_candidates` (follow-up queue), normal-approximation percentiles (the
  cohort stats carry mean and stddev, not a full distribution), and computing cohort
  stats from `person_features` when no `cohort_stats` table exists.
- **Evals** marked `planned: true` need tools that do not exist yet and are skipped
  unless you pass `--include-planned`.
