"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect } from "react"

import { Brand } from "@/components/brand"
import { ChatLauncher } from "@/components/chat/chat-launcher"
import { ChatProvider } from "@/components/chat/chat-provider"
import { PersonaMenu } from "@/components/persona-menu"
import { ReplayControls } from "@/components/replay-controls"
import { ThemeToggle } from "@/components/theme-toggle"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useHydrated, useSession } from "@/lib/auth"
import { ClockProvider } from "@/lib/clock"
import { homeFor, type Principal } from "@/lib/session"

function AppFrame({
  principal,
  children,
}: {
  principal: Principal
  children: React.ReactNode
}) {
  return (
    <div className="flex h-svh flex-col">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b bg-card px-4 sm:gap-3">
        <Link href={homeFor(principal)} aria-label="Gluco home">
          <Brand />
        </Link>
        <Badge variant="outline" className="hidden sm:inline-flex">
          {principal.role === "clinician" ? "Clinician" : "Patient"}
        </Badge>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <PersonaMenu principal={principal} />
        </div>
      </header>

      <div className="shrink-0 border-b bg-muted/60 px-4 py-1.5">
        <ReplayControls />
      </div>

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto pb-24">{children}</main>
      </div>

      <ChatLauncher audience={principal.role} />
    </div>
  )
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const hydrated = useHydrated()
  const session = useSession()

  useEffect(() => {
    if (hydrated && !session) router.replace("/")
  }, [hydrated, session, router])

  if (!session) {
    return (
      <div className="flex h-svh flex-col gap-4 p-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="flex-1" />
      </div>
    )
  }

  return (
    <ClockProvider token={session.token}>
      <ChatProvider
        key={session.principal.user_id}
        principal={session.principal}
      >
        <AppFrame principal={session.principal}>{children}</AppFrame>
      </ChatProvider>
    </ClockProvider>
  )
}
