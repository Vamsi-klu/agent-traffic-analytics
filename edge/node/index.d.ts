// Types for @agentcake/edge (index.js): the shared core and the token's format.

/** botscent's verdict on a request, as botscent/server's inspect() returns it. */
export type Verdict = { type: "agent" | "human"; agent_name?: string; reasons: readonly string[] }

/** botscent's server module (botscent/server), or anything with the same inspect(). */
export type Botscent = { inspect(request: unknown): Verdict | Promise<Verdict>; VERSION?: string }

export type CutField =
  | "path" | "sec_fetch" | "sec_fetch_user" | "sec_purpose" | "accept_language" | "sec_ch_ua" | "sec_ch_ua_platform"
  | "sec_ch_ua_mobile" | "user_agent" | "signature_agent" | "header_name"

export type CakeOptions = {
  /** The shared secret, at least 32 bytes. Default: the CAKE_SERVER_TIMING_SECRET environment variable. */
  secret?: string | Uint8Array
  /** The variable (or Workers binding) the secret is read from. */
  secretEnv?: string
  /** Cache-Control: private, no-store on HTML responses. Default false. */
  noStore?: boolean
  /** botscent's server module, or the promise import("botscent/server") returns. */
  botscent?: Botscent | Promise<Botscent>
  /** The longest the page waits for botscent's verdict, in milliseconds. Default 150. */
  verdictWaitMs?: number
  /** How many header names the token keeps. Default 40. */
  maxHeaderNames?: number
  /** The longest each value may be, by field. */
  cut?: Partial<Record<CutField, number>>
  /** Paths ending in these never get a token. */
  skipExtensions?: string[]
  /** For tests: the clock, the token id, and where the one-time warnings go. */
  now?: () => number
  randomId?: () => string
  warn?: (line: string) => void
}

/** A Fetch Request, Node's IncomingMessage, or a plain request with its header lines in order. */
export type RequestLike =
  | Request
  | { method?: string; url?: string; originalUrl?: string; headers: unknown; rawHeaders?: string[] }
  | { method: string; path: string; headers: [string, string][] }

export type TokenPayload = {
  v: 1
  id: string
  t: number
  p: string | null
  sf: { s: string | null; m: string | null; d: string | null; u: string | null }
  sp: string | null
  md: boolean
  al: string | null
  ch: { ua: string | null; pf: string | null; mb: string | null }
  ua: string | null
  hn: string[] | null
  sg: { a: string | null; s: boolean; i: boolean }
  ik: string | null
  bs: { t: "agent" | "human"; a: string | null; r: string[] } | null
  bsv: string | null
}

export type VerifyResult = { result: "ok" | "stale"; payload: TokenPayload } | { result: "bad" }

export type CakeEdge = {
  enabled: boolean
  /** The token for this request, or null when it gets none (not a page, or no usable secret). */
  token(request: RequestLike, extras?: { ip?: string | null; rawHeaders?: string[]; env?: Record<string, unknown> }): Promise<string | null>
}

export declare function createCakeEdge(options?: CakeOptions): CakeEdge

export declare function mintToken(
  secret: string | Uint8Array,
  request: RequestLike,
  extras: CakeOptions & { nowMs: number; id: string; ip?: string | null; verdict?: Verdict | null; version?: string | null; rawHeaders?: string[] },
): Promise<string | null>

export declare function signPayload(secret: string | Uint8Array, payload: unknown): Promise<string>

export declare function verifyToken(
  secret: string | Uint8Array,
  token: string,
  options?: { nowMs?: number; maxAgeMs?: number; maxFutureMs?: number },
): Promise<VerifyResult>

export declare function networkKey(secret: string | Uint8Array, ip: string | null, nowMs: number): Promise<string | null>

export declare function ipPrefix(ip: unknown): string | null

export declare function isPageRequest(request: RequestLike, options?: CakeOptions): boolean

export declare const defaults: Record<string, unknown>
