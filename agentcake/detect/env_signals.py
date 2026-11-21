"""Signals for the environment rules: what a session's recorded data says about its browser, as one dict.

    from_cake(batches, collect_requests=(), page_requests=None, settings=None) -> signals    cake.js, format v1
    from_lab(payloads, requests=(), settings=None) -> signals                                 the research lab

from_cake reads one visit's batches in cake.js's upload format version 1 (docs/collect-format.md): the `x` signal
records (env, auto, globals, cdp, frames, probes, botd, botscent, and the agent marks' marker and markers, read by
markers.page_marks), the `r` raw input records and the `e` rrweb events, which keep the lab's field names. cake.js
always watches the DOM, so a page view with raw records but no dom_add record had nothing added. `collect_requests`
are the collect endpoint's facts of the upload requests ({"headers": [[name, value], ...] or {name: value},
"ip_class": ...}); `page_requests` maps a page view id to the server half's facts of the request that opened that
page ({"headers": ...}).

from_lab reads the lab's reports in arrival order: env.js's load, probes, click and summary reports carry a `snap`
(env, auto, botd); raw.js's meta, raw and rrweb reports carry `items` (with dom_add and geo, bs.js's lab_botscent
verdicts and, in the recorder's raw.js, its `overlay` check of Claude in Chrome's indicator); `requests` are the lab
server's log rows (method, path, headers), whose POSTs are the uploads and whose GETs are the page requests.

Both give the same dict, which the rules read:

    {"pages": [{"path", "env", "auto", "botd", "dom_add", "botscent", "hidden_input", "nav": {"headers"},
                "markers": {"list", "from", "spans": [{"marker", "product", "kind", "from", "to"}, ...]}}, ...],
     "collect": {"requests": n, "headers": {name: {"present": k, "values": [...]}}, "ua_as_page", "ip_classes": [...]},
     "viewport_changes": [{"page", "dw", "dh", "doh", "w", "h"}, ...],
     "script_settings": {"hook_dom": true}}

ua_as_page: every upload carried a User-Agent the page reported (navigator.userAgent), false when a front door rewrote
them (CloudFront's defaults: "Amazon CloudFront", no Accept-Language); left out when no page reported one.

A key is left out when the session did not record it, so the rules read it as unknown, not as a miss ("markers" comes
from cake.js on a page view where its mark watch ran, and from the recorder's check of Claude in Chrome's indicator on
a page view where it saw the indicator: markers.py). Header names and event types come from the rule table's "signals"
section, and so do the page record fields that say how the site owner had set cake.js (script_settings: from cake.js
only, a setting true when it was on for any page view of the visit; the lab's own scripts had no settings).
"""
from __future__ import annotations

from collections import Counter, defaultdict, namedtuple

from agentcake import addresses
from agentcake.datafiles import load
from agentcake.detect import markers
from agentcake.detect.env_rules import load_rules

# The lab's report kinds that start a page view: env.js's first report and raw.js's first report of a page.
ENV_VIEW_START = "load"
RAW_VIEW_START = "meta"
RAW_EVENTS = "raw"
RRWEB_EVENTS = "rrweb"
BOTSCENT_ITEM = "lab_botscent"
DOM_ADD_ITEM = "dom_add"
GEO_ITEM = "geo"
GEO_LAYOUT = ("iw", "ih", "ow", "oh", "sx", "sy", "dpr", "sw", "sh")  # raw.js's geo item `g`, in this order
BOTD_PROP_PREFIX = "botdprop_"  # env.js names BotD's distinctive-property groups botdprop_<kind>
RRWEB_INCREMENTAL = 3  # protocol: rrweb EventType.IncrementalSnapshot
RRWEB_META = 4  # protocol: rrweb EventType.Meta (width and height of the viewport at a full snapshot)
RRWEB_VIEWPORT_RESIZE = 4  # protocol: rrweb IncrementalSource.ViewportResize
PAGE_METHOD = "GET"
COLLECT_METHOD = "POST"
USER_AGENT = load("data/edge.json")["headers"]["user_agent"]  # the upload header ua_as_page compares with the page's
DOM_FIELDS = ("tag", "nattr", "attrs", "open_shadow", "disp", "parent", "how")
HOOK_FLAGS = ("pptr", "utilityScript", "puppeteerEval")
# cake.js format v1: the signal records that hold what the lab sent in env.js's `snap.auto`, and the fields they hold
# (docs/collect-format.md, "The research lab's field names"). `frames` is sent once per visit and holds for all of it.
CAKE_AUTO_FIELDS = {"auto": ("globalsAtLoad", "errorStack", "docInterception"),
                    "globals": ("globalsAtEnd", "hookHits"),
                    "cdp": ("runtimeEnableLeak",),
                    "probes": ("permissions", "workerConsistency", "nativeTampering", "uaFullVersion", "systemFontNames")}
CAKE_VISIT_RECORD = "frames"
CAKE_BOTSCENT_RECORD = "botscent"
CAKE_PAGE_RECORD = "page"
CAKE_RECORD_KEYS = ("t", "ty")

_View = namedtuple("_View", "path first reports")  # one script's reports of one page view; first = arrival index
_Paired = namedtuple("_Paired", "first path env raw")
_Size = namedtuple("_Size", "key width height outer")  # a viewport size and when it was seen (page, source, time)
_Parts = namedtuple("_Parts", "path env autos botd items raw_ran dom_watch botscent nav window window_t rrweb marks")


def _globals(scans):
    """env.js's global-variable scans at load and at the end, as one union; BotD's property groups become a list of
    the group names found, so an empty scan reads as a known 'none found'."""
    found = defaultdict(list)
    for scan in scans:
        for name, names in (scan or {}).items():
            for item in names or []:
                if item not in found[name]:
                    found[name].append(item)
            found.setdefault(name, [])
    out = {name: items for name, items in found.items() if not name.startswith(BOTD_PROP_PREFIX)}
    out["botd_props"] = sorted(name[len(BOTD_PROP_PREFIX):] for name, items in found.items()
                               if name.startswith(BOTD_PROP_PREFIX) and items)
    return out


def _auto(autos):
    """The lab's `auto` layout from one or more reports of it, later reports winning."""
    if not autos:
        return None
    merged = {}
    for auto in autos:  # later reports add the asynchronous checks; keep the latest recorded value of each
        merged.update({key: value for key, value in auto.items() if value is not None})
    merged["globals"] = _globals([auto.get(key) for auto in autos for key in ("globalsAtLoad", "globalsAtEnd")])
    for key in ("globalsAtLoad", "globalsAtEnd"):
        merged.pop(key, None)
    leaks = [auto["runtimeEnableLeak"] for auto in autos if isinstance(auto.get("runtimeEnableLeak"), dict)]
    if leaks:  # the probe runs in rounds; the report with the most rounds has seen the most
        merged["runtimeEnableLeak"] = max(leaks, key=lambda leak: leak.get("rounds") or 0)
    if "hookHits" in merged:  # only when the page's DOM methods were wrapped; keep the flags, not the stacks
        hooks = []
        for auto in autos:
            for hit in auto.get("hookHits") or []:
                flags = {"fn": hit.get("fn"), **{flag: hit.get(flag) for flag in HOOK_FLAGS}}
                if flags not in hooks:
                    hooks.append(flags)
        merged["hookHits"] = hooks
    return merged


def _botscent(items):
    reasons = []
    for item in items:
        for reason in item.get("reasons") or []:
            if reason not in reasons:
                reasons.append(reason)
    last = items[-1]
    return {"reasons": reasons, "type": last.get("type"), "agent_name": last.get("agent"), "version": last.get("ver")}


def _hidden_input(items, watch):
    """botscent's hidden-document checks over raw input records: trusted input while the document was hidden, the
    pointer presses among it, and the part that arrived while the hidden document still reported focus."""
    hidden = [it for it in items if it.get("ty") in watch["events"] and it.get("tr") == 1 and it.get("vs") == 0]
    return {"trusted_hidden": len(hidden),
            "trusted_pointerdown": sum(1 for it in hidden if it.get("ty") == watch["pointer"]),
            "trusted_focused": sum(1 for it in hidden if it.get("hf") == 1)}


def _headers(headers, names):
    """Request headers ([name, value] pairs or a dict) as {lower-case name: value} for the names the rules read (never
    cookies or credentials); a header the request did not send is null, a known absence."""
    out = dict.fromkeys(names)
    pairs = headers.items() if isinstance(headers, dict) else headers or []
    for name, value in pairs:
        key = str(name).lower()
        if key in out and out[key] is None:
            out[key] = value
    return out


def _collect(requests, names, page_agents):
    """The upload requests' headers counted per name, ua_as_page (page_agents: what the page reported) and networks."""
    if not requests:
        return None
    headers = {name: {"present": 0, "values": []} for name in names}
    for request in requests:
        for name, value in _headers(request.get("headers"), names).items():
            if value is None:
                continue
            headers[name]["present"] += 1
            if value not in headers[name]["values"]:
                headers[name]["values"].append(value)
    out = {"requests": len(requests), "headers": headers}
    if page_agents:
        sent = headers.get(USER_AGENT) or {"present": 0, "values": []}
        out["ua_as_page"] = sent["present"] == len(requests) and set(sent["values"]) <= set(page_agents)
    if any("ip_class" in request for request in requests):
        out["ip_classes"] = sorted({request["ip_class"] for request in requests if request.get("ip_class")})
    return out


def _observations(index, parts):
    """The viewport sizes one page view recorded, in order: the environment snapshot's (at load in the lab, so it
    comes first; at its own time in cake.js), raw geo records and rrweb's sizes."""
    out = []
    if isinstance(parts.window, dict):
        key = (index, 0, 0) if parts.window_t is None else (index, 1, parts.window_t)
        out.append(_Size(key, parts.window.get("iw"), parts.window.get("ih"), parts.window.get("oh")))
    for item in parts.items:
        if item.get("ty") == GEO_ITEM and isinstance(item.get("g"), list):
            geometry = dict(zip(GEO_LAYOUT, item["g"]))
            out.append(_Size((index, 1, item.get("t") or 0), geometry.get("iw"), geometry.get("ih"),
                             geometry.get("oh")))
    for event in parts.rrweb:
        data = event.get("data") or {}
        resize = event.get("type") == RRWEB_INCREMENTAL and data.get("source") == RRWEB_VIEWPORT_RESIZE
        if event.get("type") == RRWEB_META or resize:
            out.append(_Size((index, 1, event.get("timestamp") or 0), data.get("width"), data.get("height"), None))
    return out


def _changes(observations):
    """Each change of viewport size between one observation and the next (an outer-height change only when both
    observations recorded the outer height)."""
    changes, previous = [], None
    for size in sorted(observations, key=lambda o: o.key):
        if not isinstance(size.width, (int, float)) or not isinstance(size.height, (int, float)):
            continue
        if previous is not None and (size.width, size.height) != (previous.width, previous.height):
            change = {"page": size.key[0], "dw": size.width - previous.width, "dh": size.height - previous.height,
                      "w": size.width, "h": size.height}
            if size.outer is not None and previous.outer is not None:
                change["doh"] = size.outer - previous.outer
            changes.append(change)
        previous = size
    return changes


def _assemble(parts_per_page, collect_requests, settings):
    """The signals dict from each page view's parts, in page order, and the upload requests."""
    pages, observations = [], []
    for index, parts in enumerate(parts_per_page):
        page = {"path": parts.path}
        if parts.env is not None:
            page["env"] = parts.env
        auto = _auto(parts.autos)
        if auto is not None:
            page["auto"] = auto
        if parts.botd is not None:
            page["botd"] = parts.botd
        if parts.raw_ran:
            if parts.dom_watch:  # without the DOM watch, no dom_add record means unknown, not "nothing added"
                page["dom_add"] = [{key: item.get(key) for key in DOM_FIELDS}
                                   for item in parts.items if item.get("ty") == DOM_ADD_ITEM]
            page["hidden_input"] = _hidden_input(parts.items, settings["hidden_input"])
        if parts.botscent:
            page["botscent"] = _botscent(parts.botscent)
        if parts.nav is not None:
            page["nav"] = {"headers": _headers(parts.nav.get("headers"), settings["network_headers"])}
        if parts.marks is not None:
            page["markers"] = parts.marks
        pages.append(page)
        observations += _observations(index, parts)
    signals = {"pages": pages}
    page_agents = [p.env.get("userAgent") for p in parts_per_page if isinstance(p.env, dict) and p.env.get("userAgent")]
    collect = _collect(list(collect_requests), settings["network_headers"], page_agents)
    if collect is not None:
        signals["collect"] = collect
    if observations:
        signals["viewport_changes"] = _changes(observations)
    return signals


# ---------------------------------------------------------------- cake.js, upload format version 1

def _cake_page_views(batches):
    """Each page view's records in arrival order, keeping one copy of a batch sent twice (s, pv, seq); page views in
    page order (the page record's number, else the first batch's time)."""
    seen, views = set(), defaultdict(list)
    for batch in batches:
        key = (batch.get("s"), batch.get("pv"), batch.get("seq"))
        if key not in seen:
            seen.add(key)
            views[batch.get("pv")].append(batch)
    ordered = []
    for pv, view in views.items():
        view.sort(key=lambda batch: batch.get("seq") or 0)
        signals = [record for batch in view for record in batch.get("x") or []]
        number = next((r.get("n") for r in signals if r.get("ty") == CAKE_PAGE_RECORD and r.get("n") is not None),
                      None)
        first_t = min((batch.get("t") or 0) for batch in view)
        ordered.append(((number is None, number or 0, first_t), pv, view, signals))
    return [(pv, view, signals) for _, pv, view, signals in sorted(ordered, key=lambda entry: entry[0])]


def _cake_parts(pv, view, signals, visit, page_requests):
    by_type = defaultdict(list)
    for record in signals:
        by_type[record.get("ty")].append(record)
    auto = {}
    for record_type, fields in CAKE_AUTO_FIELDS.items():
        for record in by_type[record_type]:
            auto.update({field: record[field] for field in fields if field in record})
    if "ipcFlooding" in visit:
        auto["ipcFlooding"] = visit["ipcFlooding"]
    if "iframeSharesRealm" in visit:  # the lab kept it inside nativeTampering
        tampering = dict(auto.get("nativeTampering") or {})
        tampering["iframeSharesRealm"] = visit["iframeSharesRealm"]
        auto["nativeTampering"] = tampering
    env_record = by_type["env"][-1] if by_type["env"] else None
    env = env_record.get("env") if env_record else None
    botd = by_type["botd"][-1] if by_type["botd"] else None
    raw = [record for batch in view for record in batch.get("r") or []]
    url = next((batch.get("u") for batch in view if batch.get("u")), None)
    return _Parts(path=addresses.path(url), env=env, autos=[auto] if auto else [],
                  botd={k: v for k, v in botd.items() if k not in CAKE_RECORD_KEYS} if botd else None,
                  items=raw, raw_ran=bool(raw), dom_watch=True, botscent=by_type[CAKE_BOTSCENT_RECORD],
                  nav=(page_requests or {}).get(pv),
                  window=env.get("window") if isinstance(env, dict) else None,
                  window_t=env_record.get("t") if env_record else None,
                  rrweb=[event for batch in view for event in batch.get("e") or []],
                  marks=markers.page_marks(signals, raw=raw, until=_last_time(signals + raw)))


def _last_time(records):
    times = [record.get("t") for record in records if isinstance(record.get("t"), (int, float))]
    return max(times) if times else None


def cake_page_order(batches):
    """The page view ids of a visit's batches in the order from_cake lists its pages: what lines up facts kept per
    page view (the server half, prerendering) with the signals' pages and the environment hits' page indexes."""
    return [pv for pv, _, _ in _cake_page_views(list(batches))]


def _script_settings(views, names):
    """How the site owner had set the page script, as the page records say: a setting is true when it was on for any
    page view (the owner can change it between two page views); empty when no page record said."""
    found = {}
    for _, _, signals in views:
        for record in signals:
            if record.get("ty") != CAKE_PAGE_RECORD:
                continue
            for name in names:
                if name in record:
                    found[name] = found.get(name) is True or record[name] is True
    return found


def from_cake(batches, collect_requests=(), page_requests=None, settings=None):
    """Signals of one visit (one `s`) from cake.js's batches (see the module docstring)."""
    settings = settings or load_rules().signals
    views = _cake_page_views(list(batches))
    visit = next(({k: v for k, v in record.items() if k not in CAKE_RECORD_KEYS}
                  for _, _, signals in views for record in signals if record.get("ty") == CAKE_VISIT_RECORD), {})
    parts = [_cake_parts(pv, view, signals, visit, page_requests) for pv, view, signals in views]
    signals = _assemble(parts, collect_requests, settings)
    script = _script_settings(views, settings["script_settings"])
    if script:
        signals["script_settings"] = script
    return signals


# ---------------------------------------------------------------- the research lab

def _split(payloads, marker, start):
    """Reports carrying `marker`, grouped into page views: a `start` report opens a view of its path, any other
    report joins the latest view of its path. Returns _View tuples in opening order."""
    views, latest = [], {}
    for index, report in enumerate(payloads):
        if marker not in report:
            continue
        path = report.get("page")
        if report.get("kind") == start or path not in latest:
            latest[path] = len(views)
            views.append(_View(path, index, []))
        views[latest[path]].reports.append(report)
    return views


def _pair(payloads):
    """Page views in load order, each with its env.js and raw.js reports: the k-th view of a path in one script is
    the k-th view of that path in the other (raw.js's meta report often arrives before env.js's load report)."""
    env_views = _split(payloads, "snap", ENV_VIEW_START)
    raw_views = _split(payloads, "items", RAW_VIEW_START)
    raw_by_path = defaultdict(list)
    for view in raw_views:
        raw_by_path[view.path].append(view)
    seen, paired = Counter(), []
    for view in env_views:
        k = seen[view.path]
        seen[view.path] += 1
        raw = raw_by_path[view.path][k] if k < len(raw_by_path[view.path]) else None
        first = min(view.first, raw.first) if raw else view.first
        paired.append(_Paired(first, view.path, view.reports, raw.reports if raw else []))
    for path, views in raw_by_path.items():  # raw.js views beyond what env.js reported for that path
        paired += [_Paired(view.first, path, [], view.reports) for view in views[seen[path]:]]
    return sorted(paired, key=lambda view: view.first)


def _lab_parts(view, nav):
    snaps = [report["snap"] for report in view.env if isinstance(report.get("snap"), dict)]
    env = next((snap["env"] for snap in snaps if isinstance(snap.get("env"), dict)), None)
    botd = [snap["botd"] for snap in snaps if snap.get("botd") is not None]
    items = [item for report in view.raw if report.get("kind") == RAW_EVENTS for item in report.get("items") or []]
    return _Parts(path=view.path, env=env, autos=[snap["auto"] for snap in snaps if isinstance(snap.get("auto"), dict)],
                  botd=botd[-1] if botd else None, items=items,
                  raw_ran=any(report.get("kind") == RAW_EVENTS for report in view.raw),
                  dom_watch=any(item.get("ty") == DOM_ADD_ITEM for item in items),  # some lab raw.js had no watch
                  botscent=[item for item in items if item.get("ty") == BOTSCENT_ITEM], nav=nav,
                  window=env.get("window") if isinstance(env, dict) else None, window_t=None,
                  rrweb=[event for report in view.raw if report.get("kind") == RRWEB_EVENTS
                         for event in report.get("items") or []], marks=markers.recorder_marks(items))


def from_lab(payloads, requests=(), settings=None):
    """Signals of one lab session (see the module docstring)."""
    settings = settings or load_rules().signals
    payloads, requests = list(payloads), list(requests)
    navs = defaultdict(list)
    for request in requests:
        if request.get("method") == PAGE_METHOD:
            navs[request.get("path")].append(request)
    taken, parts = Counter(), []
    for view in _pair(payloads):
        k = taken[view.path]
        taken[view.path] += 1
        parts.append(_lab_parts(view, navs[view.path][k] if k < len(navs[view.path]) else None))
    uploads = [request for request in requests if request.get("method") == COLLECT_METHOD]
    return _assemble(parts, uploads, settings)
