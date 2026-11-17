// Types for @agentcake/edge/express (express.js).
import type { IncomingMessage, ServerResponse } from "node:http"
import type { CakeOptions, RequestLike, mintToken } from "./index"

export type ExpressOptions = CakeOptions & {
  /** The visitor's address as the app knows it, e.g. req.ip under Express's trust proxy. */
  clientIp?: (req: IncomingMessage & { ip?: string }) => string | null | undefined
}

export type CakeMiddleware = ((req: IncomingMessage, res: ServerResponse, next: (error?: unknown) => void) => void) & { enabled: boolean }

export declare function cakeExpress(options?: ExpressOptions): CakeMiddleware
export declare const cakeNode: typeof cakeExpress

/** mintToken (index.d.ts) with Node's synchronous crypto: the same arguments, the token itself rather than a promise. */
export declare function mintTokenSync(
  secret: string | Uint8Array,
  request: RequestLike,
  extras: Parameters<typeof mintToken>[2],
): string | null
