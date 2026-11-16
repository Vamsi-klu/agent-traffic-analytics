# AgentCake site middleware for Python

AgentCake records visits through its page script, `cake.js`. Some facts about a page request are seen only by your
site's server: the Web Bot Auth signature an agent such as ChatGPT adds, and the fetch metadata of the very first
page. This middleware packs them into one signed token and sets it on that page's own response:

```text
Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"
```

`cake.js` reads the token from the page's navigation entry and sends it with the visit. AgentCake checks the signature
with the secret it shares with your server, accepts each token once and only for 15 minutes, and shows what your server
saw on the session's page ("Server middleware"). The token is the one AgentCake's Node middleware (`edge/node`) makes
for the same request, byte for byte.

- WSGI (Flask, Django, Bottle, Pyramid, any WSGI app) and ASGI (FastAPI, Starlette, Django's ASGI app).
- No dependencies: one file, `cake_edge.py`, and its settings, `cake_edge.json`. Python 3.9 or newer.
- It does nothing until it has a secret.
- It sets no cookie, stores nothing and makes no network request.
- It is not published to PyPI. It comes with AgentCake, in the edge folder of the installed package
  (`agentcake/edge/`; a checkout has it at `edge/`): copy `<edge folder>/python/cake_edge.py` and `cake_edge.json`
  into your project, side by side, where your app can import `cake_edge`. `agentcake setup --print --site` prints
  the full path.

## The secret

On the machine that runs AgentCake:

```sh
agentcake secret init
agentcake secret print
```

Give the printed value to your site's server as the environment variable `CAKE_SERVER_TIMING_SECRET`. Pipe it into your
secret store rather than pasting it into a file. Without the variable, or with a value shorter than 32 bytes, the
middleware passes every request through untouched (a value that is too short is named once in a warning, through the
`cake_edge` logger).

## Mount it

Mount it around the whole app, so it sees every page before your routes and static files answer it.

### Flask

```python
from flask import Flask
from cake_edge import CakeEdgeWSGI

app = Flask(__name__)
app.wsgi_app = CakeEdgeWSGI(app.wsgi_app, client_ip=lambda environ: environ.get("REMOTE_ADDR"))
```

Behind a load balancer, let Werkzeug's `ProxyFix` set `REMOTE_ADDR` first, so cake reads the visitor's address:
`app.wsgi_app = ProxyFix(CakeEdgeWSGI(app.wsgi_app, client_ip=...), x_for=1)`.

### FastAPI or Starlette

```python
from fastapi import FastAPI
from cake_edge import CakeEdgeASGI

app = FastAPI()
app.add_middleware(CakeEdgeASGI, client_ip=lambda scope: (scope.get("client") or [None])[0])
```

A streaming response (`StreamingResponse`) gets the entry in its head, before the first chunk, and nothing is held back.
Behind a load balancer, run Uvicorn with `--proxy-headers --forwarded-allow-ips=<the balancer's address>` so that
`scope["client"]` is the visitor's address.

### Django

`wsgi.py` (also what `manage.py runserver` serves):

```python
from django.core.wsgi import get_wsgi_application
from cake_edge import CakeEdgeWSGI

application = CakeEdgeWSGI(get_wsgi_application(), client_ip=lambda environ: environ.get("REMOTE_ADDR"))
```

or `asgi.py`:

```python
from django.core.asgi import get_asgi_application
from cake_edge import CakeEdgeASGI

application = CakeEdgeASGI(get_asgi_application(), client_ip=lambda scope: (scope.get("client") or [None])[0])
```

### Any other framework

```python
from cake_edge import CakeEdge, with_cake_entry

edge = CakeEdge(client_ip=...)
token = edge.token(method, target, header_lines, subject)  # header_lines: (name, value) in the order sent; None: no token
```

Set `Server-Timing` on that request's response to `with_cake_entry([your own Server-Timing values], token)`.

## Options

Keyword arguments of `CakeEdgeWSGI(app, ...)` and `CakeEdgeASGI(app, ...)`. Every default is in `cake_edge.json`; its
values are the Node middleware's (`edge/node/defaults.json`, `headers.json`), and a test keeps them the same.

| Option | Default | What it does |
|---|---|---|
| `secret` | the `CAKE_SERVER_TIMING_SECRET` variable | The shared secret: text or bytes, at least 32 bytes long. |
| `client_ip` | none | A function of the WSGI environ or the ASGI scope returning the visitor's address as your app knows it. Without it the token has no network key (`ik`). Never use the leftmost `X-Forwarded-For` entry: anyone can write it. |
| `no_store` | `False` | `True` sets `Cache-Control: private, no-store` on HTML responses to page requests. See "Caching and 304". |
| `max_header_names` | `40` | How many header names `hn` keeps. |
| `cut` | see `cake_edge.json` | The longest each value may be, by field (`user_agent`, `accept_language`, ...). |
| `skip_extensions` | see `cake_edge.json` | Paths ending in these never get a token. |
| `secret_env` | `CAKE_SERVER_TIMING_SECRET` | The environment variable the secret is read from. |

An option nobody knows, or a value of the wrong kind, is named once in a warning and the default is kept: a mistake in
the setup costs the token, never the pages.

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
| `hn` | The request's header names in the order your server hands them over, names only (see below). |
| `sg` | `Signature-Agent` as sent (`a`), and whether `Signature` (`s`) and `Signature-Input` (`i`) came with the request. |
| `ik` | The network key: the first 16 hex characters of HMAC-SHA256(secret, `ip|<UTC day>|<the /24 or /48 of the address>`). AgentCake computes the same from `cake.js`'s own request and keeps only whether the two match. |
| `bs` | botscent's verdict. botscent is a JavaScript library, so from Python it is always `null`. |
| `bsv` | botscent's version: always `null` from Python. |

Values are cut to the lengths in `cake_edge.json` and control characters are removed. The token never holds an IP
address, a cookie, an authorization value or the value of any other header.

### What your server hands over

The middleware reads the request the way your server gives it, so a few facts depend on the server:

- **The path.** WSGI: `REQUEST_URI` or `RAW_URI` as sent (Gunicorn, uWSGI, Werkzeug, mod_wsgi); a server without them
  (Python's own `wsgiref`) gives `PATH_INFO` decoded, and the middleware percent-encodes it again. ASGI: `raw_path` as
  sent (Uvicorn, Hypercorn, Daphne), else `path` encoded again.
- **The header names.** ASGI servers hand over every header line in order, so `hn` is what the Node middleware sees.
  A WSGI server gives one `HTTP_` key per name, in the order sent: a line sent twice is listed once, `_` reads as `-`,
  and `Content-Type` and `Content-Length` (not `HTTP_` keys) are not listed.
- **A repeated line.** ASGI: joined with `, ` as the Node middleware joins it. WSGI: joined by the server, its own way
  (`wsgiref` and Gunicorn use `,`).

## Caching and 304

By default the middleware leaves your caching headers alone. Two cases need a choice:

- **A CDN or shared cache stores your HTML.** Every visitor then gets the same stored token, and AgentCake accepts a
  token once, so only one of those visits has server middleware data. Mark the HTML `private`, or turn on `no_store`.
- **Your HTML is revalidated** (`Cache-Control: no-cache` with an `ETag` or `Last-Modified`, answered with `304 Not
  Modified`). The 304 carries a new token, and browsers show the page that new token (below). `no_store=True` avoids
  304s for HTML altogether.

Tried with Chromium 149, WebKit 27.2 (Safari's engine, as Playwright builds it) and Firefox 157, headless, on a test
site with and without `no_store`, through the Node middleware, which makes the same tokens:

- **At a 304** each of them shows the page the 304's own new token, and keeps that token with its stored copy. WebKit
  reloads a page with a plain request (a 200 with a new token) where the other two send a 304.
- **Going back or forward** to a page they stored, without asking your server, they show the token stored with it.
  AgentCake keeps every token once: another page view of the same visit bringing it again is counted as a reuse (one
  server middleware record, not a replay, no error); another visit bringing it (a new tab) is refused as a replay, and
  a token older than 15 minutes as stale, so that page view has no server middleware data. A page the back-forward
  cache keeps alive (Chrome's, even with `no_store`) is the same page view and sends nothing new.

## Tests

From the AgentCake folder:

```sh
python3 -I -m unittest discover -s tests -p "test_edge_python*.py" -v
```

They hold the middleware to the shared test vectors, `tests/vectors/edge_token.json`, which the Node middleware and
AgentCake check too: every vector's token byte for byte from `mint_token()`, through the WSGI middleware and through
the ASGI middleware.

## Licence and sources

MIT, like AgentCake. Splitting a `Server-Timing` value into entries is adapted from botscent (MIT) as the Node
middleware does; the list of static-file extensions follows @knownagents/sdk 3.1.0 (Apache-2.0; the rule only, no
code). See `THIRD_PARTY.md` at the top of the AgentCake repository.
