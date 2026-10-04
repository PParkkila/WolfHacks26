import type { components } from "@/lib/api/schema"

export type Principal = components["schemas"]["PrincipalOut"]

export type Session = {
  token: string
  principal: Principal
  /** Wall-clock expiry of the token, in epoch milliseconds. */
  expiresAt: number
}

const STORAGE_KEY = "pulsecast:session"

type Listener = () => void

const listeners = new Set<Listener>()
let current: Session | null = null
let loaded = false

function read(): Session | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Session
    return parsed.expiresAt > Date.now() ? parsed : null
  } catch {
    return null
  }
}

function write(session: Session | null) {
  try {
    if (session)
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable (private mode); the session then lives in memory.
  }
}

function emit() {
  for (const listener of listeners) listener()
}

/**
 * The signed-in persona, kept client-side. A tiny external store so the API
 * client (outside React) and components read the same token.
 */
export const sessionStore = {
  get(): Session | null {
    if (typeof window === "undefined") return null
    if (!loaded) {
      current = read()
      loaded = true
    }
    return current
  },
  set(session: Session | null) {
    current = session
    loaded = true
    write(session)
    emit()
  },
  subscribe(listener: Listener) {
    listeners.add(listener)
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY) return
      current = read()
      listener()
    }
    window.addEventListener("storage", onStorage)
    return () => {
      listeners.delete(listener)
      window.removeEventListener("storage", onStorage)
    }
  },
}

export function homeFor(principal: Principal): string {
  return principal.role === "clinician" ? "/clinician" : "/me"
}
