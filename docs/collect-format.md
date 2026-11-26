# cake.js upload format, version 1

What AgentCake's page script (`cake.js`) sends to AgentCake's `/collect`: the request, the batch, and every record in
it. The collector is built from this document. The script that produces it is built by
`tools/build_js.py` from `agentcake/static/src/`; every number named here is a key of `agentcake/data/cakejs.json`
(`script` object), shown as `CFG.<key>` with its default.

Version 1 keeps the meaning of every field cake 0.3.4's script sent (`k`, `s`, `u`, `ua`, `wd`, `e`, `st`), so a 0.3.4
collector still stores the replay of a version 1 batch, as long as it reads the body (see "Request").

## Request

| | |
|---|---|
| Method and URL | `POST <cake>/collect`, where `<cake>` is the folder cake.js was loaded from: `new URL('collect', script.src)`. `https://cake.example.com/cake.js` → `https://cake.example.com/collect`; `https://example.com/cake/cake.js` → `https://example.com/cake/collect`. |
| Body | One batch (below) as UTF-8 JSON. When the URL has `?z=gzip`, the body is that JSON gzip-compressed. |
| `Content-Type` | `text/plain`, so a cross-origin upload is a CORS simple request (no preflight). |
| Credentials | `credentials: 'omit'`: the browser sends no cookie, even when AgentCake is on the site's own origin. |
| Keepalive | A body that fits the keepalive budget (`CFG.batch.keepalive_max_bytes`, 60,000 bytes; the Fetch spec allows 64 KiB of keepalive bodies in flight per page) is sent with `keepalive: true` and survives the page being left. |
| Compression | Batches of at least `CFG.batch.compress_min_bytes` (2,048) JSON characters are gzipped when the browser has `CompressionStream`, except at exit (see "When records are made and batches are sent"). |
| Answer | Any 2xx means accepted: AgentCake answers 204, also to a batch it has already (see "Delivery"). 408, 429 and 5xx (`CFG.batch.retry_statuses`) mean "try later": cake.js keeps the batch and sends it again. Any other answer is final: the batch is dropped. cake's final answers: 400 for a body it cannot read (or a version 1 batch without `pv` and `seq`, or an unknown `v`), 403 for another site's key, 413 for a body that is or unzips too large, or holds more records than cake's per-upload limit (`max_events_per_post`). |
| CORS | When AgentCake is not on the page's origin, the answer needs `Access-Control-Allow-Origin` for cake.js to read its status: the public listener answers with the request's own Origin (when it is a well-formed origin) and `Vary: Origin`, the local listener with `*`. Without it the upload still arrives, but cake.js counts it as failed and sends it again (the copy is dropped by the collector, see "Delivery"). |

The collector must accept both a plain and a gzip body, limit the body as sent (AgentCake's per-POST limit,
`defaults.json`) and the decompressed size (at least `CFG.batch.max_record_bytes` plus a few kilobytes, since one record
can be that big). AgentCake's collector (`agentcake/collect.py`) lets a gzip body unzip to
`local_max_body_bytes` (10,000,000), counts every upload it refuses by reason, and also takes a batch of cake 0.3.4's
script (no `v`, `pv` or `seq`; kept without the check below).

## Batch

A JSON object: a header and three record arrays.

| Field | Type | Unit | Meaning and source |
|---|---|---|---|
| `v` | integer | | Format version: `1` (`CFG.format_version`). |
| `k` | string | | Site key: the script tag's `data-site`, else the key AgentCake filled in when it served cake.js. |
| `s` | string, 32 hex digits | | Tab session id: the tab's part of the browser session `bs`, which AgentCake judges, replays and stores. Random, kept in the tab's `sessionStorage` (`cake_sid`, with its clock in `cake_clock`) until the tab is closed or `window.cake.stop()` is called. The tab's first activity after `CFG.session.idle_ms` (30 minutes) without activity in the tab, or once its session has lasted `CFG.session.max_ms` (24 hours), begins a new one ("Sessions", below); so does every change of `bs`, and a tab that is a copy of another (see `w`) begins its own. |
| `bs` | string, 32 hex digits, optional | | Browser session id: random, kept in `localStorage` (`cake_bsid`, the id alone, with its clock in `cake_bclock`), so every tab of the site in the browser has the same one, as posthog-js shares its session id. It ends once no tab has seen activity for `CFG.session.idle_ms` (30 minutes), or once it has lasted `CFG.session.max_ms` (24 hours): the next activity in any tab begins the next one, and the other tabs take it at their next activity (with the visitor id and identify hash that tab keeps). `window.cake.reset()` begins the next one at once. One that is gone from `localStorage` (`window.cake.stop()` or `reset()` in another tab, or storage cleared) is never written back: the tab's next activity begins the next one, as posthog-js begins a new session when the id it stored is gone. Where `localStorage` takes no writes but `sessionStorage` does, the tab's own, kept there under the same names: one per tab; only this page view's own where neither can be used. Missing from cake.js before 0.6.2. |
| `w` | string, 32 hex digits, optional | | Tab id (posthog-js's window id): random, kept in the tab's `sessionStorage` (`cake_wid`). It lasts as long as the tab and the browser session: a tab that begins the next `bs` gets a new one, a tab that takes another tab's `bs` keeps its own. A tab that is a copy of another (a duplicated tab, or one opened by `window.open` with an opener: both copy `sessionStorage`) gets a new one, and a new `s`: a page marks the tab as its own while it runs (`cake_wopen`, removed at `pagehide`), and a page that finds another page's mark holds a copy. Missing from cake.js before 0.6.2. |
| `vid` | string, 32 hex digits | | Visitor id: random, kept in `localStorage` (`cake_vid`, with when it was last used) and replaced once it was not used for `CFG.visitor.max_age_ms` (365 days); only this page's own where `localStorage` cannot be used. Removed by `window.cake.stop()`; replaced by a new one by `window.cake.reset()`. |
| `idh` | string, 64 hex digits, optional | | Identify hash, only after the site called `window.cake.identify(id)`: the SHA-256 of the site key, `:` and the id (`CFG.identify`), in lowercase hexadecimal, made in the browser with SubtleCrypto; the id itself is never sent. Kept with the visitor id in `cake_vid` and sent with every batch from then on, on every later page view in this browser. Removed by `window.cake.reset()` and `window.cake.stop()`. AgentCake keeps it only when it is 64 lowercase hex digits. |
| `pv` | string, 32 hex digits | | Page view id: random, new for every page load. |
| `seq` | integer ≥ 0 | | Number of this batch within its page view: 0, 1, 2, … A batch sent again keeps its number. |
| `t` | number | epoch ms, 0.1 ms | When the batch was made. |
| `u` | string | | `location.origin + pathname + search` when the batch was made (single-page apps change it without a new page view). |
| `ua` | string | | `navigator.userAgent`. |
| `wd` | boolean | | `navigator.webdriver === true`. |
| `why` | string | | What made the batch: `start`, `snapshot`, `env`, `probes`, `timer`, `size`, `exit`. |
| `st` | string, optional | | The server middleware token (below), on every batch of the page until AgentCake has answered 2xx to one batch carrying it. |
| `dr` | object, optional | counts | Present once cake.js has had to drop something on this page view, cumulative: `e`, `r`, `x` records per stream (over the per-page limit or bigger than `CFG.batch.max_record_bytes`) and `b` batches it could neither send nor keep. |
| `e` | array | | rrweb events. |
| `r` | array | | Raw input records. |
| `x` | array | | Signal records. |

### `e`: rrweb events

As emitted by rrweb 2.0.0-alpha.18's `record` (`{type, data, timestamp}`, `timestamp` in epoch ms), with the privacy
rules of `agentcake/data/privacy.json` (`CFG.privacy`, not settings): `maskAllInputs: true` (an input's value becomes
`*` of the same length), `maskTextSelector` for editable elements (`[contenteditable]`: typed text masked the same way)
and `blockSelector` for private elements (`[data-cake-private], input[type=password], [autocomplete^="cc-"]`, and
cake.js's own probe frame): such an element is an empty placeholder of its size, with no content, no attributes'
values and no interaction. Sampling: `CFG.rrweb.sampling` (mouse moves at most every 50 ms, scroll every 150 ms, an
input's last value only, masked). Every page view starts with a Meta event (`type` 4) and a FullSnapshot (`type` 2);
both are sent as soon as rrweb has emitted them.

### `r`: raw input records

One record per DOM event, in the field names of the research lab's `raw.js`, so the lab's behaviour features read
AgentCake's data unchanged. An event whose target is inside a private element (`CFG.privacy.private_selector`) is not sent at
all when it is a keyboard, input or change event (`private_dropped_events`), and is sent without `s` and `r` otherwise
(`private_dropped_fields`): nothing typed into a private element, not even its timing, leaves the page. Every record has
`t` (epoch ms, 0.1 ms; the event's `timeStamp` plus `performance.timeOrigin`) and `ty` (the event type, or one of the
record types at the end of the table). Events are listened to on `window` in the capture phase: `CFG.raw.events` plus
`scroll`.

| Field | When | Meaning |
|---|---|---|
| `tr` | every event | `isTrusted`: 1 or 0. |
| `hf`, `vs` | every event, and `visibility`, `geo` | `document.hasFocus()` and `visibilityState === 'visible'`: 1 or 0. |
| `cx`, `cy`, `sx`, `sy` | mouse, pointer, wheel events | `clientX/Y`, `screenX/Y` (CSS px). |
| `mx`, `my`, `b`, `d` | same | `movementX/Y`, `buttons`, `detail`. |
| `pt`, `pr`, `w`, `h` | pointer events | `pointerType`, `pressure`, contact `width` and `height`. |
| `pid`, `tlx`, `tly` | pointer events | `pointerId`, `tiltX`, `tiltY`. |
| `co` | `pointermove` | Number of coalesced samples (`getCoalescedEvents().length`). |
| `dx`, `dy`, `dm` | `wheel` | `deltaX`, `deltaY`, `deltaMode`. |
| `x`, `y` | `scroll` | `scrollX`, `scrollY` of the window, whole px. |
| `kc`, `ce`, `rp` | `keydown`, `keyup` | Key class from `CFG.privacy.key_classes` (`letter`, `digit`, `space`, `symbol`, `delete`, `enter`, `tab`, `modifier`, `arrow`, `unidentified`, `other`); 1 when `event.code` is empty; 1 on auto-repeat. Never the key. |
| `it`, `ic`, `len` | `input` | `inputType`; `isComposing` 1 or 0; the field's length after the input (an input's value, or an editable element's text), null when it has none. Never the text. |
| `s`, `r` | `CFG.raw.target_events` | Target: `#id`, else `#<nearest ancestor id> <tag>`, else the tag; `[left, top, width, height]` (CSS px, 0.1) of the nearest `CFG.raw.target_selector` element or the target. |
| `ty: "dom_add"` | an element added directly under `<html>` or `<body>`, or attribute-less there at `CFG.raw.dom_scan_delay_ms` (cake.js's own probe frame, marked `CFG.env.probe_attr`, is never reported) | `how` (`added` or `scan`), `tag`, `nattr`, `attrs` (attribute names only, at most `CFG.raw.dom_attr_names_max`), `open_shadow` (1 or 0), `disp` (computed `display`), `parent` (`body`, `html`, `other`). |
| `ty: "geo"` | window geometry changed (checked on load, on resize and every `CFG.raw.geo_poll_ms`) | `why` (`load`, `resize`, `poll`), `g`: `[innerWidth, innerHeight, outerWidth, outerHeight, screenX, screenY, devicePixelRatio, screen.width, screen.height]`. |
| `ty: "visibility"`, `"winfocus"`, `"winblur"` | `visibilitychange`; the window gained or lost focus | |

### `x`: signal records

Every record has `t` and `ty`.

| `ty` | When | Fields |
|---|---|---|
| `page` | once per page view, first | `n` page number in this tab's session; `build` the script's build id; `nav` navigation type (`navigate`, `reload`, `back_forward`, `prerender`); `t0` `performance.timeOrigin` (epoch ms); `ran` ms from navigation start to cake.js starting; `prerendering`; `vis`; `hf`; `hist` `history.length`; `hook_dom`; `consent`: `load` (recording began when cake.js loaded) or `start` (the page asked first and called `window.cake.start()`); `p` `location.pathname`; and the source fields: `rd` the referring domain (the host of `document.referrer`, `""` without one; never the address), `utm` the page address's campaign parameters that are there (`CFG.source.campaign`: the five UTM parameters and `gad_source`, each cut to `CFG.source.max_chars`), `ck` the names of the ad-click parameters the address carries (`CFG.source.click_ids`; never their values), `lang` `navigator.language`, `tzo` `Date.getTimezoneOffset()`. (Before 0.4.2 it sent `ref`, the whole `document.referrer`.) |
| `path` | `location.pathname` changed since the last page view (a single-page app's navigation, seen with the next record) | `p`: the new path. A page view, as PostHog counts one; a new query string or fragment alone makes none. |
| `session` | a new session began on this page (see "Sessions"), its first record | `why`: `idle` (`CFG.session.idle_ms` without activity), `max` (the session lasted `CFG.session.max_ms`), `reset` (the site called `window.cake.reset()` on this page) or `tab` (another tab began the browser's next session while this tab's had not ended: its `reset()`, or two tabs that began one at the same moment; or the session was gone from `localStorage`: another tab's `stop()` or `reset()` removed it); the source fields of the page as it is now (`rd`, `utm`, `ck`, `lang`, `tzo`, as in `page`). |
| `env` | once per page view, after the load event, made in three idle tasks | `env`: webdriver and its property descriptor, navigator's own properties, user agent and `userAgentData` (brands, platform, mobile), languages, platform, cores, memory, plugin and MIME type counts, PDF viewer, `doNotTrack`, touch points, screen, window and viewport sizes, pixel ratio, time zone and offset, WebGL vendor and renderer, notification permission, `window.chrome` (type, runtime, keys), focus, visibility, history length, the referring domain (`referringDomain`; before 0.4.2 `referrer`, the whole address), `any-pointer`, `any-hover`, colour scheme, connection RTT, `window.external`, `eval` source length, `typeof process`. |
| `auto` | with `env` | `globalsAtLoad` (automation globals: BotD's distinctive properties found as `botdprop_<kind>`, `selenium_cdc`, `playwright_globals`, `puppeteer_globals`, `exposed_installed` (functions marked by Playwright's `exposeFunction`), `unnamed_native_globals` (nameless native functions, as CDP bindings leave them)), `errorStack` (a stack trace made in cake.js), `docInterception` (the navigation entry's `nextHopProtocol`, `transferSize`, `deliveryType`, `workerStart`, and `intercepted`: no network hop, no service worker, yet bytes transferred). |
| `frames` | once per tab session, when the browser is idle, on the first page view that gets that far (`cake_frames` in `sessionStorage` remembers it) | `iframeSharesRealm` (a fresh hidden frame's `Navigator` is this window's); `ipcFlooding`: of `CFG.env.frame_history_writes` (300) history writes in that frame, how many went through (`applied`), the error that stopped them (`error`) and whether all 300 did (`all300`: Chrome's IPC flooding protection is off, as Puppeteer and Playwright launch it); the writes go in bursts of `CFG.env.frame_burst_writes` every `frame_burst_gap_ms`, `longest_burst_ms` is the longest burst. |
| `cdp` | after the CDP probe (up to `CFG.env.cdp_rounds` rounds, `CFG.env.cdp_round_ms` apart, stopping at the first sign; each round logs in a hidden frame of its own, made and removed within the round) | `runtimeEnableLeak`: `rounds`; per logged error, how often `Error.prepareStackTrace` ran for it (`prepareStackTraceCount`), its `name` was read (`nameGetterCount`) and its `stack` was read (`stackLookupCount`); `firstHitRound` (null when never); `console`: `frame` (the rounds logged in their own frames, which no page script reaches) or `none` (no frame could be used, as on a page with a sandbox policy; no round ran, and `error` names why). Records without `console` come from cake.js before 2026-11-16, which logged through the page's own console. Chromium 1228 driven by Playwright: 1 formatting and 2 name reads per round. |
| `probes` | when every asynchronous probe has answered (each within `CFG.probes.timeout_ms`), or at exit with what has | `permissions` (notification permission vs Permissions API), `workerConsistency` (navigator facts in a worker that differ), `nativeTampering` (getters and methods that are not native any more), `uaFullVersion` (high-entropy client hints), `mediaDevices` (device count per kind, no labels), `fonts` (installed or not, for `CFG.probes.fonts`), `systemFontNames` (`disagree`, `agree` or `unknown`: whether the browser maps a system font name only Apple's systems map while its user agent and platform name another system; only this answer is sent), `pending` (probes that had not answered). A probe that failed has `{error}`. |
| `botd` | when BotD has run | `result` (`{bot, botKind}`), `detections` (per detector), or `error`. |
| `botscent` | when botscent starts, when its verdict changes, after `CFG.botscent.sample_ms` and at exit | `why` (`start`, `change`, `later`, `exit`), `type` (`human` or `agent`), `agent` (name or null), `reasons`, `probes` (per-probe status), `transport`, `ver`. |
| `globals` | at exit | `globalsAtEnd` (the same scan again: frameworks add theirs late); when the site owner turned on `hook_dom`: `hookHits` (page DOM lookups with an automation framework's frames on the call stack: `fn`, `arg`, `t`, `pptr`, `utilityScript`, `puppeteerEval`, `stack`) and `lookups` (`total` lookups, `checked` of them). |
| `tasks` | when the detectors have finished (after the frame checks on the tab session's first page) | `took_ms`: ms per task (`start` = cake.js's own first task, `rrweb` = the first snapshot, then the idle tasks after load: `parked`, `markers`, `env`, `webgl`, `tz`, `auto`, `cdp`, `botscent`, `probes`, `botd`, `frames`); `longest_ms`; `after_load_ms`: how long after the load event this record was made. |
| `markers` | when the watch on agent marks starts (an idle task after load), and at exit (see "Agent marks") | At the start: `why: "start"`, `list` (the mark table's version, `CFG.markers.version`), `every_ms` (how often it looks, `CFG.markers.every_ms`, 250). At exit: `why: "exit"`, `looks` (looks so far), `ms` (the time all of the watch's work took so far: its looks and its checks of DOM changes), `longest_ms` (its longest piece of work). |
| `marker` | an agent product's mark appeared or went away, as seen at a look | `m`: the mark's id in the mark table (for example `claude-chrome.working`); `on`: 1 it appeared (or lit up), 0 it went away. Nothing of the page. |
| `leave` | at exit | `why`: `pagehide` or `hidden`. |
| `pageshow` | the page came back from the back-forward cache | `persisted: true`. |
| `err` | one of cake.js's own parts failed, or `window.cake.identify()` did nothing (`where`: `identify`, with why: not an id, or no SubtleCrypto; never the value) | `where`, `msg` (the message only, at most `CFG.limits.error_chars`). |

### Agent marks

Some agent products draw on the page while they work: Claude in Chrome a "working" tag and a Stop button. When such a
mark appears and goes away tells AgentCake when the agent's
turn began and ended, so where a person may have taken over (threshold A5). cake.js watches the marks
of the mark table, `agentcake/data/agent_markers.json` (its `page` part is `CFG.markers`; the rest says what each mark
is, where it comes from, its grade and date, and the words of a reason). Products redraw their marks with new versions,
so the table is a data file of its own, updated without code changes. A mark is found:

- by element ids and a CSS selector, when it is an element of the page's own DOM: it is there or not;
- by hit-testing spots, when it is drawn inside an extension's closed shadow root, which no selector reaches:
  `document.elementFromPoint` at a spot (`x` a fraction of the viewport's width, `top` or `bottom` CSS px from that
  edge, scroll bars left out) returns the root's host while the mark covers the spot. The host must have the shape
  `CFG.markers.host`: an attribute-less, empty `<div>` with `display: contents` under `<body>` or `<html>`, which
  draws no box of its own, so a hit on it is a hit on what its shadow root draws.

cake.js looks every `CFG.markers.every_ms` (250 ms) while the page is visible and sends a `marker` record when a mark
appears or goes away: which mark and when (the look's time, so at most one interval late), nothing of the page. It only
reads the page. A hidden page shows no mark (Claude in Chrome draws nothing there), so while the page is hidden its marks
are not known and no record is made; it looks again the moment the page is shown. A mark already there when the watch
starts is noted at its first look: the `markers` start record says from when the page view was watched, and a page view
without it was not watched (left before its load event, or an older cake.js), which AgentCake reads as not known. While
a mark of a kind that bounds the agent's turn (the table's `turn_kinds`) was there, the behaviour timeline gives every
action to the agent, and Claude in Chrome's lit "working" indicator is a product rule of the environment layer
(`env.product.claude-chrome-indicator`).

What it costs, kept small on any page: ids are looked up at each look; the selectors are matched against the whole
page once, when the watch starts, and then only against what changes (a MutationObserver hands over added elements and
elements whose attributes in `CFG.markers.attributes` changed), so a page that keeps changing costs in proportion to the
change; the whole page is searched again only at a look after something was removed while a selector's mark was there.
Spots are hit-tested only while `<body>` or `<html>` has a child of the host's shape, which a page without such an
extension never has. Measured in Chromium by `tests/browser/test_markers.py` on a heavily loaded machine (load average
around 40–60, so on the high side): about 0.15 ms per look, under 1 ms of work per second, on a shop's pages, on a page of
20,000 elements and on that page changing every 100 ms; on the 20,000-element page with Claude in Chrome's tag shown,
when its four spots are hit-tested at every look, about 7 ms per look (about 30 ms per second). The exit `markers`
record carries what the watch cost on each page view.

### The research lab's field names

cake.js keeps the field names of the research lab's scripts, so what was built on lab data (the environment rules and
the behaviour features) reads AgentCake's data without renaming. Where the lab sent one report,
AgentCake sends separate records; joining them per page view gives the lab's layout back:

| Lab (`env.js` / `raw.js` / `bs.js`) | cake.js version 1 |
|---|---|
| `snap.env` | `env` record, `env` |
| `snap.auto.globalsAtLoad`, `globalsAtEnd` | `auto` record `globalsAtLoad`; `globals` record `globalsAtEnd` |
| `snap.auto.errorStack`, `docInterception` | `auto` record |
| `snap.auto.runtimeEnableLeak` | `cdp` record `runtimeEnableLeak` |
| `snap.auto.ipcFlooding` | `frames` record `ipcFlooding` (once per tab session: it holds for its every page) |
| `snap.auto.nativeTampering.iframeSharesRealm` | `frames` record `iframeSharesRealm` |
| `snap.auto.nativeTampering.tampered`, `permissions`, `workerConsistency`, `uaFullVersion` | `probes` record |
| `snap.auto.hookHits` | `globals` record `hookHits` (only lookups with an automation frame; `t` is epoch ms, the lab's `t_ms` was relative) |
| `snap.botd` (`result`, `detections`) | `botd` record |
| `raw` items (`click`, `keydown`, …, `dom_add`, `geo`, `visibility`, `winfocus`, `winblur`) | `r`, unchanged |
| `lab_botscent` items (`why`, `type`, `agent`, `reasons`, `probes`, `ver`) | `botscent` records in `x` |
| `rrweb` items | `e`, unchanged |
| `snap.inter`, `click` and `summary` reports | not sent: `r` has every event they were made from |
| `snap.auto.csp` | not sent (it needed a request to another origin of the site) |

## Server middleware token

The response that opened the page may carry `Server-Timing: cake;desc="<token>"` (set by the AgentCake middleware on
the site's server; format `c1.<base64url JSON>.<HMAC>`).
cake.js reads it from the navigation entry (`performance.getEntriesByType('navigation')[0].serverTiming`, entry name
`CFG.token.entry`) and sends it as `st` with every batch of that page until AgentCake answers 2xx to a batch carrying
it. cake.js never looks inside it. The collector verifies it and keeps it once per token id (0.3.3 `take_token`).
A page the browser shows from its cache carries the token stored with it (after a 304, the 304's own new one; going back
to a stored page, that page's earlier one), so the same token can come from several page views of a tab session: the
first keeps it, another page view of the same tab session is a reuse (no second server middleware record), another tab
session's is a replay. The answer says what happened, as `X-Cake-Token: ok | dup | reuse | replay | stale | bad | off`;
it is always a 2xx, since a token's fate is no error for the visitor.

## When records are made and batches are sent

cake.js keeps the page's own loading first. Its first task only reads its settings, hooks its listeners and makes the
`page` record; rrweb's first snapshot is the next task; everything else waits for the page's load event and runs as one
task per idle period of the browser (`requestIdleCallback`, else a timer of `CFG.idle_gap_ms`), each well under 50 ms:
re-sending parked batches, the start of the watch on agent marks (which then looks every 250 ms), the environment
snapshot (three tasks), `auto`, the CDP probe, botscent, the probes, BotD, and on the tab session's first page the frame
checks (in bursts). The `tasks` record says how long each took and when they
had all run. A page left before its load event, or before its idle tasks ran, has no `env`, `auto`, `cdp`, `probes`,
`botd` or `tasks` record: AgentCake reads those as not observed.

Batches go:

- right after rrweb's full snapshot (`snapshot`) and right after start (`start`), so a page left within a second still
  has its page record and snapshot in AgentCake; after the `auto` record (`env`) and after the `tasks` record
  (`probes`);
- every interval (`timer`): `CFG.batch.interval_min_ms` (2 s), doubled (`interval_growth`) after each interval with
  nothing to send, up to `interval_max_ms` (10 s), back to 2 s once there is data;
- as soon as the buffer holds `CFG.batch.max_bytes` (51,200 JSON characters) (`size`);
- when the page is hidden or left (`exit`): plain JSON with keepalive while the budget lasts. Batches that do not fit,
  and any batch too big for keepalive at other times, are first parked in `sessionStorage` (`cake_pending`, at most
  `CFG.batch.pending_max_bytes`) and taken out once AgentCake has answered; the tab's next page sends what is still
  parked.

## Delivery

- **A batch can arrive more than once** (a parked copy sent again, an answer cake.js could not read). The collector
  keeps one copy per **`(s, pv, seq)`**. The page view id is part of the key because two tabs can still send the same
  tab session id `s`, each with its own numbering: a tab copied from one whose page had just been left (a copy of a
  live page takes a new `s`, see `w`), or tabs under a cake.js before 0.6.2. AgentCake keeps each record with its page
  view, and each stream of a tab session up to its limit (`max_events_per_session`); later records are counted, not
  kept.
- Batches can arrive out of order; records carry their own times (`t`, rrweb's `timestamp`).
- A page view's numbers have no gaps unless batches were lost (`dr.b` counts batches cake.js could not keep).

## Limits

| Limit | Default | What happens over it |
|---|---|---|
| Records per page view, per stream (`CFG.limits.records_per_page`) | `e` 100,000, `r` 200,000, `x` 5,000 | Not sent; counted in `dr`. |
| One record (`CFG.batch.max_record_bytes`) | 4,194,304 JSON characters | Not sent; counted in `dr`. |
| One batch (`CFG.batch.max_bytes`) | 51,200 JSON characters | A new batch starts; one bigger record goes alone. |
| Keepalive body (`CFG.batch.keepalive_max_bytes`) | 60,000 bytes | Sent without keepalive, after parking a copy. |
| Parked batches (`CFG.batch.pending_max_bytes`) | 1,048,576 JSON characters | The batch is not parked (`dr.b` when it is then lost). |

## Sessions

A session is one visit of a browser to the site: every tab of the site in that browser, until no tab has had activity
for `CFG.session.idle_ms` (30 minutes) or the session has lasted `CFG.session.max_ms` (24 hours): PostHog's rules
(posthog-js `sessionid.ts`). Activity is a raw input record of `CFG.session.activity_raw` (a pointer move, a press, a
click, a scroll, a focus, an input, a touch), a `geo` record made by a resize, and a page view (`page`, `path`). Every
tab sends the session's id, `bs`, which they share, and its own id, `w`, the same for the tab while the session lasts:
a tab that begins a new session itself gets a new `w`, and a tab the browser duplicated gets one of its own. Where the
browser takes no writes into `localStorage` but does into `sessionStorage`, each tab is a session of its own; where it
lets the script keep nothing across pages, each page is, as posthog-js's in-memory one is.

Each tab's part of a session is a tab session, `s`: the unit AgentCake judges, replays and stores. A tab's session
follows the same rules on the tab's own activity, and a new `bs` begins a new one too. The first activity after the
idle time, after 24 hours or under a new `bs` begins a new tab session on the page: what is buffered is sent under the
old ids, the new ids are kept, a `session` record says why, and rrweb takes a full snapshot. While the tab is idle,
rrweb events are dropped (PostHog's recorder drops them too); other records are sent under the session they belong to.
`window.cake.reset()` also begins a new session at once in its tab, which the other tabs take at their next activity, as
posthog-js's `reset()` does: what is buffered is sent under the old session and visitor ids, then the new visitor id
(without `idh`) and the new session ids go with every later batch, and the new tab session's `session` record says why.

The collector keeps each tab session in the session its `bs` names: the first `bs` its batches carried. Batches
without `bs` come from an older cake.js still open in a tab, from a script of your own, and from every visit recorded
before 0.6.2; for them the collector applies the same rules, from the same settings. It cuts a tab's session when its
script does not cut its own: a batch whose first activity comes after the idle time, or past 24 hours, goes to the
tab's next session, whose id the collector makes (`session_split.py`). It joins the tab sessions of one visitor id
(`vid`) into sessions (`visit_join.py`): in the order their activity began, a tab session joins the session before it
when it began at most 30 minutes after the latest activity of every tab session before it, and at most 24 hours after
that session began. A tab session joins whole, by when it began, and one without `vid` is a session of its own. A
batch that comes late gives the sessions that the same batches give in order.

## Consent

A site that asks before recording either adds the cake.js line only after the visitor agreed, or adds it with
`data-consent="required"` (`CFG.attr.consent`) and calls `window.cake.start()` once they agree: until then cake.js does
nothing (no listener, no `sessionStorage`, no request). `window.cake.stop()` ends recording and sending on that page for
good: nothing more is sent, unsent records and parked batches are dropped, and the tab's session id and its clock, the
tab id and its mark, the page count and the frame-check mark (and the tab's own copy of the browser session id and its
clock, where `localStorage` took no writes) are removed from `sessionStorage`, and the browser session id and its clock
and the visitor id from `localStorage`; no other tab writes them back. An upload already on its way may still arrive; if
it fails, it is dropped, not parked, so a later `start()` sends nothing from before the refusal. Consent code that may
run before cake.js has loaded can queue the calls: `window.cake = window.cake || []; window.cake.push('start')` (or
`'stop'`). Nothing is sent to say a visitor refused (that would be a request after the refusal), so the collector keeps
what came before; deleting it is the site owner's call (`agentcake delete`).

## What a batch never holds

Which key was pressed (only its class), what was typed (only the input type and the field's length; rrweb masks every
input and editable text), anything typed into or shown in a private element, the address of the page the visitor came
from (only its domain), the values of ad-click parameters outside the page's own address (only their names), cookies
(cake.js reads and sets none, and uploads omit credentials) and the visitor's IP address (the collector sees it on the request, works out its network facts and never
keeps the address itself). `tests/test_privacy_recording.py` checks this in Chromium with a canary string and a card number typed into every
kind of field. `PRIVACY.md` says the same for site owners.

## Versions

`v` changes only when a field changes meaning or goes away. New optional fields and record types keep `v: 1`; a
collector ignores fields it does not know.

## Example (shortened)

```json
{"v":1,"k":"9f3c…","s":"5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5","bs":"e41d…","w":"07b2…","vid":"aa11…","pv":"c2a8…",
 "seq":0,"t":1794518371369.5,
 "u":"https://shop.example.com/demo","why":"snapshot","st":"c1.eyJ…","ua":"Mozilla/5.0 …","wd":false,
 "e":[{"type":4,"data":{"href":"https://shop.example.com/demo","width":1280,"height":900},"timestamp":1794518371301},
      {"type":2,"data":{"node":{…},"initialOffset":{"left":0,"top":0}},"timestamp":1794518371304}],
 "r":[{"t":1794518371302.4,"ty":"geo","hf":1,"vs":1,"why":"load","g":[1280,900,1280,987,0,25,2,1512,982]}],
 "x":[{"t":1794518371300.1,"ty":"page","n":1,"build":"3f9a…","nav":"navigate","t0":1794518371012.3,
       "ran":288.1,"prerendering":false,"vis":"visible","hf":true,"hist":1,"hook_dom":false,"consent":"load",
       "p":"/demo","rd":"www.google.com","utm":{"utm_source":"newsletter"},"ck":[],"lang":"en-US","tzo":480}]}
```
