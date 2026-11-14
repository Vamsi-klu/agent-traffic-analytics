# AgentCake site middleware for PHP

AgentCake records visits through its page script, `cake.js`. Some facts about a page request are seen only by your
site's server: the Web Bot Auth signature an agent such as ChatGPT agent adds, and the fetch metadata of the very first
page. This middleware packs them into one signed token and sets it on that page's own response:

```text
Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"
```

`cake.js` reads the token from the page's navigation entry and sends it with the visit. AgentCake checks the signature
with the secret it shares with your server, accepts each token once and only for 15 minutes, and shows what your server
saw on the session's page ("Server half"). The token is the one AgentCake's Node middleware (`edge/node`) makes for the
same request, byte for byte. The Web Bot Auth headers go into it as sent; AgentCake verifies the signature, not your
server.

- PHP 7.4 or newer. Nothing to install: it uses only the parts of PHP that are always on (hash, JSON, PCRE,
  `random_bytes`).
- Three files that stay side by side: `cake_edge.php` (the mounting), `cake_edge_format.php` (the token's format) and
  `cake_edge.json` (every value they use).
- It does nothing until it has a secret.
- It sets no cookie, stores nothing and makes no network request.
- It is not published to Packagist. It comes with AgentCake, in the edge folder of the installed package
  (`agentcake/edge/`; a checkout has it at `edge/`): copy the three files from `<edge folder>/php/` into your site,
  for example into a `cake/` folder. `agentcake setup --print --site` prints the full path.
- On WordPress, use the AgentCake plugin instead (`edge/wordpress/agentcake`): it carries these same files.

## The secret

On the machine that runs AgentCake:

```sh
agentcake secret init
agentcake secret print
```

Give the printed value to PHP as the environment variable `CAKE_SERVER_TIMING_SECRET`: with PHP-FPM,
`env[CAKE_SERVER_TIMING_SECRET] = ...` in the pool's configuration; with Apache, `SetEnv CAKE_SERVER_TIMING_SECRET ...`
in a configuration file only the server reads. Or pass it as the `secret` option from your own secret store. Without
it, or with a value shorter than 32 bytes, the middleware does nothing (a value that is too short is named in the PHP
error log).

## Mount it

### Any PHP site

```php
<?php
require __DIR__ . '/cake/cake_edge.php';

(new \AgentCake\Edge([
    'clientIp' => function (array $server): ?string {
        return $server['REMOTE_ADDR'] ?? null;
    },
]))->sendHeader();
```

Put it at the top of the front controller (`index.php`), or of a file every page includes first, before any output:
`sendHeader()` adds a header, and PHP sends the head with the first byte of the page. To cover every PHP page without
editing them, put those lines in a file of their own and name it in `php.ini`'s `auto_prepend_file`.

`sendHeader()` keeps the `Server-Timing` entries already set. Code that runs later and calls
`header('Server-Timing: ...')` replaces the header, cake's entry with it: such code should pass `false` as `header()`'s
second argument, which adds a line instead.

### Laravel, Symfony or any framework with a response object

```php
$token = (new \AgentCake\Edge())->tokenForRequest(); // null: no token for this request
// ... the framework makes $response ...
if ($token !== null) {
    $response->headers->set('Server-Timing', \AgentCake\Edge::withCakeEntry($response->headers->all('server-timing'), $token));
}
```

In Laravel this is a middleware's `handle($request, $next)`, with `$response = $next($request)` in the middle.

### WordPress

Install the AgentCake plugin (`edge/wordpress/agentcake`, see its README): it sets the header and adds the `cake.js`
line, with a settings page for AgentCake's address and site key.

## Options

Every default is in `cake_edge.json`; its values are the Node middleware's (`edge/node/defaults.json`, `headers.json`),
and a test keeps them the same.

| Option | Default | What it does |
|---|---|---|
| `secret` | the `CAKE_SERVER_TIMING_SECRET` variable | The shared secret, at least 32 bytes long. |
| `clientIp` | none | A function of the `$_SERVER` array returning the visitor's address as your site knows it. Without it the token has no network key (`ik`). Never use the leftmost `X-Forwarded-For` entry: anyone can write it. |
| `noStore` | `false` | `true` sets `Cache-Control: private, no-store` on HTML responses to page requests. See "Caching and 304". |
| `maxHeaderNames` | `40` | How many header names `hn` keeps. |
| `cut` | see `cake_edge.json` | The longest each value may be, by field (`user_agent`, `accept_language`, ...). |
| `skipExtensions` | see `cake_edge.json` | Paths ending in these never get a token. |
| `secretEnv` | `CAKE_SERVER_TIMING_SECRET` | The environment variable the secret is read from. |
| `warn` | `error_log` | Where warnings go: an unknown option, a value of the wrong kind, a secret that is too short. |

A mistake in the setup costs the token, never the page: an unknown option or a value of the wrong kind is named once
and the default kept, and a missing `cake_edge.json` turns the middleware off with one line in the error log.

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
| `p` | The path as sent (`REQUEST_URI`), without the query string. |
| `sf` | `Sec-Fetch-Site`, `-Mode`, `-Dest` and `-User` as sent (`s`, `m`, `d`, `u`). |
| `sp` | `Sec-Purpose` (a prefetch or prerender), or `null`. |
| `md` | Whether `Accept` lists `text/markdown`. |
| `al` | `Accept-Language`. |
| `ch` | The low-entropy client hints `sec-ch-ua`, `sec-ch-ua-platform` and `sec-ch-ua-mobile` (`ua`, `pf`, `mb`). |
| `ua` | `User-Agent`. |
| `hn` | The request's header names in the order your server hands them over, names only (see below). |
| `sg` | `Signature-Agent` as sent (`a`), and whether `Signature` (`s`) and `Signature-Input` (`i`) came with the request. |
| `ik` | The network key: the first 16 hex characters of HMAC-SHA256(secret, `ip|<UTC day>|<the /24 or /48 of the address>`). AgentCake computes the same from `cake.js`'s own request and keeps only whether the two match. |
| `bs` | botscent's verdict. botscent is a JavaScript library, so from PHP it is always `null`. |
| `bsv` | botscent's version: always `null` from PHP. |

Values are cut to the lengths in `cake_edge.json` and control characters are removed. Header bytes are read one
character per byte, as Node reads them. The token never holds an IP address, a cookie, an authorization value or the
value of any other header.

The header names come from `getallheaders()` where PHP has it (Apache's module, PHP's built-in server and PHP-FPM),
in the order sent; otherwise from `$_SERVER`'s `HTTP_` keys, where `_` reads as `-` and `Content-Type` and
`Content-Length` are not listed. Either way your server merges a header line sent twice into one, so its name is
listed once and its values come joined the server's way.

## Caching and 304

By default the middleware leaves your caching headers alone. Two cases need a choice:

- **A CDN or shared cache stores your HTML.** Every visitor then gets the same stored token, and AgentCake accepts a
  token once, so only one of those visits has a server half. Mark the HTML `private`, or turn on `noStore`.
- **Your HTML is revalidated** (`Cache-Control: no-cache` with an `ETag` or `Last-Modified`, answered with `304 Not
  Modified`). The 304 carries a new token, and browsers show the page that new token (below). `noStore: true` avoids
  304s for HTML altogether.

Tried with Chromium 149, WebKit 27.2 (Safari's engine, as Playwright builds it) and Firefox 157, headless, on a test
site with and without `noStore`, through the Node middleware, which makes the same tokens:

- **At a 304** each of them shows the page the 304's own new token, and keeps that token with its stored copy. WebKit
  reloads a page with a plain request (a 200 with a new token) where the other two send a 304.
- **Going back or forward** to a page they stored, without asking your server, they show the token stored with it.
  AgentCake keeps every token once: another page view of the same visit bringing it again is counted as a reuse (one
  server half, not a replay, no error); another visit bringing it (a new tab) is refused as a replay, and a token older
  than 15 minutes as stale, so that page view has no server half. A page the back-forward cache keeps alive (Chrome's,
  even with `noStore`) is the same page view and sends nothing new.

## Check it

`example.php` is a two-page site that shows, on each page, the token its own navigation entry carries (what `cake.js`
reads):

```sh
CAKE_SERVER_TIMING_SECRET=<secret> php -S 127.0.0.1:8123 edge/php/example.php
```

## Tests

```sh
php edge/php/tests/run.php
```

No PHPUnit: the tests have no dependencies either. They pass on PHP 7.4.33 and 8.3.36. They hold the middleware to
the shared test vectors, `tests/vectors/edge_token.json`, which the Node and Python middleware and AgentCake check too:
every vector's token byte for byte, from the request as text and from the request as `$_SERVER` and `getallheaders()`
give it.

## Licence and sources

MIT, like AgentCake. Splitting a `Server-Timing` value into entries is adapted from botscent (MIT) as the Node
middleware does; the list of static-file extensions follows @knownagents/sdk 3.1.0 (Apache-2.0; the rule only, no
code). See `THIRD_PARTY.md` at the top of the AgentCake repository.
