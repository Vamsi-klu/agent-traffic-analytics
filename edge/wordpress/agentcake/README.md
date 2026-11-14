# AgentCake for WordPress

AgentCake records visits through its page script, `cake.js`. Some facts about a page request are seen only by your
site's server: the Web Bot Auth signature an agent such as ChatGPT agent adds, and the fetch metadata of the very first
page. This plugin is AgentCake's server half for WordPress. On every page it:

- sets one signed token in the page's own response, `Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"`,
  which `cake.js` reads and sends with the visit, so AgentCake shows what your server saw ("Server half");
- adds the `cake.js` line to the page's head, with AgentCake's address and your site key.

It wraps AgentCake's PHP site middleware (`cake_edge.php`, `cake_edge_format.php`, `cake_edge.json`, the same files as
`edge/php`), so the token is the one the Node, Python and PHP middleware make for the same request, byte for byte.

- WordPress 5.7 or newer, PHP 7.4 or newer.
- Only WordPress's own hooks: `send_headers` for the header, `wp_head` for the `cake.js` line, the Settings API for the
  settings page. It installs nothing else and needs no other plugin.
- It sets no cookie, makes no network request and stores nothing but its settings (one option). The page script loads
  from AgentCake.
- It is not published on wordpress.org. It comes with AgentCake. MIT licence, which is compatible with the GPL.

## Install

The plugin folder comes with AgentCake, in the edge folder of the installed package (`agentcake/edge/`; a checkout
has it at `edge/`); `agentcake setup --print --site` prints its full path. Zip it (into your home folder, so the
installed package stays as it is) and upload the zip under **Plugins > Add New Plugin > Upload Plugin**:

```sh
cd <edge folder>/wordpress && zip -r ~/agentcake.zip agentcake
```

or copy the `agentcake` folder into `wp-content/plugins/`. Then activate **AgentCake** under **Plugins**.

## Set it up

1. On the machine that runs AgentCake, `agentcake setup --print --site` prints AgentCake's address and the site key.
2. Under **Settings > AgentCake**, fill in **AgentCake address** (for example `https://cake.example.com`, where
   visitors' browsers reach AgentCake) and **Site key** (`ck_...`). From then on every page's head has the line
   `<script data-site="ck_..." defer src="https://cake.example.com/cake.js"></script>`. If your theme has the line
   already, turn off **cake.js line**.
3. Give the plugin the server half's secret. On AgentCake's machine, `agentcake secret init`, then
   `agentcake secret print`. Add the printed value to `wp-config.php`, above the line that says to stop editing:

   ```php
   define( 'CAKE_SERVER_TIMING_SECRET', '...' );
   ```

   An environment variable of that name works too. The secret is never stored in the database and the settings page
   never shows it: it only says whether pages carry a token. Without a secret, or with one shorter than 32 bytes, pages
   carry no token and the `cake.js` line still works.

## What it adds to a page

- **The header**, in WordPress's `send_headers` action, before the page goes out. Only page requests get a token: a
  `GET` whose `Sec-Fetch-Dest` is `document`, or, from a client that sends no fetch metadata, a `GET` that accepts
  `text/html`. Never a frame, a subresource, a `POST` or `HEAD`, a static file or a dot-file. The admin screens, the REST
  API, `admin-ajax.php` and `wp-cron.php` never run `send_headers`, so they never get one. The `Server-Timing` entries
  already set stay; a plugin that later replaces the whole header with `header('Server-Timing: ...')` drops cake's entry.
- **The `cake.js` line**, in `wp_head`, through `wp_print_script_tag()`, so a plugin that adds a nonce for a Content
  Security Policy (the `wp_script_attributes` filter) adds it here too.
- **Prefetched pages.** WordPress (6.8 and newer) prefetches a link when the visitor points at it (Speculation Rules).
  The prefetch is a page request and gets its token, with `Sec-Purpose: prefetch` inside; the page the visitor then
  opens shows that token. Checked in Chromium 149 on WordPress 7.1.4.

## Settings

| Setting | Default | What it does |
|---|---|---|
| AgentCake address | none | Where the page script loads from: `<address>/cake.js`. |
| Site key | none | AgentCake's site key, `ck_` and 3 to 40 letters, digits or `_`. |
| cake.js line | on | Adds the line to every page's head. Turn it off when the theme has it. |
| Visitor address | not used | Where the network key (`ik`) comes from: nowhere, or the connection's address (`REMOTE_ADDR`). Behind a proxy or a CDN the connection's address is the proxy's: leave it off, or give the visitor's address with the `agentcake_client_ip` filter (below). Never use the leftmost `X-Forwarded-For` entry: anyone can write it. |
| Page caching | off | Keeps pages out of caches so that every page view has its own token: `Cache-Control: private, no-store` (browsers, CDNs and proxies) and `DONOTCACHEPAGE` (page cache plugins). See below. |

Behind Cloudflare, for example, and only when the site takes traffic from Cloudflare alone (anyone else could write
the header):

```php
add_filter( 'agentcake_client_ip', function ( $address, $server ) {
    return $server['HTTP_CF_CONNECTING_IP'] ?? $address;
}, 10, 2 );
```

## Page cache plugins

A page cache stores a page once and serves the stored copy to the visitors after that. What happens to the token
depends on what the cache stores:

- **Only the page** (Cache Enabler, WP Super Cache, WP Fastest Cache and most page cache plugins, which serve the stored
  HTML before WordPress loads). The visitor whose visit made the page gets a token. Every visitor after that gets the
  stored page with the `cake.js` line and no token: those page views have no server half. AgentCake still records
  them through `cake.js`. Tried with Cache Enabler on WordPress 7.1.4: the stored page went out with Cache Enabler's
  own header and no `Server-Timing`.
- **The whole response, headers included** (a CDN's or a reverse proxy's full-page cache, Varnish, nginx's
  `fastcgi_cache`). Every visitor gets the same stored token. AgentCake accepts a token once: the first session that
  sends it gets the server half. When the same visitor sees the stored token again, AgentCake counts it as **reuse**,
  as it does for a page the browser shows from its own cache when going back: no error, and the page view is not
  counted twice (a page the browser revalidates, a 304, brings a new token). Another
  visitor's session that sends the same token is refused as a replay, so that page view has no server half.

To give every page view its own token, turn on **Page caching** under **Settings > AgentCake**, then clear the page
cache once (pages stored before keep going out until then). Pages then go out with `Cache-Control: private, no-store`,
which browsers, CDNs and proxies do not store, and with `DONOTCACHEPAGE` defined, which page cache plugins read as "do
not store this page". Tried with Cache Enabler: every page view had its own token and nothing was stored. This trades
the page cache for the server half: leave it off if the site needs its page cache, and accept that cached page views
have none.

## What the token holds

Any script on the page can read `Server-Timing`. The signature proves that the token comes from your site; it does not
hide it. So the token holds only what the browser sent anyway.

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
| `hn` | The request's header names in the order the web server hands them to PHP, names only. |
| `sg` | `Signature-Agent` as sent (`a`), and whether `Signature` (`s`) and `Signature-Input` (`i`) came with the request. |
| `ik` | The network key: the first 16 hex characters of HMAC-SHA256(secret, `ip|<UTC day>|<the /24 or /48 of the address>`), only with **Visitor address** set. AgentCake computes the same from `cake.js`'s own request and keeps only whether the two match. |
| `bs` | botscent's verdict. botscent is a JavaScript library, so from WordPress it is always `null`. |
| `bsv` | botscent's version: always `null` from WordPress. |

Values are cut to the lengths in `cake_edge.json` and control characters are removed. The token never holds an IP
address, a cookie, an authorization value or the value of any other header. `edge/php/README.md` has the details of how
PHP hands over the request.

## Uninstall

Deleting the plugin under **Plugins** removes its settings, the one option it keeps. Remove the
`CAKE_SERVER_TIMING_SECRET` line from `wp-config.php` by hand.

## Tests

`php edge/php/tests/run.php` (from the AgentCake folder) checks the middleware against the shared test vectors and that
this plugin carries the same middleware files as `edge/php`. The plugin itself was tried in WordPress Playground
(`@wp-playground/cli` 3.1.64, WordPress 7.1.4, PHP 8.3) with Chromium, with and without a page cache plugin.

## Licence and sources

MIT, like AgentCake, which is compatible with the GPL that WordPress uses. Written from the WordPress Plugin Handbook
and its API references (plugin header, Settings API, `send_headers`, `wp_head`, `wp_print_script_tag`, uninstall), with
no code copied from other plugins. See `THIRD_PARTY.md` at the top of the AgentCake repository.
