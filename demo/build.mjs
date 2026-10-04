// Turns a take into the final video: frames + narration + burned-in subtitles.
//
// Reads out/frames.json, out/cues.json, out/vo/*.wav and narration.json, and
// writes out/gluco-demo.mp4 (1920x1080, 30 fps, H.264 + AAC). The video is
// never cut; narration clips are laid on the timeline where record.mjs cued
// them. Fails if the result runs over the hard limit.

import { execFileSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"

const LIMIT_S = 120
const OUT = new URL("./out/", import.meta.url).pathname
const read = (path) => JSON.parse(readFileSync(path, "utf8"))

const { end, frames } = read(`${OUT}frames.json`)
const cues = read(`${OUT}cues.json`)
const durations = read(`${OUT}vo/durations.json`)
const { lines } = read(new URL("./narration.json", import.meta.url).pathname)
const text = Object.fromEntries(lines.map((l) => [l.id, l.text]))

const start = frames[0].at
const total = (end - start) / 1000
const ffmpeg = (...args) =>
  execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", ...args], {
    stdio: "inherit",
  })

// Frames: the screencast only sends a frame when the page changes, so each
// one is held until the next arrives.
const list = frames.flatMap((frame, i) => {
  const next = i + 1 < frames.length ? frames[i + 1].at : end
  return [`file 'frames/${frame.file}'`, `duration ${((next - frame.at) / 1000).toFixed(3)}`]
})
list.push(`file 'frames/${frames.at(-1).file}'`) // concat ignores the last duration otherwise
writeFileSync(`${OUT}frames.txt`, list.join("\n"))

// Narration: each clip delayed to its cue, mixed, then loudness-normalised.
const inputs = cues.flatMap((c) => ["-i", `${OUT}vo/${c.id}.wav`])
const delays = cues
  .map((c, i) => {
    const ms = Math.max(0, c.at - start)
    return `[${i}:a]adelay=${ms}|${ms}[a${i}]`
  })
  .join(";")
const mix = cues.map((_, i) => `[a${i}]`).join("")
ffmpeg(
  ...inputs,
  "-filter_complex",
  `${delays};${mix}amix=inputs=${cues.length}:normalize=0,` +
    `apad,atrim=0:${total.toFixed(3)},loudnorm=I=-16:TP=-1.5:LRA=11[out]`,
  "-map",
  "[out]",
  "-ar",
  "48000",
  `${OUT}narration.wav`
)

// Subtitles: each line split into short chunks, timed by their share of it.
function chunks(line, max = 62) {
  const words = line.split(" ")
  const out = []
  let current = ""
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word
    const breakAfter = /[.:;,]$/.test(current) && current.length > max * 0.45
    if ((candidate.length > max || breakAfter) && current) {
      out.push(current)
      current = word
    } else {
      current = candidate
    }
  }
  if (current) out.push(current)
  return out
}

const stamp = (s) => {
  const cs = Math.round(s * 100)
  const h = Math.floor(cs / 360000)
  const m = Math.floor((cs % 360000) / 6000)
  const sec = Math.floor((cs % 6000) / 100)
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`
}

const events = cues.flatMap((cue) => {
  const parts = chunks(text[cue.id])
  const length = parts.reduce((n, p) => n + p.length, 0)
  let at = (cue.at - start) / 1000
  return parts.map((part) => {
    const span = (durations[cue.id] * part.length) / length
    const line = `Dialogue: 0,${stamp(at)},${stamp(at + span)},Caption,,0,0,0,,${part}`
    at += span
    return line
  })
})

writeFileSync(
  `${OUT}subs.ass`,
  `[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Inter,40,&H00FFFFFF,&H00FFFFFF,&H50101820,&H50101820,0,0,0,0,100,100,0,0,3,14,0,2,200,200,56,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${events.join("\n")}
`
)

// Final encode.
ffmpeg(
  "-f",
  "concat",
  "-safe",
  "0",
  "-i",
  `${OUT}frames.txt`,
  "-i",
  `${OUT}narration.wav`,
  "-vf",
  `fps=30,scale=1920:1080:flags=lanczos,subtitles=${OUT}subs.ass,format=yuv420p`,
  "-c:v",
  "libx264",
  "-preset",
  "slow",
  "-crf",
  "18",
  "-c:a",
  "aac",
  "-b:a",
  "192k",
  "-t",
  total.toFixed(3),
  "-movflags",
  "+faststart",
  `${OUT}gluco-demo.mp4`
)

const probed = Number(
  execFileSync("ffprobe", [
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "csv=p=0",
    `${OUT}gluco-demo.mp4`,
  ]).toString()
)
console.log(`out/gluco-demo.mp4: ${probed.toFixed(2)}s`)
if (probed > LIMIT_S) {
  console.error(`Over the ${LIMIT_S}s limit by ${(probed - LIMIT_S).toFixed(2)}s`)
  process.exit(1)
}
