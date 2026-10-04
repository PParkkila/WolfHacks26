import createClient, { type Middleware } from "openapi-fetch"

import type { components, paths } from "@/lib/api/schema"
import { sessionStore } from "@/lib/session"

export type Schemas = components["schemas"]

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "")

/** A failed API call. `code` is the back-end's stable error code when it sent one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | undefined,
    message: string,
    readonly body?: unknown
  ) {
    super(message)
    this.name = "ApiError"
  }

  static from(status: number, body: unknown): ApiError {
    const record = (body ?? {}) as { detail?: unknown; code?: unknown }
    const message =
      typeof record.detail === "string"
        ? record.detail
        : status === 0
          ? "Can't reach the Gluco API."
          : `Request failed (${status}).`
    const code = typeof record.code === "string" ? record.code : undefined
    return new ApiError(status, code, message, body)
  }
}

export function authHeader(): Record<string, string> {
  const token = sessionStore.get()?.token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** An expired or rejected token signs the persona out; the app shell sends them to the picker. */
export function handleUnauthorized(status: number) {
  if (status === 401 && sessionStore.get()) sessionStore.set(null)
}

const auth: Middleware = {
  onRequest({ request }) {
    for (const [name, value] of Object.entries(authHeader())) {
      request.headers.set(name, value)
    }
    return request
  },
  onResponse({ response }) {
    handleUnauthorized(response.status)
    return response
  },
}

export const api = createClient<paths>({ baseUrl: API_BASE_URL })
api.use(auth)

type Result<T> = { data?: T; error?: unknown; response: Response }

/** The response body, or an ApiError for anything that isn't a 2xx. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>
  try {
    result = await call
  } catch (cause) {
    throw new ApiError(0, undefined, "Can't reach the Gluco API.", cause)
  }
  if (!result.response.ok || result.error !== undefined) {
    throw ApiError.from(result.response.status, result.error)
  }
  return result.data as T
}
