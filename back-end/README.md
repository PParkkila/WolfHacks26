# PulseCast back-end

Read-only API over the dashboard data Databricks publishes to Tiger
(`gold.dashboard_windows`). It serves a dashboard and two chatbots: one for
clinicians, who can see every participant, and one for patients, who can only see
themselves. It never computes the model's prediction and never writes to the
database.

The model's output is a 0–100 risk index. The data adapter turns it into the
**Gluco Score** (`100 − risk`, so higher is healthier), and nothing above the
adapter sees the raw index.

## Setup

```bash
cd back-end
source .venv/bin/activate
uv sync
cp .env.example .env   # GEMINI_API_KEY, AGENT_MODEL, and the PG* variables for Tiger
```

With no database configured, the app uses a seeded mock that has the same shape
as the real data (17 participants × 171 hourly windows).

## Run

| Task | Command |
| --- | --- |
| API on :8000 | `just run` (or `uv run agent serve`) |
| API on the seeded mock | `just mock` |
| One question, no server | `just ask "Who needs follow-up?"`, or as a patient: `just ask "Why did my score drop?" 13` |
| Evals (real model) | `just eval` (`--only 9 10`, `-v`) |
| Tests, lint, types | `just test`, `just lint` |
| Read-only checks against Tiger | `just test-live` |

Interactive API docs (OpenAPI) are served at `http://localhost:8000/docs`.

## How it fits together

```
Tiger gold.dashboard_windows -> data/postgres.py (or data/mock.py)   WindowSource port
        -> store.py   every window in memory; new rows picked up every STORE_REFRESH_S
        -> query.py   QueryService(principal): scope + replay clock + aggregation
        -> api/dashboard.py (REST, /stream)   and   tools/clinician.py | tools/patient.py
                                                     -> agent per request -> POST /chat (SSE)
```

- **Identity** (`auth.py`). There are no passwords. `GET /personas` lists
  "Dr. Demo" plus one persona per participant. `POST /auth/login` returns a signed
  JWT, sent afterwards as `Authorization: Bearer …`. The server decides what each
  request may see from that token, never from the UI or the LLM.
- **Scope** (`query.py`). Clinicians see everyone. Patients see only their own
  rows: no other participant, no cohort aggregates. Asking for anything else
  returns `403 not_permitted`.
- **Replay clock** (`clock.py`). The published data is a finished week, so a
  shared simulated "now" walks through it and everything is limited to windows
  ending at or before it. It starts on first use, one day after the first window,
  at `REPLAY_SECONDS_PER_HOUR` (default 5), and pauses when it reaches the newest
  window. `REPLAY_ENABLED=false` always shows everything.
- **Two agents** (`tools/`, `prompts/`, `guardrails.py`). Agents are built per
  request for the caller's role. Patient tools take no participant argument
  (they are bound to the token), so other people's data is out of reach even
  through prompt injection. Each role has its own input guardrail; the patient one
  allows general wellness questions but blocks diagnosis, prescriptions and
  questions about other people.

## API

All routes except `/personas`, `/auth/login` and `/health` need a token.

| Endpoint | Returns |
| --- | --- |
| `GET /personas`, `POST /auth/login {persona_id}`, `GET /me` | persona picker, token, caller |
| `GET /catalog` | metrics (label, unit, description, `higher_is_better`), visible participants, data range, supported buckets/aggs |
| `POST /query` | the generic query behind most widgets (below) |
| `GET /participants?sort_by=gluco_score&order=asc` | newest values per visible participant |
| `GET /participants/{id}` | one participant's newest values (`id` may be short: `13`, `P013`, `imu50`) |
| `GET /participants/{id}/explain?hours=24` | now vs N hours ago and vs their own week; plus where they sit in the cohort (clinicians only) |
| `GET /participants/{id}/compare?metric=…` | one metric vs the cohort (clinicians only) |
| `GET /cohort` | cohort overview: Gluco spread, lowest scores, biggest 24 h drops and gains (clinicians only) |
| `GET /clock`, `POST /clock {action: play\|pause\|speed\|seek, seconds_per_hour?, to?}` | replay control |
| `GET /stream` | SSE `tick` events: clock state plus newly visible windows (`reset: true` after a backwards seek) |
| `POST /chat {session_id, message}` | SSE: `token`, `tool_start`, `tool_end`, `data`, `done`, `error` |
| `GET /chat/sessions`, `GET /chat/sessions/{id}` | the caller's conversations and their messages |
| `GET /tools` | the caller's chatbot tools and their JSON schemas |
| `GET /health` | database, LLM key, row count, clock |

`POST /query` body (all fields optional):

```json
{
  "metrics": ["gluco_score", "hr_mean_bpm_24h"],
  "participants": ["13"],          // omit for everyone visible
  "hours": 168,                    // or "start"/"end" (ISO); end is capped at the clock
  "bucket": "day",                 // raw | hour | day | all
  "agg": "mean",                   // mean | median | min | max | first | last | delta
  "group_by": "participant",       // or "cohort" (clinicians only)
  "sort_by": "gluco_score", "order": "asc", "limit": 5
}
```

The response is `{as_of, start, end, metrics, units, series: [{participant_id,
display_name, points: [{t, n, <metric>: value}]}], total_series, truncated}`. A
chat `data` event carries this same shape under `chart`, so one chart component
can serve both the dashboard and the chat.

Errors come back as `{detail, code, …}`, where `code` is one of `not_found`,
`ambiguous`, `not_permitted` or `bad_query` (the last includes `suggestions` for
an unknown metric).

## Layout

```
src/agent/
  config.py        Settings; the only reader of env vars
  bootstrap.py     Composition root (Runtime)
  llm.py           The only module that knows the provider (Gemini, OpenAI-compatible)
  auth.py          Personas, tokens, Principal
  store.py         In-memory windows, incremental refresh
  clock.py         Replay clock
  query.py         QueryService: scope, clock, every derived number
  domain/          Window, metric catalog, WindowSource port, errors, Contract B events
  data/            postgres.py and mock.py implement WindowSource; factory.py picks one
  analysis/        Pure logic: aggregation, deviations, stats, id resolution, grounding
  tools/           clinician.py, patient.py; registry.py picks by role
  factory.py       Builds the role's Agent;  guardrails.py  per-role input guardrail
  prompts/         clinician.md, patient.md
  api/             app.py, deps.py (auth, errors), login.py, dashboard.py, chat.py,
                   chat_service.py, sse.py, sessions.py (per-user SQLite memory)
  observability/   JSONL turn log (SDK tracing is disabled)
evals/             cases.yaml (per role) + run.py
```

To change the database mapping, edit the names at the top of `data/postgres.py`
(`TABLE`, `COLUMNS`, `PAYLOAD_KEYS`). To add a metric, add it to
`domain/metrics.py`; `/catalog`, `/query`, the tools and the prompts all pick it
up from there.

To add a tool, put it in `tools/clinician.py` or `tools/patient.py`. Tools call the
`QueryService` they were built with, return `result(...)`, put series under
`chart`, and never raise: `safe_tool` turns errors into payloads.

## Behaviour worth knowing

- **Numbers are checked against tool results.** After each answer,
  `analysis/grounding.py` looks for numbers that no tool returned. The answer has
  already streamed, so this can only flag them: they go into the turn log, into
  the `done` event when present, and they fail `just eval`.
- **The agent knows "now".** The replay clock's time is written into each turn's
  instructions, and every tool returns it as `as_of`, so the agent never guesses
  dates.
- **Gemini quirk.** Gemini's OpenAI-compatible stream gives parallel tool calls the
  same index. `llm.py` re-indexes them; otherwise the SDK merges the calls and
  Gemini rejects the next request.
- **Database access.** Connections are read-only with a statement timeout. Still
  use a SELECT-only role: startup logs a warning if the role could write.
- **CORS** allows `ALLOWED_ORIGINS` only (a JSON list; the default is the Vite dev
  server and the GitHub Pages site).
