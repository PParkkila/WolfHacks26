"use client"

import { LogOutIcon, StethoscopeIcon, UserIcon, UsersIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { usePersonas } from "@/lib/api/queries"
import { useAuth } from "@/lib/auth"
import type { Principal } from "@/lib/session"

function initials(name: string) {
  const words = name
    .replace(/[^\p{L}\p{N} ]/gu, "")
    .split(" ")
    .filter(Boolean)
  const last = words.at(-1) ?? "?"
  return /\d/.test(last)
    ? last.slice(-2)
    : words
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
}

function PersonaSwitcher({
  open,
  onOpenChange,
  current,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  current: Principal
}) {
  const personas = usePersonas(open)
  const { login } = useAuth()

  async function choose(persona: Principal) {
    onOpenChange(false)
    if (persona.user_id === current.user_id) return
    try {
      await login(persona.user_id)
      toast.success(`Signed in as ${persona.display_name}`)
    } catch (error) {
      toast.error(`Couldn't switch to ${persona.display_name}.`, {
        description: error instanceof Error ? error.message : undefined,
      })
    }
  }

  const groups = [
    { heading: "Clinician", role: "clinician", icon: StethoscopeIcon },
    { heading: "Patients", role: "patient", icon: UserIcon },
  ] as const

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Switch persona"
      description="Sign in as another persona"
    >
      <Command>
        <CommandInput placeholder="Search personas…" />
        <CommandList>
          <CommandEmpty>
            {personas.isPending ? "Loading…" : "No persona found."}
          </CommandEmpty>
          {groups.map(({ heading, role, icon: Icon }) => (
            <CommandGroup key={role} heading={heading}>
              {personas.data
                ?.filter((p) => p.role === role)
                .map((persona) => (
                  <CommandItem
                    key={persona.user_id}
                    value={`${persona.display_name} ${persona.user_id}`}
                    onSelect={() => choose(persona)}
                  >
                    <Icon />
                    {persona.display_name}
                    {persona.user_id === current.user_id ? (
                      <span className="ml-auto text-xs text-muted-foreground">
                        current
                      </span>
                    ) : null}
                  </CommandItem>
                ))}
            </CommandGroup>
          ))}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}

export function PersonaMenu({ principal }: { principal: Principal }) {
  const { logout } = useAuth()
  const [switching, setSwitching] = useState(false)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className="gap-2 px-1.5"
            aria-label={`Account: ${principal.display_name}`}
          >
            <Avatar className="size-6">
              <AvatarFallback className="text-[0.65rem]">
                {initials(principal.display_name)}
              </AvatarFallback>
            </Avatar>
            <span className="hidden sm:inline">{principal.display_name}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="flex flex-col">
            <span>{principal.display_name}</span>
            <span className="text-xs font-normal text-muted-foreground">
              {principal.role === "clinician" ? "Clinician" : "Patient"}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem onSelect={() => setSwitching(true)}>
              <UsersIcon />
              Switch persona…
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={logout}>
              <LogOutIcon />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <PersonaSwitcher
        open={switching}
        onOpenChange={setSwitching}
        current={principal}
      />
    </>
  )
}
