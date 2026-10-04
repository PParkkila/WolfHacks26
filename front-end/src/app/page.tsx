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
  description: string
  icon: React.ComponentType
  pending: boolean
  disabled: boolean
  onSelect: () => void
}) {
  return (
    <Item variant="outline" asChild>
      <button type="button" onClick={onSelect} disabled={disabled}>
        <ItemMedia variant="icon">
          <Icon />
        </ItemMedia>
        <ItemContent>
          <ItemTitle>{persona.display_name}</ItemTitle>
          <ItemDescription>{description}</ItemDescription>
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
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-4 py-12 sm:py-16">
      <header className="flex flex-col gap-4">
        <Brand />
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">
            Who&apos;s looking today?
          </h1>
          <p className="max-w-2xl text-muted-foreground">
            Pick a persona for this demo. There are no passwords: the server
            signs a token for the persona you choose and decides what it may see
            from that token alone.
          </p>
        </div>
      </header>

      {personas.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Can&apos;t load personas</AlertTitle>
          <AlertDescription>
            The PulseCast API at {API_BASE_URL} didn&apos;t answer. Start it
            with <code>cd back-end &amp;&amp; just run</code>.
          </AlertDescription>
        </Alert>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-muted-foreground">Clinician</h2>
        {personas.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <ItemGroup className="gap-3">
            {clinicians.map((persona) => (
              <PersonaItem
                key={persona.user_id}
                persona={persona}
                icon={StethoscopeIcon}
                description="Sees every participant, cohort trends and the clinical assistant."
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
          <h2 className="text-sm font-medium text-muted-foreground">
            Patients
          </h2>
          <p className="text-sm text-muted-foreground">
            Each patient sees only their own data and their own assistant.
          </p>
        </div>
        {personas.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : (
          <ItemGroup className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {patients.map((persona) => (
              <PersonaItem
                key={persona.user_id}
                persona={persona}
                icon={UserIcon}
                description="Their own Gluco Score, sensors and assistant."
                pending={pending === persona.user_id}
                disabled={pending !== null}
                onSelect={() => choose(persona)}
              />
            ))}
          </ItemGroup>
        )}
      </section>

      <p className="text-xs text-muted-foreground">
        The Gluco Score is a model estimate from wearable data. It is not a
        glucose reading or a diagnosis.
      </p>
    </main>
  )
}
