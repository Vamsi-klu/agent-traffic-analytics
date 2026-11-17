# AgentCake site middleware for Node

AgentCake records visits through its page script, `cake.js`. Some facts about a page request are seen only by your
site's server: the Web Bot Auth signature an agent such as ChatGPT adds, and the fetch metadata of the very first
page. This middleware packs them into one signed token and sets it on that page's own response:

```text
Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"
```

`cake.js` reads the token from the page's navigation entry and sends it with the visit. AgentCake checks the signature
with the secret it shares with your server, accepts each token once and only for 15 minutes, and shows what your server
saw on the session's page ("Server middleware").

- No dependencies. Node 20 or newer, and the Next.js edge runtime.
- It does nothing until it has a secret.
- It sets no cookie, stores nothing and makes no network request.
- It is not published to npm. It comes with AgentCake, in the edge folder of the installed package
  (`agentcake/edge/`; a checkout has it at `edge/`): `npm install <edge folder>/node`. `agentcake setup --print --site`
  prints the full path.

## The secret

On the machine that runs AgentCake:

```sh
agentcake secret init
agentcake secret print
```

Give the printed value to your site's server as the environment variable `CAKE_SERVER_TIMING_SECRET`. Pipe it into your
secret store rather than pasting it into a file. Without the variable, or with a value shorter than 32 bytes, the
middleware passes every request through untouched.

## Mount it

### Express, Connect or node:http

```js
const { cakeExpress } = require("@agentcake/edge/express")

app.set("trust proxy", 1) // behind one load balancer: req.ip is then the visitor's address
app.use(cakeExpress({ clientIp: (req) => req.ip }))
```

Mount it before the routes and the static files that answer pages. On plain `node:http`, or around a Next.js custom
server's request handler:

```js
const cake = cakeExpress({ clientIp: (req) => req.socket.remoteAddress })
http.createServer((req, res) => cake(req, res, () => handle(req, res)))
```

The entry is written when the response's head is, so a handler that sets its own `Server-Timing` later keeps its entries
and cake's.

### Next.js

`middleware.ts` (`proxy.ts` from Next.js 16):

```ts
import { NextResponse, type NextRequest } from "next/server"
import { cakeNext } from "@agentcake/edge/next"

const cake = cakeNext({ clientIp: (request) => request.headers.get("x-real-ip") })

export async function middleware(request: NextRequest) {
  return cake(request, NextResponse.next())
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] }
```

If you already have middleware, pass the response it returns instead of `NextResponse.next()`. It runs on the edge
runtime and on Node (it uses Web Crypto only). Next.js gives middleware the request headers without their order, so
`hn` is `null` here.

### Hono

```ts
import { Hono } from "hono"
import { cakeHono } from "@agentcake/edge/hono"

const app = new Hono()
app.use(cakeHono({ clientIp: (c) => c.req.header("cf-connecting-ip") ?? null }))
```

On Cloudflare Workers, store the secret as a binding named `CAKE_SERVER_TIMING_SECRET`
(`wrangler secret put CAKE_SERVER_TIMING_SECRET`). On Node (`@hono/node-server`) the header order is kept.

### Any other framework

```js
import { createCakeEdge } from "@agentcake/edge"

const edge = createCakeEdge()
const token = await edge.token(request, { ip }) // a Fetch Request, or Node's IncomingMessage; null: no token
```

Set `Server-Timing: cake;desc="<token>"` on that request's response.

## Options

Every default is in `defaults.json`, and the request header names are in `headers.json`.

| Option | Default | What it does |
|---|---|---|
| `secret` | the `CAKE_SERVER_TIMING_SECRET` variable | The shared secret: a string or bytes, at least 32 bytes long. |
| `clientIp` | none | A function returning the visitor's address as your app knows it. Without it the token has no network key (`ik`). Never use the leftmost `X-Forwarded-For` entry: anyone can write it. |
| `noStore` | `false` | `true` sets `Cache-Control: private, no-store` on HTML responses (on Next.js, on every page navigation's response). See "Caching and 304". |
| `botscent` | none | botscent's server module (`import("botscent/server")`, or the module itself): its verdict on the request rides the token. |
| `verdictWaitMs` | `150` | The longest the page waits for botscent's verdict. A slow or failing botscent costs the verdict, never the page. |
| `maxHeaderNames` | `40` | How many header names `hn` keeps. |
| `cut` | see `defaults.json` | The longest each value may be, by field (`user_agent`, `accept_language`, ...). |
| `skipExtensions` | see `defaults.json` | Paths ending in these never get a token. |
| `secretEnv` | `CAKE_SERVER_TIMING_SECRET` | The variable (or Workers binding) the secret is read from. |

## Which requests get a token

A `GET` whose `Sec-Fetch-Dest` is `document`, or, from a client that sends no fetch metadata, a `GET` that accepts
`text/html`. Never a frame, a subresource, a `POST` or `HEAD`, a static file (by extension) or a dot-file such as
`/.well-known/...`. A prefetch or prerender of a page does get one, with its `Sec-Purpose`, because the browser shows that
very response if the visitor goes to the page.

## What the token holds

Any script on the page can read `Server-Timing`. The signature proves that the token comes from your server; it does
not hide it. So the token holds only what the browser sent anyway.

| Field | What it is |
|---|---|
| `v` | The payload's version, `1`. |
| `id` | A random token id. AgentCake accepts each id once. |
| `t` | When your server saw the request, in milliseconds since 1970 (UTC). |
| `p` | The path as sent, without the query string. |
| `sf` | `Sec-Fetch-Site`, `-Mode`, `-Dest` and `-User` as sent (`s`, `m`, `d`, `u`). |
| `sp` | `Sec-Purpose` (a prefetch or prerender), or `null`. |
| `md` | Whether `Accept` lists `text/markdown`. |
| `al` | `Accept-Language`. |
| `ch` | The low-entropy client hints `sec-ch-ua`, `sec-ch-ua-platform` and `sec-ch-ua-mobile` (`ua`, `pf`, `mb`). |
| `ua` | `User-Agent`. |
| `hn` | The request's header names in the order they were sent, names only; `null` where the runtime does not keep the order. |
| `sg` | `Signature-Agent` as sent (`a`), and whether `Signature` (`s`) and `Signature-Input` (`i`) came with the request. |
| `ik` | The network key: the first 16 hex characters of HMAC-SHA256(secret, `ip|<UTC day>|<the /24 or /48 of the address>`). AgentCake computes the same from `cake.js`'s own request and keeps only whether the two match. |
| `bs` | botscent's verdict, `{ t, a, r }` (type, agent name, reason ids), or `null`. |
| `bsv` | botscent's version, or `null`. |

Values are cut to the lengths in `defaults.json` and control characters are removed. The token never holds an IP
address, a cookie, an authorization value or the value of any other header.

## Caching and 304

By default the middleware leaves your caching headers alone. Two cases need a choice:

- **A CDN or shared cache stores your HTML.** Every visitor then gets the same stored token, and AgentCake accepts a
  token once, so only one of those visits has server middleware data. Mark the HTML `private`, or turn on `noStore`.
- **Your HTML is revalidated** (`Cache-Control: no-cache` with an `ETag` or `Last-Modified`, answered with `304 Not
  Modified`). The 304 carries a new token, and browsers show the page that new token (below). `noStore: true` avoids
  304s for HTML altogether.

Tried with Chromium 149, WebKit 27.2 (Safari's engine, as Playwright builds it) and Firefox 157, headless, on a test
site with and without `noStore`:

- **At a 304** each of them shows the page the 304's own new token, and keeps that token with its stored copy. WebKit
  reloads a page with a plain request (a 200 with a new token) where the other two send a 304.
- **Going back or forward** to a page they stored, without asking your server, they show the token stored with it.
  AgentCake keeps every token once: another page view of the same visit bringing it again is counted as a reuse (one
  server middleware record, not a replay, no error); another visit bringing it (a new tab) is refused as a replay, and
  a token older than 15 minutes as stale, so that page view has no server middleware data. A page the back-forward
  cache keeps alive (Chrome's, even with `noStore`) is the same page view and sends nothing new.

## Check a token by hand

```js
const { verifyToken } = require("@agentcake/edge")
await verifyToken(secret, token) // { result: "ok" | "stale" | "bad", payload }
```

## Tests

```sh
node --test test/*.test.js
```

The token format is pinned by the test vectors in the AgentCake repository, `tests/vectors/edge_token.json`, which
the Python and PHP middleware and AgentCake itself check too.

## Licence and sources

MIT. The response-head hook and the `Server-Timing` parsing are adapted from botscent (MIT); the list of static-file
extensions follows @knownagents/sdk 3.1.0 (Apache-2.0; the rule only, no code). See `THIRD_PARTY.md` at the top of the
AgentCake repository.
