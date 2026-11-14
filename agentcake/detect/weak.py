"""Weak signals: patterns agents show but humans show too, so each only adds a reason (layer "weak") and never
changes a verdict (a guessed pattern never makes a Bot or an Agent).

    facts(signals, requests, raw, settings=None) -> what the signals below read, for verdict.decide's evidence["weak"]
    reasons(found, settings=None) -> [reason dicts]

  timezone-country   the browser's time zone is not one the address's country uses (IANA zone.tab: timezones.json)
  language-country   the browser's languages name regions, none of them the address's country
  same-address       many sessions from one address (its salted hash) within a window
  header-order       a User-Agent that claims a browser, on requests whose header names come in an order that
                     browser does not send (only requests that reached cake directly: a load balancer reorders them)
  display-change     the screen's colour depth or size changed within the session (Claude in Chrome's tab
                     reported 30 where its user's own window reported 24)
  window-jump        the window jumped across the screen while keeping its size
  rhythm             most steps come after a still pause (as when an AI looks at the page before it acts): "is
                     there time to think". Its other half, nearly every step right after the previous one,
                     was removed: humans step that way as often as agents do, so it only
                     wrote "like a script" into humans' replays
The keyboard and assistive-tool guard is the verdict's own (the reason behavior.assistive). The address's
country comes from the load balancer (server mode); in local mode the first two have nothing to compare. Thresholds
and the header anchors: agentcake/data/verdict.json "weak".

signals: env_signals' dict; requests: the visit's request facts (oldest first); raw: the raw stream's records.
"""
from agentcake import datafiles
from agentcake.detect import segment
from agentcake.detect.verdict_text import reason
from agentcake.units import MS_PER_S, PERCENT, S_PER_HOUR

SETTINGS_FILE = "data/verdict.json"
TIMEZONES_FILE = "data/timezones.json"
LANGUAGE_SEPARATOR, QUALITY_SEPARATOR, SUBTAG_SEPARATOR = ",", ";", "-"  # protocol: Accept-Language (RFC 9110 12.5.4)
REGION_LENGTH = 2  # protocol: a BCP 47 region subtag of two letters (ISO 3166-1)
LOAD_BALANCER_FACTS = ("country", "ja4", "proto")  # what netfacts.request_facts adds when a load balancer was there
MOVE = "move"
GEO = "geo"
GEO_SIZE, GEO_POSITION = slice(2, 4), slice(4, 6)  # protocol: cake.js geo record g = [iw, ih, ow, oh, sx, sy, ...]


def facts(signals, requests, raw, settings=None):
    """What the weak signals read, from one session's signals, request facts and raw records (see the docstring)."""
    rule = (settings or datafiles.load(SETTINGS_FILE))["weak"]
    envs = [page.get("env") or {} for page in signals.get("pages") or []]
    headers = [dict((name.lower(), value) for name, value in fact.get("headers") or []) for fact in requests]
    return {"country": next((f["country"] for f in reversed(requests) if f.get("country")), None),
            "timezones": _distinct(env.get("tz") for env in envs),
            "languages": _distinct([tag for env in envs for tag in env.get("languages") or []]
                                   + [tag for h in headers for tag in _accepted(h.get("accept-language"))]),
            "user_agents": _distinct(h.get("user-agent") for h in headers),
            # a request whose order is not known (a web server log's page request) has no "names"
            "header_orders": [fact["names"] for fact in requests
                              if fact.get("names") and not any(key in fact for key in LOAD_BALANCER_FACTS)],
            "color_depths": _distinct((env.get("screen") or {}).get("cd") for env in envs),
            "screens": _distinct(_size(env.get("screen")) for env in envs),
            "window_jump": _window_jump(raw),
            "steps": _steps(raw, rule["rhythm"]),
            "address_sessions": None}


def reasons(found, settings=None):
    """The weak reasons these facts give; [] for None (nothing recorded)."""
    if not found:
        return []
    rule = (settings or datafiles.load(SETTINGS_FILE))["weak"]
    out = []
    country = found.get("country")
    zones = datafiles.load(TIMEZONES_FILE)["zones"]
    for tz in found.get("timezones") or []:
        if country and tz in zones and country not in zones[tz]:
            out.append(reason("weak.timezone-country", "page", tz, tz=tz, country=country))
    regions = _distinct(_region(tag) for tag in found.get("languages") or [])
    if country and regions and country not in regions:
        out.append(reason("weak.language-country", "page", regions, languages=", ".join(found["languages"]),
                          country=country))
    same = found.get("address_sessions")
    if same is not None and same >= rule["same_address"]["min_sessions"]:
        out.append(reason("weak.same-address", "collector", same, n=same,
                          hours=round(rule["same_address"]["window_s"] / S_PER_HOUR)))
    out += _header_order(found, rule["header_order"])
    if len(found.get("color_depths") or []) > 1 or len(found.get("screens") or []) > 1:
        out.append(reason("weak.display-change", "page", found.get("color_depths"),
                          depths=", ".join(map(str, found.get("color_depths") or [])),
                          sizes=", ".join(found.get("screens") or [])))
    jump = found.get("window_jump")
    if jump is not None and jump >= rule["window_jump"]["min_px"]:
        out.append(reason("weak.window-jump", "page", jump, px=round(jump)))
    out += _rhythm(found.get("steps"), rule["rhythm"])
    return out


def _distinct(values):
    out = []
    for value in values:
        if value not in (None, "") and value not in out:
            out.append(value)
    return out


def _accepted(header):
    """The language tags of an Accept-Language value, without their weights."""
    return [part.split(QUALITY_SEPARATOR)[0].strip() for part in (header or "").split(LANGUAGE_SEPARATOR)
            if part.strip()]


def _region(tag):
    parts = str(tag).split(SUBTAG_SEPARATOR)
    regions = [p.upper() for p in parts[1:] if len(p) == REGION_LENGTH and p.isalpha()]
    return regions[0] if regions else None


def _size(screen):
    return f"{screen['w']}x{screen['h']}" if isinstance(screen, dict) and screen.get("w") else None


def _window_jump(raw):
    """The largest move of the window's position between two geo records with the same window size, in px."""
    jumps, previous = [], None
    for record in raw or []:
        g = record.get("g") if record.get("ty") == GEO else None
        if not isinstance(g, list) or len(g) < GEO_POSITION.stop:
            continue
        if previous and previous[GEO_SIZE] == g[GEO_SIZE]:
            (x0, y0), (x1, y1) = previous[GEO_POSITION], g[GEO_POSITION]
            jumps.append(max(abs(x1 - x0), abs(y1 - y0)))
        previous = g
    return max(jumps) if jumps else None


def _steps(raw, rule):
    """{"n", "still"}: steps (actions that are not pointer moves) and the share that came after a still pause (no
    input at all for still_ms)."""
    segments = segment.actions(sorted(raw or [], key=lambda record: record["t"]))
    pairs = [(prev, seg) for prev, seg in zip(segments, segments[1:]) if seg["kind"] != MOVE]
    if not pairs:
        return {"n": 0, "still": None}
    idle = [seg["start"] - prev["end"] for prev, seg in pairs]
    return {"n": len(pairs), "still": sum(gap >= rule["still_ms"] for gap in idle) / len(pairs)}


def _header_order(found, rule):
    claims = any(rule["browser_token"] in (ua or "") for ua in found.get("user_agents") or [])
    if not claims:
        return []
    for names in found.get("header_orders") or []:
        if rule["first"] not in names or (rule["before"] in names
                                          and names.index(rule["before"]) < names.index(rule["first"])):
            return [reason("weak.header-order", "collector", names[:rule["shown"]], browser=rule["browser"],
                           order=", ".join(names[:rule["shown"]]))]
    return []


def _rhythm(steps, rule):
    if not steps or steps["n"] < rule["min_steps"]:
        return []
    if steps["still"] >= rule["still_share"]:
        return [reason("weak.rhythm-pauses", "page", steps["still"], pct=round(steps["still"] * PERCENT),
                       seconds=round(rule["still_ms"] / MS_PER_S))]
    return []
