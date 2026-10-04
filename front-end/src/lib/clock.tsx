"use client"

import { useQueryClient } from "@tanstack/react-query"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import { toast } from "sonner"

import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client"
import type { ClockState, TickEvent } from "@/lib/api/events"
import { keys } from "@/lib/api/queries"
import { streamSSE } from "@/lib/api/sse"

type ClockCommand = Schemas["ClockCommand"]

type ClockContextValue = {
  clock: ClockState | null
  connected: boolean
  control: (command: ClockCommand) => Promise<void>
}

const ClockContext = createContext<ClockContextValue | null>(null)

function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener("abort", () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

/**
 * The shared replay clock. Holds one GET /stream connection for the signed-in
 * persona and refreshes clock-dependent queries when the clock moves: all of
 * them after a backwards seek, the active ones when new windows land.
 */
export function ClockProvider({
  token,
  children,
}: {
  token: string
  children: React.ReactNode
}) {
  const queryClient = useQueryClient()
  const [clock, setClock] = useState<ClockState | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller

    const onTick = (tick: TickEvent) => {
      setConnected(true)
      setClock(tick.clock)
      if (tick.reset) {
        void queryClient.invalidateQueries({
          queryKey: keys.data,
          refetchType: "all",
        })
      } else if (tick.new_windows.length > 0) {
        void queryClient.invalidateQueries({ queryKey: keys.data })
      }
    }

    void (async () => {
      let attempt = 0
      while (!signal.aborted) {
        try {
          await streamSSE("/stream", { signal }, (data) => {
            attempt = 0
            if ((data as TickEvent).type === "tick") onTick(data as TickEvent)
          })
        } catch (error) {
          if (signal.aborted) return
          if (error instanceof ApiError && error.status === 401) return
        }
        setConnected(false)
        await wait(Math.min(1000 * 2 ** attempt++, 10_000), signal)
      }
    })()

    return () => controller.abort()
  }, [token, queryClient])

  const control = useCallback(async (command: ClockCommand) => {
    try {
      setClock(await unwrap(api.POST("/clock", { body: command })))
    } catch (error) {
      toast.error("The replay clock didn't respond.", {
        description: error instanceof Error ? error.message : undefined,
      })
    }
  }, [])

  const value = useMemo(
    () => ({ clock, connected, control }),
    [clock, connected, control]
  )
  return <ClockContext.Provider value={value}>{children}</ClockContext.Provider>
}

export function useClock(): ClockContextValue {
  const value = useContext(ClockContext)
  if (!value) throw new Error("useClock must be used inside <ClockProvider>")
  return value
}
