# PulseCast agent layer

Read-only reasoning service over the ML pipeline's risk scores. It never computes a
risk score and never writes to ML-owned tables. Design: see the implementation plan.

## Setup

```bash
cd back-end
source .venv/bin/activate
uv sync
cp .env.example .env   # set AGENT_MODEL and GEMINI_API_KEY; DATA_BACKEND=mock until the DB is ready
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
  domain/          Pydantic records, read-only data Protocols, Contract B events
  data/            mock.py and postgres.py implement the ports; factory.py picks one
  analysis/        Pure logic: cohort stats, z-scores, quality and abstention policy
  tools/           Tool groups; registry.py is the single list
  factory.py       Builds the Agent;  guardrails.py  input guardrail
  prompts/         system.md
  api/             app.py (FastAPI), sse.py (SDK events -> Contract B), chat_service.py
  observability/   JSONL turn log (SDK tracing is disabled)
evals/             cases.yaml + run.py
```

Adding a tool: write it in a `tools/` module (or a new one), register the module in
`tools/registry.py`. Swapping the database: edit the column maps at the top of
`data/postgres.py`.
