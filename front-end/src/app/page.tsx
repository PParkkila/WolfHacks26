"use client"

import { ChevronRightIcon, StethoscopeIcon, UserIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Brand } from "@/components/brand"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { API_BASE_URL } from "@/lib/api/client"
import { usePersonas } from "@/lib/api/queries"
import { useAuth, useSession } from "@/lib/auth"
import { homeFor, type Principal } from "@/lib/session"

function PersonaItem({
  persona,
  description,
  icon: Icon,
  pending,
  disabled,
  onSelect,
}: {
  persona: Principal
  description?: string
  icon: React.ComponentType
  pending: boolean
  disabled: boolean
  onSelect: () => void
}) {
  return (
    <Item
      variant="outline"
      asChild
      className="bg-card transition-colors hover:border-primary/40 hover:bg-accent/50"
    >
      <button type="button" onClick={onSelect} disabled={disabled}>
        <ItemMedia variant="icon" className="bg-accent text-accent-foreground">
          <Icon />
        </ItemMedia>
        <ItemContent>
          <ItemTitle>{persona.display_name}</ItemTitle>
          {description ? (
            <ItemDescription>{description}</ItemDescription>
          ) : null}
        </ItemContent>
        <ItemActions>
          {pending ? <Spinner /> : <ChevronRightIcon />}
        </ItemActions>
      </button>
    </Item>
  )
}

export default function PersonaPickerPage() {
  const router = useRouter()
  const session = useSession()
  const personas = usePersonas()
  const { login } = useAuth()
  const [pending, setPending] = useState<string | null>(null)

  useEffect(() => {
    if (session) router.replace(homeFor(session.principal))
  }, [session, router])

  async function choose(persona: Principal) {
    setPending(persona.user_id)
    try {
      await login(persona.user_id)
    } catch (error) {
      setPending(null)
      toast.error(`Couldn't sign in as ${persona.display_name}.`, {
        description: error instanceof Error ? error.message : undefined,
      })
    }
  }

  const clinicians = personas.data?.filter((p) => p.role === "clinician") ?? []
  const patients = personas.data?.filter((p) => p.role === "patient") ?? []

  return (
    <main className="mx-auto grid w-full max-w-6xl flex-1 gap-12 px-4 py-10 sm:px-6 sm:py-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
      <header className="flex flex-col gap-8 lg:sticky lg:top-16 lg:self-start">
        <Brand />
        <div className="flex flex-col gap-4">
          <h1 className="text-4xl leading-[1.05] font-bold tracking-tight text-balance sm:text-5xl">
            Your wearable, explained in plain language.
          </h1>
          <p className="max-w-md text-lg text-muted-foreground">
            Gluco scores each day of wearable data and answers questions about
            it, for people at risk of diabetes and their care team.
          </p>
        </div>
        <p className="max-w-md text-xs text-muted-foreground">
          The Gluco Score is a model estimate from wearable data. It is not a
          glucose reading or a diagnosis.
        </p>
      </header>

      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold tracking-tight">
            Who&apos;s looking today?
          </h2>
          <p className="text-sm text-muted-foreground">
            Pick a demo persona. There are no passwords: the server signs a
            token for the persona you choose and decides what it may see from
            that token alone.
          </p>
        </div>

        {personas.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Can&apos;t load personas</AlertTitle>
            <AlertDescription>
              The Gluco API at {API_BASE_URL} didn&apos;t answer. Start it with{" "}
              <code>cd back-end &amp;&amp; just run</code>.
            </AlertDescription>
          </Alert>
        ) : null}

        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium text-muted-foreground">
            Clinician
          </h3>
          {personas.isPending ? (
            <Skeleton className="h-18 w-full rounded-xl" />
          ) : (
            <ItemGroup className="gap-3">
              {clinicians.map((persona) => (
                <PersonaItem
                  key={persona.user_id}
                  persona={persona}
                  icon={StethoscopeIcon}
                  description="Sees every participant, cohort trends and Gluco in clinical mode."
                  pending={pending === persona.user_id}
                  disabled={pending !== null}
                  onSelect={() => choose(persona)}
                />
              ))}
            </ItemGroup>
          )}
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-medium text-muted-foreground">
              Patients
            </h3>
            <p className="text-sm text-muted-foreground">
              Each patient sees only their own Gluco Score, readings and
              assistant.
            </p>
          </div>
          {personas.isPending ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-14 rounded-xl" />
              ))}
            </div>
          ) : (
            <ItemGroup className="grid gap-3 sm:grid-cols-2">
              {patients.map((persona) => (
                <PersonaItem
                  key={persona.user_id}
                  persona={persona}
                  icon={UserIcon}
                  pending={pending === persona.user_id}
                  disabled={pending !== null}
                  onSelect={() => choose(persona)}
                />
              ))}
            </ItemGroup>
          )}
        </section>
      </div>
    </main>
  )
}
