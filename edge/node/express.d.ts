// Types for @agentcake/edge/express (express.js). Step S4.1.
import type { IncomingMessage, ServerResponse } from "node:http"
import type { CakeOptions, RequestLike, Verdict } from "./index"

export type ExpressOptions = CakeOptions & {
  /** The visitor's address as the app knows it, e.g. req.ip under Express's trust proxy. */
  clientIp?: (req: IncomingMessage & { ip?: string }) => string | null | undefined
}

export type CakeMiddleware = ((req: IncomingMessage, res: ServerResponse, next: (error?: unknown) => void) => void) & { enabled: boolean }

export declare function cakeExpress(options?: ExpressOptions): CakeMiddleware
export declare const cakeNode: typeof cakeExpress

export declare function mintTokenSync(
  secret: string | Uint8Array,
  request: RequestLike,
  extras: CakeOptions & { nowMs: number; id: string; ip?: string | null; verdict?: Verdict | null; version?: string | null; rawHeaders?: string[] },
): string | null
