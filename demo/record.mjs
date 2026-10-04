// Records the demo in one continuous take.
//
// Needs the API (mock data, replay on) on :8000 and the web app on :3000; see
// README.md. Reads out/vo/durations.json from tts.py so every scene lasts at
// least as long as its narration line, and writes:
//   out/frames/*.jpg   screencast frames
//   out/frames.json    when each frame arrived (ms since the take started)
//   out/cues.json      when each narration line starts (ms since the take started)

import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { performance } from "node:perf_hooks"
import { chromium } from "playwright"

const WEB = process.env.WEB_URL ?? "http://localhost:3000"
const API = process.env.API_URL ?? "http://localhost:8000"
const BROWSER = process.env.BROWSER_PATH ?? "/usr/bin/brave-browser"
const PATIENT = "demo:big_ideas:013"
// The browser viewport, rendered at 4/3 scale so frames come out 1920x1080.
const VIEWPORT = { width: 1440, height: 810 }
const SIZE = { width: 1920, height: 1080 }

const OUT = new URL("./out/", import.meta.url).pathname
const durations = JSON.parse(readFileSync(`${OUT}vo/durations.json`, "utf8"))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// ---------------------------------------------------------------- API setup

async function api(path, { token, method = "GET", body } = {}) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`)
  }
  return response.status === 204 ? null : response.json()
}

async function login(personaId) {
  const { token } = await api("/auth/login", {
    method: "POST",
    body: { persona_id: personaId },
  })
  return token
}

async function clearPins(token) {
  for (const pin of await api("/widgets", { token })) {
    await api(`/widgets/${pin.id}`, { token, method: "DELETE" })
  }
}

// The three widget kinds the take doesn't build on camera, already pinned.
const PREPINNED = [
  {
    title: "Gluco Score: patients 010, 013 and 016",
    kind: "trend",
    query: {
      metrics: ["gluco_score"],
      participants: ["demo:big_ideas:010", PATIENT, "demo:big_ideas:016"],
      hours: 48,
      bucket: "hour",
      agg: "mean",
    },
  },
  {
    title: "Panel average heart rate, last 7 days",
    kind: "cohort_trend",
    query: {
      metrics: ["hr_mean_bpm_24h"],
      hours: 168,
      bucket: "day",
      agg: "mean",
      group_by: "cohort",
    },
  },
  {
    title: "Most active patients",
    kind: "table",
    query: {
      metrics: ["motion_mean_g", "hr_mean_bpm_24h", "temperature_mean_c_24h"],
      bucket: "all",
      agg: "last",
      sort_by: "motion_mean_g",
      order: "desc",
      limit: 5,
    },
  },
]

async function setup() {
  const clinician = await login("clinician:demo")
  await clearPins(clinician)
  await clearPins(await login(`patient:${PATIENT}`))
  for (const spec of PREPINNED) {
    await api("/widgets", { token: clinician, method: "POST", body: spec })
  }
  // Ten simulated hours before the end of the data, paused: pressing play on
  // camera plays patient 013's overnight crash and then catches up to live.
  const clock = await api("/clock", { token: clinician })
  const start = new Date(Date.parse(clock.data_end) - 10 * 3_600_000)
  await api("/clock", { token: clinician, method: "POST", body: { action: "pause" } })
  await api("/clock", {
    token: clinician,
    method: "POST",
    body: { action: "speed", seconds_per_hour: 1 },
  })
  await api("/clock", {
    token: clinician,
    method: "POST",
    body: { action: "seek", to: start.toISOString() },
  })
}

// ---------------------------------------------------------------- the take

let t0 = 0
const elapsed = () => performance.now() - t0
const cues = []

/** Start narration line `id` now. */
function say(id) {
  if (!(id in durations)) throw new Error(`No narration line "${id}"`)
  cues.push({ id, at: Math.round(elapsed()) })
  console.log(`${(elapsed() / 1000).toFixed(1).padStart(6)}s  ${id}`)
}

/** Wait until line `id` has finished playing, plus `pad` ms of breathing room. */
async function finish(id, pad = 250) {
  const cue = cues.findLast((c) => c.id === id)
  const end = cue.at + durations[id] * 1000 + pad
  if (end > elapsed()) await sleep(end - elapsed())
}

// The app scrolls inside <main>, not the window. Eased in-page scrolling looks
// smoother on video than wheel events, and doesn't stall the take.
const SCROLL = `(target, ms) => new Promise((resolve) => {
  const el = document.querySelector("main") ?? document.scrollingElement
  const from = el.scrollTop
  const to = Math.max(0, Math.min(target(el), el.scrollHeight - el.clientHeight))
  const start = performance.now()
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms)
    el.scrollTop = from + (to - from) * ease(t)
    t < 1 ? requestAnimationFrame(step) : resolve()
  }
  requestAnimationFrame(step)
})`

/** Scroll by `dy` pixels over `ms`. */
async function glide(page, dy, ms = 1200) {
  await page.evaluate(
    ([fn, dy, ms]) => eval(fn)((el) => el.scrollTop + dy, ms),
    [SCROLL, dy, ms]
  )
}

/** Scroll so `locator` sits `offset` pixels below the top of the page. */
async function glideTo(page, locator, ms = 1200, offset = 120) {
  await locator.evaluate(
    (node, [fn, ms, offset]) =>
      eval(fn)(
        (el) =>
          el.scrollTop +
          node.getBoundingClientRect().top -
          el.getBoundingClientRect().top -
          offset,
        ms
      ),
    [SCROLL, ms, offset]
  )
}

async function type(page, text) {
  await page.getByRole("textbox", { name: "Message Gluco" }).pressSequentially(text, {
    delay: 28,
  })
  await sleep(200)
  await page.keyboard.press("Enter")
}

/** Wait for the assistant to finish answering. */
async function answered(page) {
  await sleep(400)
  await page.getByRole("button", { name: "Stop answering" }).waitFor({ state: "hidden" })
}

async function take(page) {
  const pin = page.getByRole("button", { name: "Pin", exact: true })

  // Landing page.
  say("intro")
  await sleep(2500)
  await page.getByRole("button", { name: /Dr\. Demo/ }).hover()
  await finish("intro", -900)
  await page.getByRole("button", { name: /Dr\. Demo/ }).click()

  // Clinician panel.
  await page.getByRole("heading", { name: "Pinned widgets" }).waitFor()
  await sleep(600)
  say("panel")
  await sleep(800)
  await glide(page, 520, 1800)
  await sleep(600)
  await glide(page, 560, 1600)
  await finish("panel", 0)

  // Press play on the replay clock.
  say("live")
  await glide(page, -2000, 900)
  await page.getByRole("button", { name: "Play demo" }).click()
  await finish("live", 0)

  // Patient 013.
  const row = page.getByRole("table").getByRole("link", { name: "Patient 013" })
  await glideTo(page, row, 1200, 300)
  await row.click()
  await page.getByRole("heading", { name: "Patient 013" }).waitFor()
  await sleep(300)
  say("detail")
  await page.getByText("Live sensors").waitFor({ timeout: 20_000 })
  await finish("detail", 600)

  // Clinician chat: explanation plus a heatmap.
  say("ask")
  await page.getByRole("button", { name: "Ask Gluco" }).click()
  await sleep(500)
  await type(page, "Why did Patient 013's score drop? Show it as a heatmap by day.")
  await finish("ask", 0)
  say("pipeline")
  await pin.waitFor({ timeout: 30_000 })
  await answered(page)
  await finish("pipeline", 0)
  say("pin")
  await pin.click()
  await finish("pin")

  // A suggested prompt: ranking.
  say("ranking")
  await page.getByRole("button", { name: "New conversation" }).click()
  await sleep(500)
  await page.getByRole("button", { name: /ranking the 5 lowest/ }).click()
  await pin.waitFor({ timeout: 30_000 })
  await answered(page)
  await sleep(500)
  await pin.click()
  await finish("ranking")

  // Back to the panel to see the new pins.
  say("board")
  await page.getByRole("button", { name: "Close chat" }).click()
  await page.getByRole("link", { name: "Gluco home" }).click()
  await page.getByRole("heading", { name: "Pinned widgets" }).waitFor()
  await sleep(500)
  await glideTo(page, page.getByRole("heading", { name: "Pinned widgets" }), 900, 80)
  await finish("board")

  // Switch to the patient.
  say("switch")
  await page.getByRole("button", { name: /^Account:/ }).click()
  await page.getByRole("menuitem", { name: /Switch profile/ }).click()
  await page.getByPlaceholder("Search profiles…").pressSequentially("013", { delay: 60 })
  await sleep(300)
  await page.keyboard.press("Enter")
  await page.getByRole("heading", { name: "Hi, Patient 013" }).waitFor()
  await finish("switch", 0)

  // The patient's own dashboard.
  say("me")
  await sleep(1200)
  await glide(page, 450, 1500)
  await sleep(600)
  await glideTo(page, page.getByRole("heading", { name: "Your vitals" }), 1500, 100)
  await finish("me", 0)

  // Patient builds a stat tile.
  say("stat")
  await page.getByRole("button", { name: "Ask Gluco" }).click()
  await sleep(400)
  await type(page, "Make a stat tile of my heart rate this week")
  await pin.waitFor({ timeout: 30_000 })
  await answered(page)
  await sleep(300)
  await pin.click()
  await finish("stat")

  // Guardrail.
  say("guard")
  await type(page, "Do I have diabetes?")
  await answered(page)
  await finish("guard", 600)

  // End on the patient's pinned widgets.
  await page.getByRole("button", { name: "Close chat" }).click()
  await sleep(300)
  await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2)
  await glide(page, -3000, 600)
  await glideTo(page, page.getByRole("heading", { name: "Pinned widgets" }), 900, 80)
  say("outro")
  await page.screencast.showOverlay(endCard(), { duration: 6000 })
  await finish("outro", 2600)
}

function endCard() {
  const { endCard: card } = JSON.parse(
    readFileSync(new URL("./narration.json", import.meta.url), "utf8")
  )
  const lines = card.lines.map((l) => `<div style="margin-top:10px">${l}</div>`).join("")
  return `
    <div style="position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
                background:rgba(250,250,249,.86);backdrop-filter:blur(10px);z-index:2147483647;
                font-family:var(--font-sans),ui-sans-serif,system-ui,sans-serif;color:#0f172a;text-align:center;
                animation:fade .5s ease-out">
      <style>@keyframes fade{from{opacity:0}to{opacity:1}}</style>
      <div>
        <div style="font-size:64px;font-weight:700;letter-spacing:-.02em">${card.title}</div>
        <div style="font-size:26px;color:#475569;margin-top:6px">${card.tagline}</div>
        <div style="font-size:18px;color:#64748b;margin-top:28px">${lines}</div>
      </div>
    </div>`
}

// ---------------------------------------------------------------- main

async function main() {
  await setup()
  rmSync(`${OUT}frames`, { recursive: true, force: true })
  mkdirSync(`${OUT}frames`, { recursive: true })

  const browser = await chromium.launch({ executablePath: BROWSER })
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SIZE.width / VIEWPORT.width,
    colorScheme: "light",
  })
  const page = await context.newPage()
  await page.goto(WEB)
  await page.getByRole("button", { name: /Dr\. Demo/ }).waitFor()
  await sleep(800)

  const frames = []
  t0 = performance.now()
  await page.screencast.start({
    size: SIZE,
    quality: 92,
    onFrame: ({ data }) => {
      const at = Math.round(elapsed())
      const file = `${String(frames.length).padStart(5, "0")}.jpg`
      writeFileSync(`${OUT}frames/${file}`, data)
      frames.push({ file, at })
    },
  })
  await page.screencast.showActions({
    cursor: "pointer",
    duration: 600,
    style: {
      point:
        "width:34px;height:34px;border-radius:50%;background:rgba(13,148,136,.25);" +
        "border:2px solid rgba(13,148,136,.7)",
      title: "display:none",
    },
  })

  try {
    await take(page)
  } finally {
    const end = Math.round(elapsed())
    await page.screencast.stop().catch((error) => console.error(error.message))
    writeFileSync(`${OUT}frames.json`, JSON.stringify({ end, frames }))
    writeFileSync(`${OUT}cues.json`, JSON.stringify(cues, null, 2))
    await browser.close()
    console.log(`take: ${(end / 1000).toFixed(1)}s, ${frames.length} frames`)
  }
}

await main()
