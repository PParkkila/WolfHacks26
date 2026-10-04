"use client"

import { SparklesIcon } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { Brand } from "@/components/brand"
import { ChatPanel } from "@/components/chat/chat-panel"
import { ChatProvider } from "@/components/chat/chat-provider"
import { PersonaMenu } from "@/components/persona-menu"
import { ReplayControls } from "@/components/replay-controls"
import { ThemeToggle } from "@/components/theme-toggle"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useMediaQuery } from "@/hooks/use-media-query"
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
  const isDesktop = useMediaQuery("(min-width: 1024px)")
  const [docked, setDocked] = useState(true)
  const [sheetOpen, setSheetOpen] = useState(false)
  const audience = principal.role

  const chatVisible = isDesktop ? docked : sheetOpen
  const toggleChat = () =>
    isDesktop ? setDocked((v) => !v) : setSheetOpen((v) => !v)

  return (
    <div className="flex h-svh flex-col">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4 sm:gap-3">
        <Link href={homeFor(principal)} aria-label="PulseCast home">
          <Brand />
        </Link>
        <Badge variant="secondary" className="hidden sm:inline-flex">
          {principal.role === "clinician" ? "Clinician" : "Patient"}
        </Badge>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant={chatVisible ? "secondary" : "ghost"}
            size="sm"
            onClick={toggleChat}
            aria-pressed={chatVisible}
            aria-label="Assistant"
          >
            <SparklesIcon data-icon="inline-start" />
            <span className="hidden sm:inline">Assistant</span>
          </Button>
          <ThemeToggle />
          <PersonaMenu principal={principal} />
        </div>
      </header>

      <div className="shrink-0 border-b px-4 py-2">
        <ReplayControls />
      </div>

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
        {isDesktop && docked ? (
          <aside className="flex w-[400px] shrink-0 flex-col border-l xl:w-[460px]">
            <ChatPanel audience={audience} onClose={() => setDocked(false)} />
          </aside>
        ) : null}
      </div>

      {!isDesktop ? (
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent
            side="right"
            showCloseButton={false}
            className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-md"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>Assistant</SheetTitle>
              <SheetDescription>Ask questions about the data.</SheetDescription>
            </SheetHeader>
            <ChatPanel
              audience={audience}
              onClose={() => setSheetOpen(false)}
            />
          </SheetContent>
        </Sheet>
      ) : null}
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
