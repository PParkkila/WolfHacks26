import { ActivityIcon } from "lucide-react"

export function Brand() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <ActivityIcon className="size-4" />
      </span>
      PulseCast
    </span>
  )
}
