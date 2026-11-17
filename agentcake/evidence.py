"""One session's evidence for the verdict, read from the database: what verdict.judge() takes.

    session_evidence(con, session_id, c=None, now_s=None) -> (evidence, raw, rrweb)

The evidence keys are agentcake/detect/verdict.py's. Each comes from what collect kept and the server
half:
  pages        one per page view, in env_signals' page order: when it began (its first batch), whether it was
               prerendered and then shown (the page record cake.js sends, the visibility of its records), and the
               Sec-Purpose of the request that opened it (the page's server half: srv.body through batches.token_id)
  env          env_rules.evaluate() of env_signals.from_cake(the visit's batches, its requests' facts, each page
               view's server half read back as request headers)
  marks        markers.turn_spans() of those signals: when an agent product's indicator said its agent was working
  user_agents, platform   verdict_identity.claims_from_signals() of those signals; the page's User-Agent also from
               the batches' ua field (sessions.ua: the only one a cake 0.3.4 visit sends)
  signatures   collector: the best Web Bot Auth result collect kept with a request (facts "wba", collect.py);
               server: a page request's Signature-Agent, a claim only (the token keeps no signature to check)
  network      the lists.match_ip() fields kept with the visit's requests: the latest that had an address
  visits       when the earlier sessions from the same network began (the requests' net_hash)
  touch        the environment record says mobile, or there is a coarse pointer and no fine one
  mode         "server" when server mode is on (public_listen), else "local": every visit comes from 127.0.0.1
  weak         weak.facts() of the signals, requests and raw records, with how many sessions came from the same
               address (its salted ip_hash) within the weak same_address window
raw: the raw stream's records (the behaviour model's input); rrweb: only when there are none (cake 0.3.x
recordings), the rrweb events. A record without a time is left out: the behaviour model orders by it. A cake 0.3.4
visit has one page view (None), and its server half is the session's first srv row (0.3.4 kept no page view to link
it to).
"""
import json

from agentcake import session_replay, streams, visit_batches
from agentcake.config import load_cfg
from agentcake.datafiles import load
from agentcake.detect import env_rules, env_signals, httpsig, markers, verdict_identity, weak, webbotauth
from agentcake.storage_config import now_ms as clock_ms
from agentcake.units import MS_PER_S

HEADERS = load("data/edge.json")["headers"]
# The server half's token fields (edge_token.request_facts) and the request header each one holds.
TOKEN_HEADERS = ((("ua",), "user_agent"), (("al",), "accept_language"), (("ch", "ua"), "sec_ch_ua"),
                 (("ch", "pf"), "sec_ch_ua_platform"), (("ch", "mb"), "sec_ch_ua_mobile"),
                 (("sf", "s"), "sec_fetch_site"), (("sf", "m"), "sec_fetch_mode"), (("sf", "d"), "sec_fetch_dest"),
                 (("sf", "u"), "sec_fetch_user"))  # protocol: the token payload's format
TOKEN_PURPOSE, TOKEN_SIGNATURE, TOKEN_SIGNATURE_AGENT = "sp", "sg", "a"  # protocol: token payload fields
MATCH_IP_FIELDS = ("range", "range_id", "range_kind", "operator", "verifies", "cloud", "cdn", "relay")
WEB_BOT_AUTH = "wba"  # the request facts key collect.py keeps a Web Bot Auth result under
VERIFICATION_FIELDS = ("outcome", "code", "signer", "keyid", "label", "via", "claimed", "facts")
PAGE_RECORD = "page"
PRERENDER_NAV = "prerender"  # protocol: the page record's nav (PerformanceNavigationTiming.type) of a prerender
COARSE, FINE = "coarse", "fine"  # protocol: CSS any-pointer values
SHOWN = 1  # protocol: cake.js's vs field, 1 while the page is visible
SERVER_MODE, LOCAL_MODE = "server", "local"
RAW_TIME, RRWEB_TIME = "t", "timestamp"  # protocol: the time field of a raw record (cake.js) and of an rrweb event


def session_evidence(con, session_id, c=None, now_s=None):
    """(evidence, raw, rrweb) of one stored session (see the module docstring)."""
    c = c or load_cfg()
    batches = visit_batches.batches(con, session_id)
    halves = _server_halves(con, session_id)
    pages, page_requests = _pages(batches, halves)
    signals = env_signals.from_cake(batches, visit_batches.collect_requests(con, session_id), page_requests)
    claims = verdict_identity.claims_from_signals(signals)
    batch_ua = (con.execute("SELECT ua FROM sessions WHERE id=?", (session_id,)).fetchone() or (None,))[0]
    if batch_ua and batch_ua not in claims["user_agents"]["page"]:
        claims["user_agents"]["page"].append(batch_ua)
    facts = [json.loads(text) for (text,) in
             con.execute("SELECT facts FROM requests WHERE session_id=? ORDER BY recv_ms, rowid", (session_id,))]
    raw = _timed((json.loads(text) for _, _, text in streams.read_events(con, session_id, ["raw"])), RAW_TIME)
    rrweb = None if raw else _timed((json.loads(text) for text in session_replay.rrweb_texts(con, session_id)),
                                    RRWEB_TIME)
    evidence = {"mode": SERVER_MODE if c.get("public_listen") else LOCAL_MODE, "pages": pages,
                "user_agents": claims["user_agents"], "platform": claims["platform"],
                "signatures": _signatures(facts, halves, now_s if now_s is not None else clock_ms() / MS_PER_S),
                "network": _network(facts), "rdns": None, "env": env_rules.evaluate(signals),
                "marks": markers.turn_spans(signals),
                "touch": _touch(signals), "visits": _visits(con, session_id, facts),
                "weak": dict(weak.facts(signals, facts, raw),
                             address_sessions=_address_sessions(con, session_id, facts))}
    return evidence, raw, rrweb


def _server_halves(con, session_id):
    """{page view: token payload}: each page view's first linked server half; a 0.3.4 visit's under None. A page view
    that reused another one's token (the browser showed it a stored copy) has no server half of its own; a token
    kept before 0.4.0 names no page view and stays with every page view linked to it."""
    halves = {}
    for pv, body in con.execute("SELECT b.pv, s.body FROM batches b JOIN srv s ON s.id = b.token_id WHERE "
                                "b.session_id=? AND (s.pv IS NULL OR s.pv = b.pv) ORDER BY b.pv, b.seq",
                                (session_id,)):
        halves.setdefault(pv, json.loads(body))
    if not halves:
        first = con.execute("SELECT body FROM srv WHERE session_id=? ORDER BY page_ms, recv_ms LIMIT 1",
                            (session_id,)).fetchone()
        if first:
            halves[None] = json.loads(first[0])
    return halves


def _token_headers(payload):
    """A server half's request headers, as env_signals reads a page request: {header name: value}."""
    out = {}
    for path, role in TOKEN_HEADERS:
        value = payload
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if value is not None:
            out[HEADERS[role]] = value
    return out


def _pages(batches, halves):
    """(the pages' facts in env_signals' page order, {page view: {"headers"}} for env_signals.from_cake)."""
    by_view = {batch["pv"]: batch for batch in batches}
    pages = []
    for pv in env_signals.cake_page_order(batches):
        batch = by_view[pv]
        record = next((x for x in batch.get("x") or [] if x.get("ty") == PAGE_RECORD), {})
        prerendered = bool(record.get("prerendering")) or record.get("nav") == PRERENDER_NAV
        shown = not prerendered or any(item.get("vs") == SHOWN for item in batch.get("r") or [])
        purpose = (halves.get(pv) or {}).get(TOKEN_PURPOSE)
        pages.append({"t": batch.get("t"), "sp": purpose, "prerendered": prerendered, "shown": shown})
    return pages, {pv: {"headers": _token_headers(payload)} for pv, payload in halves.items()}


def _signatures(facts, halves, now_s):
    """{"collector": the best Web Bot Auth result of the requests, "server": a page request's claim}."""
    out, order = {}, webbotauth.OUTCOME_ORDER
    for fact in facts:
        found = fact.get(WEB_BOT_AUTH)
        if found and ("collector" not in out or order.index(found["outcome"]) > order.index(out["collector"].outcome)):
            out["collector"] = webbotauth.Verification(**{name: found.get(name) for name in VERIFICATION_FIELDS})
    claim = next((half[TOKEN_SIGNATURE][TOKEN_SIGNATURE_AGENT] for half in halves.values()
                  if (half.get(TOKEN_SIGNATURE) or {}).get(TOKEN_SIGNATURE_AGENT)), None)
    if claim:
        request = httpsig.Request("GET", "https", "", "/", [(HEADERS["signature_agent"], claim)])
        out["server"] = webbotauth.verify_request(request, {}, now_s)  # no signature: always a claim (declared)
    return out


def _network(facts):
    looked_up = [fact for fact in facts if "range_id" in fact]
    return {name: looked_up[-1].get(name) for name in MATCH_IP_FIELDS} if looked_up else None


def _visits(con, session_id, facts):
    """When the earlier sessions from this session's network began (ms), oldest first."""
    net_hash = next((fact["net_hash"] for fact in reversed(facts) if fact.get("net_hash")), None)
    if not net_hash:
        return []
    rows = con.execute("SELECT DISTINCT s.start_ms FROM requests r JOIN sessions s ON s.id = r.session_id WHERE "
                       "r.session_id != ? AND json_extract(r.facts, '$.net_hash') = ? AND s.start_ms < "
                       "(SELECT start_ms FROM sessions WHERE id = ?) ORDER BY s.start_ms",
                       (session_id, net_hash, session_id))
    return [start for (start,) in rows]


def _timed(records, field):
    return [r for r in records if isinstance(r, dict) and isinstance(r.get(field), (int, float))
            and not isinstance(r.get(field), bool)]


def _address_sessions(con, session_id, facts):
    """How many sessions (this one too) came from this session's address within the same_address window, or None
    when its address was not seen (local mode, no load balancer)."""
    ip_hash = next((fact["ip_hash"] for fact in reversed(facts) if fact.get("ip_hash")), None)
    if not ip_hash:
        return None
    window_ms = load("data/verdict.json")["weak"]["same_address"]["window_s"] * MS_PER_S
    return con.execute("SELECT COUNT(DISTINCT session_id) FROM requests WHERE json_extract(facts, '$.ip_hash') = ? "
                       "AND recv_ms >= (SELECT end_ms FROM sessions WHERE id = ?) - ?",
                       (ip_hash, session_id, window_ms)).fetchone()[0]


def _touch(signals):
    for page in signals.get("pages") or []:
        env = page.get("env") or {}
        pointers = env.get("anyPointer") or []
        if (env.get("uaData") or {}).get("mobile") or (COARSE in pointers and FINE not in pointers):
            return True
    return False
