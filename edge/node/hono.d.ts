// Types for @agentcake/edge/hono (hono.js). Hono's own types are not imported: this package depends on nothing. Step S4.1.
import type { CakeOptions } from "./index"

/** The part of Hono's Context the middleware uses. */
export type HonoContextLike = { req: { raw: Request }; res: Response; env?: unknown }

export type HonoOptions = CakeOptions & {
  /** The visitor's address, e.g. c.req.header("cf-connecting-ip") on Cloudflare Workers. */
  clientIp?: (c: any) => string | null | undefined
}

export type CakeHono = ((c: any, next: () => Promise<void>) => Promise<void>) & { enabled: boolean }

export declare function cakeHono(options?: HonoOptions): CakeHono
