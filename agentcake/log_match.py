"""A web server's page requests matched to the visits they opened, and what they say kept.

record(con, envelope, now_ms, c, directory=None) -> counts. The caller (edge_api) holds store.LOCK and commits.

A log line has no token, so it is matched the way N5 says: by the visitor's address, hashed with the salt the
uploads are hashed with (ip_salt.py), its User-Agent, and time. A page view of a visit is a candidate for a line when
that page view's first upload (the requests rows of cake.js's own uploads) came from the same address hash and
User-Agent, between log_match_skew_s before and log_match_window_s after the line's time (settings). Lines are taken
in time order, first each by a candidate whose page URL has the line's path, then the rest by any candidate left;
among candidates the one whose first upload came soonest wins, and one page request opens one page view. A line
already kept for that visit (same time, address hash, User-Agent, method, path, status) is a duplicate, so importing
a log twice keeps each line once.

A matched line becomes one more requests row: seq NULL, pv the page view it opened, and as facts
(JSON) what netfacts.request_facts keeps of the headers sent (no header order, no origin: a log has neither), with
source "log", format, method, path (without the query), status, the address's published range and network class
(lists.match_ip, as for an upload), ip_hash and net_hash (netfacts.address_hashes), and, for a request with Web Bot
Auth headers, the result of verifying it at its own time against the release's keys (webbotauth.verify_request) under
"wba", in the shape collect.py keeps an upload's in, so that the verdict (evidence.py) weighs both alike. A line
that matches no visit is dropped whole: that visitor never ran cake.js (no consent given, or no JavaScript), and the
log is the site's. Every record's address is looked up and hashed, then dropped; it is in no row, count or message.

counts: records (well-formed ones), matched, duplicates, unmatched, bad (not a record), and views_without_address,
candidate page views whose uploads carried no address: no line can match those (log_report explains it).
"""
import json
from collections import Counter, defaultdict, namedtuple

from agentcake import addresses, ip_salt, netfacts
from agentcake.datafiles import load, sizes
from agentcake.detect import httpsig, lists, webbotauth
from agentcake.evidence import VERIFICATION_FIELDS, WEB_BOT_AUTH
from agentcake.log_formats import LogRecord
from agentcake.units import MS_PER_S

SPEC = load("data/logs.json")
SOURCE = "log"
COUNTS = ("records", "matched", "duplicates", "unmatched", "bad", "views_without_address")
SIGNATURE_FIELDS = tuple(name.lower() for name in netfacts.SIGNATURE_HEADERS)
USER_AGENT = "user-agent"

View = namedtuple("View", "session pv first_ms path")
Line = namedtuple("Line", "index t_ms key identity path facts")


def record(con, envelope, now_ms, c, directory=None):
    """Match and keep the envelope's records (see the module docstring); returns the counts."""
    counts = Counter(dict.fromkeys(COUNTS, 0))
    salt, verifier = ip_salt.current(con, now_ms), _Verifier(directory)
    lines = []
    for index, raw in enumerate(envelope["records"]):
        line = _line(index, raw, envelope["format"], salt, verifier)
        if line is None:
            counts["bad"] += 1
        else:
            lines.append(line)
    counts["records"] = len(lines)
    if not lines:
        return dict(counts)
    window_ms, skew_ms = c["log_match_window_s"] * MS_PER_S, c["log_match_skew_s"] * MS_PER_S
    low_ms, high_ms = min(line.t_ms for line in lines) - skew_ms, max(line.t_ms for line in lines) + window_ms
    views, kept, taken, without_address = _candidates(con, low_ms, high_ms)
    counts["views_without_address"] = without_address
    duplicates = {line.index for line in lines if line.identity in kept}
    chosen = {}
    for same_path in (True, False):
        for line in sorted(lines, key=lambda each: (each.t_ms, each.index)):
            if line.index in chosen or line.index in duplicates:
                continue
            view = _choose(line, views.get(line.key, ()), taken, window_ms, skew_ms, same_path)
            if view is not None:
                chosen[line.index] = view
                taken.add((view.session, view.pv))
    for line in lines:
        view = chosen.get(line.index)
        if view is not None:
            con.execute("INSERT INTO requests(session_id, recv_ms, seq, pv, facts) VALUES(?,?,NULL,?,?)",
                        (view.session, line.t_ms, view.pv, json.dumps(line.facts)))
    counts.update(matched=len(chosen), duplicates=len(duplicates))
    counts["unmatched"] = len(lines) - len(chosen) - len(duplicates)
    return dict(counts)


# ---------------------------------------------------------------- one record
def _line(index, raw, format_name, salt, verifier):
    """The Line of a record /edge received, or None when it is not one. Its address leaves nothing behind but the
    look-up's result and the two salted hashes."""
    record = _well_formed(raw)
    if record is None:
        return None
    hashes = netfacts.address_hashes(salt, record.ip)
    if not hashes:
        return None
    facts = netfacts.request_facts(record.headers, None, False, netfacts.look_up(record.ip))
    facts.pop("names", None)
    facts.pop("origin", None)
    path = (record.path or "")[:sizes()["max_chars"]["token_path"]]
    facts.update(source=SOURCE, format=format_name, method=record.method, path=path, status=record.status, **hashes)
    signature = verifier.check(record)
    if signature is not None:
        facts[WEB_BOT_AUTH] = signature
    key = (hashes["ip_hash"], _header_value(facts["headers"], USER_AGENT))
    return Line(index, record.t_ms, key, _identity(key, record.t_ms, facts), path, facts)


def _well_formed(raw):
    """A LogRecord from a record as logs.to_json() writes it ({t, ip, m, u, s, h, sc, hd}), or None."""
    caps = SPEC["edge"]["max_chars"]
    if not isinstance(raw, dict):
        return None
    t_ms, ip, method, target, status = raw.get("t"), raw.get("ip"), raw.get("m"), raw.get("u"), raw.get("s")
    host, scheme, headers = raw.get("h"), raw.get("sc"), raw.get("hd")
    ok = (type(t_ms) is int and t_ms >= 0 and type(status) is int and short_text(ip, caps["ip"])
          and short_text(method, caps["method"]) and short_text(target, caps["target"])
          and (host is None or short_text(host, caps["host"]))
          and (scheme is None or short_text(scheme, caps["scheme"]))
          and isinstance(headers, dict)
          and all(short_text(name, caps["field"]) and short_text(value, caps["header"])
                  for name, value in headers.items()))
    if not ok:
        return None
    return LogRecord(t_ms, ip, method, target, None, status, host, scheme,
                     {name.lower(): value for name, value in headers.items()})


def short_text(value, cap):
    """Whether value is a text field an /edge envelope may hold: a string, not empty, of at most cap characters
    (data/logs.json edge.max_chars; edge_api checks the envelope's own fields with it too)."""
    return isinstance(value, str) and 0 < len(value) <= cap


def _header_value(pairs, name):
    """The first value of the header name (any case) among stored [name, value] pairs, or None."""
    return next((value for key, value in pairs or () if str(key).lower() == name), None)


def _identity(key, t_ms, facts):
    return key + (t_ms, facts["method"], facts["path"], facts["status"])


class _Verifier:
    """Web Bot Auth verification of a record at the time it was logged, against the release's keys (or the
    directory given); a record without any of its headers is not verified."""

    def __init__(self, directory):
        self.directory = directory

    def check(self, record):
        if not any(name in record.headers for name in SIGNATURE_FIELDS):
            return None
        request = httpsig.Request(record.method, record.scheme or SPEC["default_scheme"], record.host or "",
                                  record.target, list(record.headers.items()))
        result = webbotauth.verify_request(request, self._directory(), record.t_ms / MS_PER_S)
        return {name: getattr(result, name) for name in VERIFICATION_FIELDS}

    def _directory(self):
        if self.directory is None:
            try:
                keys = lists.current().key_directories()
            except lists.ListsError:  # no readable lists: every signer is unknown, so declared
                keys = {}
            self.directory = webbotauth.KeyDirectory(keys, webbotauth.default_settings())
        return self.directory


# ---------------------------------------------------------------- the visits around the lines
def _candidates(con, low_ms, high_ms):
    """The page views whose first upload arrived between low_ms and high_ms, by (address hash, User-Agent); the
    identities of the lines kept already for these visits and the page views they opened; and how many page views
    had no address to match by."""
    views, kept, taken, without = defaultdict(list), set(), set(), 0
    sessions = con.execute("SELECT id FROM sessions WHERE end_ms >= ? AND start_ms <= ?", (low_ms, high_ms))
    for (session,) in sessions.fetchall():
        first_uploads = {}
        for pv, recv_ms, seq, text in con.execute("SELECT pv, recv_ms, seq, facts FROM requests WHERE session_id=? "
                                                  "ORDER BY recv_ms, rowid", (session,)):
            if seq is not None:  # an upload of cake.js format v1
                first_uploads.setdefault(pv, (recv_ms, text))
                continue
            facts = json.loads(text) if pv is not None else {}  # a cake 0.3.4 upload has no page view
            if facts.get("source") == SOURCE:
                key = (facts.get("ip_hash"), _header_value(facts.get("headers"), USER_AGENT))
                kept.add(_identity(key, recv_ms, facts))
                taken.add((session, pv))
        pages = _first_urls(con, session)
        for pv, (first_ms, text) in first_uploads.items():
            if not low_ms <= first_ms <= high_ms:
                continue
            facts = json.loads(text)
            ip_hash, user_agent = facts.get("ip_hash"), _header_value(facts.get("headers"), USER_AGENT)
            if not ip_hash or user_agent is None:
                without += 1
                continue
            views[(ip_hash, user_agent)].append(View(session, pv, first_ms, pages.get(pv)))
    return views, kept, taken, without


def _first_urls(con, session):
    """The path of each page view's URL, as its first batch gave it."""
    paths = {}
    for pv, url in con.execute("SELECT pv, url FROM batches WHERE session_id=? ORDER BY pv, seq", (session,)):
        if pv not in paths and url:
            parts = addresses.split(url)  # an address that cannot be read has no path to match, only a time
            paths[pv] = (parts.path or "/") if parts else None
    return paths


def _choose(line, views, taken, window_ms, skew_ms, same_path):
    best, best_gap = None, None
    for view in views:
        gap = view.first_ms - line.t_ms
        if (view.session, view.pv) in taken or not -skew_ms <= gap <= window_ms:
            continue
        if same_path and view.path != line.path:
            continue
        if best is None or gap < best_gap:
            best, best_gap = view, gap
    return best
