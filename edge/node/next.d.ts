// Types for @agentcake/edge/next (next.js).
import type { CakeOptions } from "./index"

export type NextOptions = CakeOptions & {
  /** The visitor's address as your host gives it, e.g. request.headers.get("x-real-ip"). */
  clientIp?: (request: Request) => string | null | undefined
}

/** cake(request, NextResponse.next()) resolves to the response for the middleware to return. */
export type CakeNext = ((request: Request, response: Response) => Promise<Response>) & { enabled: boolean }

export declare function cakeNext(options?: NextOptions): CakeNext
