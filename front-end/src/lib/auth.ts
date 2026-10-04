"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import { useCallback, useSyncExternalStore } from "react"

import { api, unwrap } from "@/lib/api/client"
import { homeFor, sessionStore, type Session } from "@/lib/session"

const noop = () => () => {}

/** False during server render and hydration, true once running in the browser. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false
  )
}

/** The signed-in persona, or null. Always null until hydrated. */
export function useSession(): Session | null {
  return useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.get,
    () => null
  )
}

export function useAuth() {
  const router = useRouter()
  const queryClient = useQueryClient()

  const login = useCallback(
    async (personaId: string) => {
      const res = await unwrap(
        api.POST("/auth/login", { body: { persona_id: personaId } })
      )
      // Nothing cached for the previous persona may leak into the next one.
      queryClient.clear()
      sessionStore.set({
        token: res.token,
        principal: res.principal,
        expiresAt: Date.now() + res.expires_in * 1000,
      })
      router.replace(homeFor(res.principal))
    },
    [queryClient, router]
  )

  const logout = useCallback(() => {
    sessionStore.set(null)
    queryClient.clear()
    router.replace("/")
  }, [queryClient, router])

  return { login, logout }
}
