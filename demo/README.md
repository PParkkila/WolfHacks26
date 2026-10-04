# Demo video

Records the hackathon demo in one continuous take, narrates it with Kokoro
text-to-speech and burns in subtitles. Output: `out/gluco-demo.mp4`, 1080p,
must stay under 120 s (`build.mjs` fails if it doesn't).

The final WolfHacks submission is available on
[YouTube](https://www.youtube.com/watch?v=gFUiAyoaX4A) and embedded on the
[Glue4Glu Devpost page](https://devpost.com/software/glue4glu). The rendered
video is linked rather than committed so the repository stays small while this
directory preserves the reproducible narration and recording pipeline.

## Run

1. Start the servers in separate terminals:
   - `api-demo`: mock data, replay on, its own `var/demo-sessions.sqlite` so
     real chats and pins are untouched. Needs `AGENT_MODEL` and the Gemini key
     from `back-end/.env`.
   - `web-demo`: a production build of the front end (no Next.js dev badge).
2. One-time: download the Kokoro model into `~/.cache/kokoro/`
   (`kokoro-v1.0.onnx`, `voices-v1.0.bin` from the kokoro-onnx releases), and
   `bun install` here.
3. `npm run all`, or step by step:
   - `npm run tts`: `narration.json` → `out/vo/*.wav` + durations
   - `npm run record`: pins the pre-made widgets, sets the replay clock, records
     the take with Playwright (Brave by default; set `BROWSER_PATH`)
   - `npm run build`: frames + narration + subtitles → `out/gluco-demo.mp4`

## Editing

- Narration text, voice and the end card live in `narration.json`. Re-run
  `tts` after changing a line: scenes stretch to fit their line.
- The shot list is `take()` in `record.mjs`; each scene is `say(id)`, actions,
  then `finish(id)`.
