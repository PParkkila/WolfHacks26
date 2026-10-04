# Gluco web app

Next.js 16 + Tailwind 4 + shadcn/ui front-end for the FastAPI back-end in
`../back-end` (read its README for the API, roles and the replay clock).

## Run

```bash
cd ../back-end && just run        # API on :8000 (just mock for offline data)
cd front-end && bun install
cp .env.example .env.local        # NEXT_PUBLIC_API_BASE_URL, default http://localhost:8000
bun dev                           # http://localhost:3000
```

The back-end's default CORS origins include `http://localhost:3000`.

| Task | Command |
| --- | --- |
| Regenerate API types from the running back-end | `bun run gen:api` |
| Types, lint, production build | `bun run typecheck`, `bun run lint`, `bun run build` |

## How it fits together

- `src/lib/api/`: `schema.d.ts` is generated from `/openapi.json`; never edit
  it by hand. `client.ts` is the typed client (adds the Bearer token, signs out
  on 401). `sse.ts` reads `/stream` and `/chat` with fetch, because
  EventSource can't send headers. `events.ts` types the SSE payloads, which
  OpenAPI doesn't describe.
- `src/lib/clock.tsx`: one `/stream` connection. Ticks with new windows
  invalidate every `['data', …]` query. A backwards seek (`reset: true`)
  refetches them all.
- `src/lib/catalog.ts`: metric labels, units and descriptions all come from
  `/catalog`.
- `src/components/query-chart.tsx`: the one chart for `/query` results and
  chat `data.chart` events.
- Routes: `/` persona picker, `/clinician` and `/clinician/participants/[id]`,
  `/me` (patients). Patients never render or request cohort-wide views.
- Times are replay time (`as_of`), shown in UTC to match the back-end's day
  buckets. The Gluco Score is always labelled an estimate, not a diagnosis.
