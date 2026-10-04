"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"

import { useSession } from "@/lib/auth"
import { homeFor, type Principal } from "@/lib/session"

/**
 * Renders its children only for the given role and sends anyone else to their
 * own home. The server enforces scope regardless; this keeps patients from ever
 * rendering (and requesting) cohort-wide views.
 */
export function RoleGate({
  role,
  children,
}: {
  role: Principal["role"]
  children: React.ReactNode
}) {
  const router = useRouter()
  const session = useSession()
  const allowed = session?.principal.role === role

  useEffect(() => {
    if (session && !allowed) router.replace(homeFor(session.principal))
  }, [session, allowed, router])

  return allowed ? children : null
}
