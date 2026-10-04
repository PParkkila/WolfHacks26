"use client"

import {
  ArrowUpIcon,
  HistoryIcon,
  MessageSquareIcon,
  PanelRightCloseIcon,
  PlusIcon,
  SquareIcon,
} from "lucide-react"
import { useState } from "react"

import { GlucoMark } from "@/components/brand"
import { ChatMessage } from "@/components/chat/chat-message"
import { useChat } from "@/components/chat/chat-provider"
import type { Audience } from "@/components/estimate-note"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import { Marker, MarkerContent } from "@/components/ui/marker"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { Spinner } from "@/components/ui/spinner"
import { useThreads } from "@/lib/api/queries"

const SUGGESTIONS: Record<Audience, string[]> = {
  clinician: [
    "Which patients need follow-up?",
    "Build a widget ranking the 5 lowest Gluco Scores",
    "Largest Gluco Score declines in the last 24 h",
    "Compare average heart rate across my panel this week",
  ],
  patient: [
    "Why did my score change?",
    "How active was I this week?",
    "What does my Gluco Score mean?",
  ],
}

function ThreadMenu() {
  const threads = useThreads()
  const { sessionId, openThread } = useChat()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Past conversations">
          <HistoryIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-80 w-72">
        <DropdownMenuLabel>Conversations</DropdownMenuLabel>
        <DropdownMenuGroup>
          {threads.isPending ? (
            <DropdownMenuItem disabled>
              <Spinner />
              Loading…
            </DropdownMenuItem>
          ) : threads.data?.length ? (
            threads.data.map((thread) => (
              <DropdownMenuItem
                key={thread.session_id}
                onSelect={() => void openThread(thread.session_id)}
                disabled={thread.session_id === sessionId}
              >
                <MessageSquareIcon />
                <span className="truncate">{thread.title}</span>
              </DropdownMenuItem>
            ))
          ) : (
            <DropdownMenuItem disabled>No conversations yet</DropdownMenuItem>
          )}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Composer({ audience }: { audience: Audience }) {
  const { send, stop, streaming } = useChat()
  const [draft, setDraft] = useState("")

  function submit() {
    if (!draft.trim() || streaming) return
    send(draft)
    setDraft("")
  }

  return (
    <form
      className="flex flex-col gap-2 border-t p-3"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <InputGroup>
        <InputGroupTextarea
          aria-label="Message Gluco"
          placeholder={
            audience === "patient"
              ? "Ask Gluco about your health data…"
              : "Ask about your panel or a specific patient…"
          }
          className="max-h-40 min-h-10"
          rows={1}
          maxLength={4000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <InputGroupAddon align="block-end" className="justify-end">
          {streaming ? (
            <InputGroupButton
              size="icon-sm"
              variant="outline"
              onClick={stop}
              aria-label="Stop answering"
            >
              <SquareIcon />
            </InputGroupButton>
          ) : (
            <InputGroupButton
              type="submit"
              size="icon-sm"
              variant="default"
              disabled={!draft.trim()}
              aria-label="Send"
            >
              <ArrowUpIcon />
            </InputGroupButton>
          )}
        </InputGroupAddon>
      </InputGroup>
      <p className="text-xs text-muted-foreground">
        {audience === "patient"
          ? "Gluco can make mistakes. It explains your data but can't diagnose or give medical advice."
          : "Gluco can make mistakes. Answers reflect data up to the time shown and don't replace clinical judgment."}
      </p>
    </form>
  )
}

export function ChatPanel({
  audience,
  onClose,
}: {
  audience: Audience
  onClose?: () => void
}) {
  const { messages, newChat, send, loadingThread, chartsMissing, streaming } =
    useChat()

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
        <GlucoMark className="size-5" />
        <h2 className="flex items-baseline gap-2 text-sm">
          <span className="font-semibold">Gluco</span>
          <span className="text-muted-foreground">
            {audience === "patient" ? "Your assistant" : "Clinical assistant"}
          </span>
        </h2>
        <div className="ml-auto flex items-center gap-1">
          <ThreadMenu />
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={newChat}
            disabled={streaming || messages.length === 0}
            aria-label="New conversation"
          >
            <PlusIcon />
          </Button>
          {onClose ? (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onClose}
              aria-label="Hide assistant"
            >
              <PanelRightCloseIcon />
            </Button>
          ) : null}
        </div>
      </header>

      <MessageScrollerProvider autoScroll>
        <MessageScroller className="min-h-0 flex-1">
          <MessageScrollerViewport>
            <MessageScrollerContent className="p-4">
              {loadingThread ? (
                <MessageScrollerItem>
                  <Marker>
                    <MarkerContent className="shimmer">
                      Opening conversation…
                    </MarkerContent>
                  </Marker>
                </MessageScrollerItem>
              ) : messages.length === 0 ? (
                <MessageScrollerItem className="my-auto">
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon" className="bg-accent">
                        <GlucoMark className="size-6" />
                      </EmptyMedia>
                      <EmptyTitle>
                        {audience === "patient"
                          ? "Ask Gluco about your week"
                          : "Ask Gluco about your patients"}
                      </EmptyTitle>
                      <EmptyDescription>
                        {audience === "patient"
                          ? "Simple answers about your own Gluco Score and wearable readings."
                          : "Answers use the same data as the dashboard, up to the time shown."}
                      </EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                      <div className="flex flex-col gap-2">
                        {SUGGESTIONS[audience].map((suggestion) => (
                          <Button
                            key={suggestion}
                            variant="outline"
                            size="sm"
                            className="rounded-full"
                            onClick={() => send(suggestion)}
                          >
                            {suggestion}
                          </Button>
                        ))}
                      </div>
                    </EmptyContent>
                  </Empty>
                </MessageScrollerItem>
              ) : (
                <>
                  {chartsMissing ? (
                    <MessageScrollerItem>
                      <Marker variant="separator">
                        <MarkerContent className="text-xs">
                          Charts from earlier answers aren&apos;t available here
                        </MarkerContent>
                      </Marker>
                    </MessageScrollerItem>
                  ) : null}
                  {messages.map((message) => (
                    <MessageScrollerItem
                      key={message.id}
                      messageId={message.id}
                      scrollAnchor={message.role === "user"}
                    >
                      <ChatMessage message={message} audience={audience} />
                    </MessageScrollerItem>
                  ))}
                </>
              )}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>

      <Composer audience={audience} />
    </div>
  )
}
