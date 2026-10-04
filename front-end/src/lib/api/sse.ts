import { EventSourceParserStream } from "eventsource-parser/stream"

import {
  API_BASE_URL,
  ApiError,
  OFFLINE_MESSAGE,
  authHeader,
  handleUnauthorized,
} from "@/lib/api/client"

/**
 * Read a server-sent event stream with fetch, so it can carry the Bearer header
 * (EventSource can't). Resolves when the server closes the stream; rejects with
 * an ApiError for a non-2xx response, or the abort reason when `signal` fires.
 */
export async function streamSSE(
  path: string,
  init: RequestInit & { signal: AbortSignal },
  onEvent: (data: unknown, event: string) => void
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "text/event-stream",
        ...authHeader(),
        ...init.headers,
      },
    })
  } catch (cause) {
    if (init.signal.aborted) throw cause
    throw new ApiError(0, undefined, OFFLINE_MESSAGE, cause)
  }

  if (!response.ok || !response.body) {
    handleUnauthorized(response.status)
    const body = await response.json().catch(() => undefined)
    throw ApiError.from(response.status, body)
  }

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream())
    .getReader()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) return
      let data: unknown
      try {
        data = JSON.parse(value.data)
      } catch {
        continue
      }
      onEvent(data, value.event ?? "message")
    }
  } finally {
    reader.releaseLock()
  }
}
