# Privacy in AgentCake

What AgentCake records about the visits to your website, what it never records, where it keeps what it records,
for how long, and how to delete it. It is written for site owners. A notice you can adapt for your own visitors is
in [`docs/privacy-notice-template.md`](docs/privacy-notice-template.md). Neither file is legal advice.

## What AgentCake is for

For each visit to a website, AgentCake tells whether a human or an AI agent was using the page, and which agent. It
does not try to find out who a visitor is, and it keeps nothing that names one. A site that signs its visitors in can
have each of them counted once across browsers and devices: AgentCake then keeps a one-way hash of the site's own id
for the visitor, never the id ("Counting a signed-in visitor once", below).

## What the page script records

The page script, `cake.js`, is the one line a site adds. It records:

- **The session replay** (rrweb): the page and how it changes. Every form input is masked: only its length is kept.
  Text typed into editable elements (`contenteditable`) is masked the same way. Elements marked `data-cake-private`,
  password fields and payment card fields (`autocomplete="cc-…"`) are not recorded at all: the replay shows an empty
  box of their size. So are the parts of your pages you list on the settings page ("Hide these parts of your pages",
  the `hide_selectors` setting, CSS selectors).
- **Raw input events**: where the mouse, pointer or finger was and when, wheel and scroll movements, and whether each
  event came from the device (the browser's `isTrusted`). A key press is kept only as its time and its class (letter,
  digit, space, symbol, delete, enter, tab, modifier, arrow, other), never which key. An input is kept only as the
  kind of input (typed, pasted, deleted, …) and the field's length, never the text. Nothing typed into a private
  element is kept, not even its timing.
- **What the browser shows about itself**: user agent and client hints, screen and window sizes, time zone, the
  graphics renderer, traces automation tools leave, the results of the bundled BotD and botscent checks, how many
  media devices of each kind exist (no names), whether a few fonts are installed, whether the browser recognises a system
  font name only Apple's systems have while it says it runs on another system (one answer: yes, no or can't tell; no
  font names or sizes leave the page), and when an agent product's own
  marks (such as Claude in Chrome's "working" tag) appeared on the page and went away: which mark and when, nothing
  else of the page.
- **Where the visit came from**: the domain of the page that linked to yours (the host of `document.referrer`, such
  as `www.google.com`, never that page's address), the campaign parameters in the address of the page the visitor
  arrived on (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term` and `gad_source`, each cut to 200
  characters), and which ad-click parameters that address carries (`gclid`, `fbclid`, `msclkid` and the others listed
  in `agentcake/data/cakejs.json`): their names only. (The page's address, which every upload carries, still holds
  its whole query string, values included, as it always has.) With them, the browser's language and its time zone offset, which the
  environment record above also holds.
- **A visitor id**: a random id the script keeps in the visitor's browser (localStorage) and sends with each upload,
  so that AgentCake can count visitors. It is made from nothing about the device or the visitor, and it expires a
  year after the visitor's last page view on your site ("What the script keeps in the visitor's browser", below).
- **An identify hash, only when your site calls `window.cake.identify(id)`** (after a visitor signs in, with your own
  id for them): the SHA-256 hash of your site key, a colon and that id, made in the visitor's browser. Only the hash is
  sent; the id itself never leaves the browser. The script keeps it with the visitor id and sends it with every later
  upload from that browser ("Counting a signed-in visitor once", below).
- **The server middleware token** the site's own server puts in the page's response, when the site runs AgentCake's
  middleware (below).

The rules are in `agentcake/data/privacy.json` and are not settings: no configuration turns input masking off or makes
private elements recorded; `hide_selectors` can only hide more. One setting adds to what the script looks at:
`hook_dom` (off unless you turn it on) wraps your site's own document lookups to notice an automation tool calling
them; when one does, it records the method, its first argument and the calls that led to it, never anything typed. The upload format is [`docs/collect-format.md`](docs/collect-format.md).

## What AgentCake keeps of each upload

- **The visit**: when it began and when it was last seen, the page's address, the browser's User-Agent, whether the
  browser said it is automated (`navigator.webdriver`), the `Sec-Fetch-*` headers of the upload request, and whether
  the upload came from your site or from another one (another site's uploads are kept, but left out of the dashboard).
  A visit is one session of one browser tab: after 30 minutes without activity, or after 24 hours, the tab's next
  activity begins a new session, and AgentCake applies the same rules to an older page script that does not.
- **What the dashboard groups sessions by**: the visitor id and, when the session's uploads carried one, the
  identify hash; where the session came from (the referring domain, the
  campaign parameters, the names of the ad-click parameters, and the channel these make, such as Organic Search); the
  browser, operating system and device type read from the User-Agent; the language and time zone offset; and, on a
  server with `trust_lb` on, the country, region and city your load balancer gives.
- **Each upload's header**: when it was made and when it arrived, the page's address at that moment, why it was sent,
  how many records of each kind it held, and what `cake.js` itself had to drop.
- **Each upload request**: the values of a few of its headers (`User-Agent`, `Accept-Language`, the low-entropy client
  hints `Sec-CH-UA`, `Sec-CH-UA-Mobile` and `Sec-CH-UA-Platform`, `Origin`, the `Sec-Fetch-*` headers and the Web Bot
  Auth headers), the names of all its headers in the order they came, and where it came from. Of every other header
  only the name is kept: never the value of a cookie, a credential, the `Referer` or anything a proxy adds. (The
  domain of the page the visitor came from is what the page script sends, above; the address is never sent.)
- **On a server, with `trust_lb` on**: what your load balancer says about the connection: the country, the region and
  city (when it sends them), the published network range the address belongs to (an AI provider's published agent ranges, for example) and the kind of network
  (a relay such as iCloud Private Relay, a CDN, a cloud provider), the TLS fingerprint (JA4), the protocol, and the Web
  Bot Auth signature headers the request carried. And two salted hashes: of the address, and of its /24 (IPv4) or /48
  (IPv6) network. They are HMACs with a random salt that AgentCake keeps in its database and replaces every
  `ip_salt_days` (30 by default): within one period they tell whether two uploads came from the same address or
  network; once the salt is replaced, nothing can match them to an address any more.
- **Refused uploads**: only how many, per reason.
- **Classifications**: AgentCake's own conclusions: which stretches of the visit a human or an agent acted in, the
  agent's name and the evidence for it.

The visitor's IP address is never stored. On a server AgentCake uses it for a moment, to look up which published range
holds it, to hash it with the salt and to compare networks with the server middleware's token, then drops it. Without
`trust_lb` (on your own computer) the collector does not read it at all.

## The server middleware

When your site's server runs AgentCake's middleware (`edge/`), it signs a token into each page's response and
`cake.js` forwards it. AgentCake keeps each token it verifies: when your server saw the request, the path (without
the query string), the request's `Sec-Fetch-*` and `Sec-Purpose` headers, `Accept-Language`, the low-entropy client
hints, the User-Agent, the names (not the values) of the request's headers, the Web Bot Auth `Signature-Agent` and
whether a signature came with it, botscent's verdict if your server runs botscent, and a network key: the first 16
hex characters of an HMAC of the address's /24 (IPv4) or /48 (IPv6) and the day, keyed with the secret your server
and AgentCake share. The key is not the address. Anyone who has the secret, which is kept in the same data folder,
could work out the /24 or /48 by trying every network; never the full address.

## Your web server's log

Optional, for a site without the middleware: `agentcake logs import`, run on the machine that holds your web server's
access log, reads the log where it lies and sends its page requests to your own AgentCake (on the same machine, or the
server you name with `--to`), signed with the secret they share. A request that matches no visit is dropped whole. Of
one that matches a visit, AgentCake keeps what it keeps of an upload: the values of `User-Agent`, `Accept-Language`,
`Sec-Fetch-*`, `Sec-CH-UA` and the Web Bot Auth headers, the method, the path without its query, the status, which
published range holds the address and the two salted hashes of the address, and whether a Web Bot Auth signature
verifies. Never the address, the query, cookies or credentials ([`SERVER.md`](SERVER.md), "Server logs").

## What it never records

What is typed, which keys are pressed, passwords, card numbers, the content of private elements, cookies (the script
reads none, sets none and sends its uploads without credentials, and the collector reads no cookie header),
authorization headers, the visitor's IP address, the address of the page the visitor came from (only its domain), the
id your site gives `window.cake.identify()` (only its hash), and anything the site stores in the visitor's browser.

## Where it goes, and what goes online

AgentCake does not collect usage data or telemetry.

What visitors' browsers send goes only to your own AgentCake: the address `cake.js` was loaded from. No third party
and no analytics service receives it, the makers of AgentCake included.

AgentCake sends no installation event, no usage data, no update checks and no crash reports, and nothing about your
site or its visits. Apart from the registration below, sent once when you press "Register and continue", it makes no
request to the internet while it runs. The local page loads nothing from the internet (its fonts and icons are
bundled). The lists AgentCake names agents and published networks from come with each release. Only `agentcake lists
update`, which you run by hand, downloads newer copies, from the public sources listed in
`agentcake/data/lists/sources.json` (GitHub files and the address and key lists the operators publish); it sends
nothing about your site or its visits. `agentcake ping` talks only to your own AgentCake on `127.0.0.1`. So does
`agentcake doctor`, and once you have saved your own site's address (`site_url`), it also opens that page of your site
to check AgentCake's page script and token there; the request carries test headers only, nothing about your visits.
`agentcake logs import` sends your web server's page requests only to your own AgentCake ("Your web server's log",
above).

### Registration: once, when you first open the dashboard

AgentCake is an open-source project. We're looking for early users to help shape what we build next. That is why the
first time you open the local dashboard, AgentCake asks you to register: with your e-mail address we can ask you for
feedback and tell you about product updates. You give your e-mail address (required) and your company (optional),
and there is a separate box for product updates: you get product update e-mails only if you tick it, and every one of
them lets you unsubscribe. The page says: "Your registration details will be sent to Tartini AI. No website traffic,
session replay or product usage telemetry is sent." Next to the button, "See what's sent" shows exactly what will be
sent.

- **What is sent**: your e-mail address, your company if you gave one, whether you ticked the product-updates box, and
  the version of the consent text you were shown. Nothing else: no installation id, no AgentCake version, no usage
  data, nothing of your website's traffic, no session replay, not your site's domain. As with any request on the
  internet, the receiving server sees the network address the request comes from.
- **When**: once, when you press "Register and continue". Nothing is sent before that, and nothing afterwards. That you
  registered, and the text that was sent, are kept in AgentCake's own database, once for each data folder, so that
  the settings page can show them.
- **Where**: to Tartini AI (tartini.ai), whose server records it in its log, kept for 30 days, and once a day sends
  that day's new registrations to admin@tartini.ai in one e-mail; it is not stored in a database. The address it is
  sent to is the `register_url` setting; the request carries the text "See what's sent" shows, exactly, and a
  User-Agent of only the product's name.
- **What waits for it**: only the local dashboard. The collecting of visits by `cake.js`, the command line and
  `agentcake doctor` all work without registering.
- **When it cannot be sent** (no internet connection, the address does not answer or does not accept it, or
  `register_url` is empty): the page says so and lets you in, and asks again the next time you open the dashboard.
  AgentCake never retries in the background and keeps nothing of it.
- **Seeing what you sent, and taking it back**: the settings page shows what you sent. To stop product updates, use
  the unsubscribe link in any of them; to have your registration deleted, write to admin@tartini.ai.
- **No switch**: no setting turns registration off (an empty `register_url` only means that nothing can be sent: the
  card still asks). AgentCake is open source: you may remove it from your own copy of the code.

The bundled BotD library would send a usage request of its own; that request is removed from AgentCake's copy
([`THIRD_PARTY.md`](THIRD_PARTY.md)).

## Consent

The site decides when a visit may be recorded. Either:

1. add the `cake.js` line only after the visitor agreed; or
2. add it with `data-consent="required"` and call `window.cake.start()` once they agree. Until then the script does
   nothing at all: no listener, no storage, no request.

When the visitor says no, call `window.cake.stop()`: from then on nothing is recorded or sent from that page, what had
not been sent yet is dropped, and the visit id, the visitor id and its identify hash are deleted from the browser. Consent code that may run before `cake.js` has loaded can
queue the call: `window.cake = window.cake || []; window.cake.push('start')` (or `'stop'`).

What was recorded before a refusal stays in AgentCake: the script sends nothing after `stop()`, so AgentCake is not
told about the refusal. To delete that visit too, your consent code can read the visit id (`sessionStorage` key
`cake_sid`) before it calls `window.cake.stop()` and hand it to your server, which runs
`agentcake delete --visitor <that id>` (below). The id names the tab's current session; a session that ended more
than 30 minutes earlier had an id of its own.

## What the script keeps in the visitor's browser

In `sessionStorage`, which ends with the browser tab: `cake_sid` (the visit id, random; a new one after 30 minutes
without activity or 24 hours), `cake_clock` (when that session began and when it last saw activity), `cake_pn` (the
number of pages seen in the visit), `cake_frames` (a once-per-visit check is done) and `cake_pending` (uploads waiting
to be sent again).

In `localStorage`, one key: `cake_vid`, the visitor id (random), when it was last used and, after your site called
`window.cake.identify()`, the identify hash. It is replaced by a new one, without the hash, once a year has passed
without a page view on your site, and when your site calls `window.cake.reset()`. AgentCake uses it only to count
visitors (Visitors on the dashboard); it is not a cookie and is never sent to your site's server. Where the browser
refuses `localStorage`, the id and the hash live only as long as the page.

No cookies. `window.cake.stop()` removes all of them.

## Counting a signed-in visitor once

Without it, every browser is a visitor of its own: one person who visits your site on a laptop and a phone counts
twice. A site with sign-in can tell AgentCake which visits belong to the same signed-in visitor:

```js
// after a visitor signs in, with your own id for them
window.cake.identify(user.id)
// when they sign out
window.cake.reset()
```

Code that may run before `cake.js` has loaded can queue the calls: `window.cake = window.cake || [];
window.cake.push(['identify', user.id])` (or `'reset'`). Calling `identify()` is your site's choice; nothing calls it
for you.

- **What is sent**: the visitor's browser makes the SHA-256 hash of your site key, a colon and the id (with the
  browser's SubtleCrypto, so only on https pages and on localhost; elsewhere `identify()` does nothing) and sends only
  the hash. The id never leaves the browser, and AgentCake keeps only the hash, with each session that carried it.
  AgentCake accepts nothing else in its place: a value that is not a SHA-256 hash in hexadecimal is dropped.
- **What it is used for**: only to count visitors. A session counts as the visitor whose hash it carried, or whose hash
  its browser's visitor id was first sent with, sessions from before the sign-in included, so a visitor who signs in on
  two browsers counts once. `window.cake.reset()` deletes the hash from the browser and starts a new visitor id and a
  new session, so the next person who signs in on a shared computer counts as another visitor. The dashboard shows no
  hash and no id, and AgentCake keeps no profile of a visitor.
- **What it is not**: anonymous. A hash can't be turned back into the id, but your site key is in your pages, so
  anyone who knows an id, or can guess it, can make the same hash and compare. Your site, which knows its visitors'
  ids, can find a signed-in visitor's sessions that way, and so could anyone who got a copy of AgentCake's data folder,
  for ids that are easy to guess. Pass an internal id that is hard to guess: not an e-mail address, not a name, not a
  number that counts up. Mention it in your privacy notice ([`docs/privacy-notice-template.md`](docs/privacy-notice-template.md)).
- **Deleting**: `agentcake delete` deletes a visit's hash with the rest of the visit (below).

## Where it is stored, and for how long

On the computer or server AgentCake runs on, in its data folder: `~/.cake`, or `$CAKE_HOME` (`/var/lib/cake` on a
server set up as [`SERVER.md`](SERVER.md) says).

| File | What it holds |
|---|---|
| `cake.db` (with `cake.db-wal`, `cake.db-shm`) | visits, uploads' headers, classifications, the server middleware's tokens, the index of the replay chunks |
| `replays/` | replays, raw input and browser signals as compressed chunks |
| `backups/` | the copy of `cake.db` that `agentcake migrate` makes before it changes anything (only after a migration) |
| `srv_secret` | the secret shared with your site's server (only after `agentcake secret init`), readable by its owner only |
| `cake.log`, `cake.pid` | only when started with `agentcake start`; a service logs to the system's journal instead |
| `config.json`, `lists/` | settings; lists downloaded by `agentcake lists update` |

Everything is kept until you delete it. You can choose to delete visits older than 30 or 90 days (`retention_days`).
When less than 10% of the disk budget (`budget_mb`) is left and `auto_free` is on (the default), AgentCake deletes
visits' replays, oldest first, across all kinds of visit, until it is back under 90% of the budget; a replay still
being recorded waits until the visit is quiet. When the disk itself has less than `disk_min_free_mb` free (10 GB by
default), AgentCake deletes nothing and records new visits without their replays until there is room.
Classifications and timelines always stay (SERVER.md, "Disk budget").

## Deleting

One visit, everywhere in the data folder:

```sh
agentcake delete --session <id>          # the id the dashboard shows for the visit
agentcake delete --visitor <visit id>    # the same visit, by the id the visitor's browser keeps (cake_sid), with
                                         # every session AgentCake cut from it after 30 minutes or 24 hours
agentcake delete --session <id> --dry-run   # first see what would go
```

A visit is one session: both names reach the same rows. Give either several times to delete several visits. It works
while AgentCake runs, with no need to stop it: the command asks the running AgentCake, on `127.0.0.1` only, to do
the deleting. On a server, run it as the service does (`SERVER.md`): with systemd through the alias it gives, with
Docker as `docker exec agentcake python3 -I -m agentcake delete --session <id>`.

What goes:

- every row of the visit in every table of `cake.db`, and the database file is rewritten so that no copy of a deleted
  row is left in its free space or its write-ahead log;
- its replay, raw input and signal chunks: their bytes are overwritten with zeros at once, and the space comes back
  the way it does for any removed replay (a chunk file with nothing left in it is deleted, a mostly empty one rewritten);
- its rows in the backups `agentcake migrate` made in `backups/`;
- the lines of `cake.log` that name it.

What it cannot reach: copies outside the data folder. Delete the visit from your own backups and snapshots too, or let
them expire. The system's journal and `docker logs` keep what AgentCake printed; it prints no visit data, only, rarely,
a session id in an error message. A visit still going on when you delete it (the visitor still in the same tab) is
recorded again from its next upload: delete once the visitor has left, or after your site called `window.cake.stop()`.

Everything at once: stop AgentCake (`agentcake stop`, or stop the service) and delete its data folder.

## Checking

In a checkout of AgentCake's repository, `python3 -I tools/privacy_scan.py <data folder> --canary <text>` reads
every table, every replay chunk (decompressed), every log and every JSON file in the folder, and reports how many IP
addresses, card numbers, e-mail addresses, cookies, authorization headers, key names, private keys, copies of
`srv_secret` and copies of the text you typed into a test visit it found, and where. It prints only counts and places,
never what it found.

## For site owners

You decide whether and when your visitors are recorded, and you tell them. The template in
[`docs/privacy-notice-template.md`](docs/privacy-notice-template.md) is a starting point for the part of your privacy
notice about AgentCake. It is not legal advice: what you must tell your visitors, and whether you need their consent
first, depends on where you and they are.
