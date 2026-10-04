"use client"

import { useState } from "react"

import type { Audience } from "@/components/estimate-note"
import { ChatPanel } from "@/components/chat/chat-panel"
import { useChat } from "@/components/chat/chat-provider"
import { GlucoDot, type GlucoMood } from "@/components/chat/gluco-dot"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useMediaQuery } from "@/hooks/use-media-query"

function LauncherButton({
  mood,
  className,
  ...props
}: React.ComponentProps<typeof Button> & { mood: GlucoMood }) {
  return (
    <Button
      size="icon-lg"
      aria-label="Ask Gluco"
      {...props}
      className={cn(
        "group size-14 rounded-full p-0 shadow-lg active:scale-95",
        className
      )}
    >
      <GlucoDot mood={mood} className="size-full" />
    </Button>
  )
}

export function ChatLauncher({ audience }: { audience: Audience }) {
  const isDesktop = useMediaQuery("(min-width: 768px)")
  const [open, setOpen] = useState(false)
  const { streaming } = useChat()
  const mood: GlucoMood = streaming ? "thinking" : open ? "open" : "idle"

  if (!isDesktop) {
    return (
      <>
        <div className="fixed right-4 bottom-4 z-40 sm:right-6 sm:bottom-6">
          <LauncherButton
            mood={mood}
            aria-expanded={open}
            onClick={() => setOpen(true)}
          />
        </div>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent
            side="bottom"
            showCloseButton={false}
            className="gap-0 overflow-hidden rounded-t-xl p-0 data-[side=bottom]:h-[85dvh]! data-[side=bottom]:max-h-[85dvh]!"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>Gluco</SheetTitle>
              <SheetDescription>
                Ask Gluco questions about the health data.
              </SheetDescription>
            </SheetHeader>
            <ChatPanel audience={audience} onClose={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
      </>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div className="fixed right-4 bottom-4 z-40 sm:right-6 sm:bottom-6">
        {/* Tooltip wraps a span so it does not steal the popover trigger ref. */}
        <Tooltip open={open ? false : undefined}>
          <TooltipTrigger asChild>
            <span className="inline-flex">
              <PopoverTrigger asChild>
                <LauncherButton mood={mood} />
              </PopoverTrigger>
            </span>
          </TooltipTrigger>
          <TooltipContent side="left" sideOffset={8}>
            Ask Gluco
          </TooltipContent>
        </Tooltip>
      </div>
      <PopoverContent
        side="top"
        align="end"
        sideOffset={12}
        onInteractOutside={(event) => event.preventDefault()}
        onFocusOutside={(event) => event.preventDefault()}
        className="h-[min(640px,calc(100dvh-7rem))] w-[400px] gap-0 overflow-hidden rounded-xl p-0 xl:w-[440px]"
      >
        <ChatPanel audience={audience} onClose={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  )
}
