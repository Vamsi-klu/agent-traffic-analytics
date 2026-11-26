"""Keeping one accepted upload: its request's facts, the batch's key, the visit, the token, the records,
and what was refused.

record(con, batch, visit, now_ms, c) writes, in the caller's transaction (store.LOCK held, the caller commits):

0. the request's network facts (netfacts.request_facts) in the requests table, for every accepted request (a copy of
   a batch is a request too), with the batch's page view and number, and the address's salted hashes
   (netfacts.address_hashes, the salt of ip_salt.py) when the load balancer gave one;
1. the batch's key (batches table, with its header). A version 1 batch whose (s, pv, seq) is there already is a copy
   (sent again from sessionStorage, or an answer cake.js could not read): nothing else is written. A cake 0.3.4
   batch has no key and is always kept;
2. the session row: first and last seen, URL, User-Agent, automation flag, Sec-Fetch headers, self-check flag, where
   the visit came from (site_origin.py; once "other", it stays "other"), the load balancer's network facts; what
   the web analytics tables group it by (web_props.keep: the visitor id, the entry source, the device, the place);
   and the visit it is a tab session of (visit_join.place: by the batch's browser session id, else by the visitor id);
3. the server-half token (edge_token.take_token), which also puts the id of a token it verified on the batch's
   row: that links each page view to its server half, also a page view that reused an earlier page view's token;
4. each stream's records with their page view (streams.append), up to max_events_per_session per stream; the
   rrweb replay only while the disk budget and the disk's free space allow (space.room_for_replay), else
   counted in sessions.events_dropped as in 0.3.4. Raw input and signals are kept either way: judging needs
   them. Records over the limit are counted in sessions.events_refused and the refusals table.

count(con, reason, records, now_ms) adds one refused upload to the refusals table. The visitor's address (Visit.
address) is only hashed and handed to take_token to compare networks; it is never written. take_token also compares
the upload request's User-Agent and Accept-Language, as Visit.facts keeps them, with the token's.
"""
import json
from collections import namedtuple
from dataclasses import dataclass
from typing import Optional

from agentcake import ip_salt, netfacts, streams, visit_join, web_props
from agentcake.edge_token import HEADERS, Delivery, take_token
from agentcake.space import room_for_replay

REPLAY = "rrweb"
BATCH_STREAMS = ("rrweb", "raw", "env")  # protocol: the batches table's n_<stream> columns, in this order

Kept = namedtuple("Kept", "copy token")  # copy: the batch was stored before; token: take_token's answer or None


@dataclass
class Visit:
    """What the request says about the visit, besides the batch."""
    origin: str                      # site_origin.classify
    sec_fetch: str                   # the Sec-Fetch-* headers, JSON
    net: Optional[dict]              # netfacts.net_facts on the public listener with trust_lb, else None
    address: Optional[str]           # the visitor's IP address, to hash and for take_token; never written
    public: bool
    facts: dict                      # netfacts.request_facts, without the address's hashes


def record(con, batch, visit, now_ms, c):
    """Keep one batch (see the module docstring); returns Kept."""
    _request(con, batch, visit, now_ms)
    if batch.page_view is not None and not _new_batch(con, batch, now_ms):
        return Kept(True, None)
    _session(con, batch, visit, now_ms)
    web_props.keep(con, batch, visit)
    visit_join.place(con, batch.session, batch.browser_session, batch.window, visit.origin, now_ms)
    took = take_token(con, batch.token, _delivery(batch, visit), now_ms, c) if batch.token else None
    _records(con, batch, now_ms, c)
    if batch.bad_records:
        count(con, "bad_record", batch.bad_records, now_ms)
    return Kept(False, took)


def count(con, reason, records, now_ms):
    con.execute("""INSERT INTO refusals(reason, posts, records, last_ms) VALUES(?,1,?,?) ON CONFLICT(reason) DO UPDATE
                   SET posts=posts+1, records=records+excluded.records, last_ms=excluded.last_ms""",
                (reason, records, now_ms))


def _request(con, batch, visit, now_ms):
    hashes = netfacts.address_hashes(ip_salt.current(con, now_ms), visit.address) if visit.address else {}
    con.execute("INSERT INTO requests(session_id, recv_ms, seq, pv, facts) VALUES(?,?,?,?,?)",
                (batch.session, now_ms, batch.seq, batch.page_view, json.dumps(dict(visit.facts, **hashes))))


def _new_batch(con, batch, now_ms):
    """Insert the batch's key and header; False when that key was there already."""
    counts = [len(batch.records.get(stream, ())) for stream in BATCH_STREAMS]
    cursor = con.execute("""INSERT INTO batches(session_id, pv, seq, recv_ms, t, url, why, dropped, n_rrweb, n_raw,
                            n_env) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
                         (batch.session, batch.page_view, batch.seq, now_ms, batch.made_ms, batch.url, batch.why,
                          batch.dropped, *counts))
    return cursor.rowcount == 1


def _session(con, batch, visit, now_ms):
    con.execute("""INSERT INTO sessions(id, start_ms, end_ms, url, ua, webdriver, sec_fetch, is_test, origin, net)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET end_ms=excluded.end_ms,
                   url=COALESCE(sessions.url, excluded.url), ua=COALESCE(sessions.ua, excluded.ua),
                   webdriver=max(webdriver, excluded.webdriver), net=COALESCE(sessions.net, excluded.net),
                   origin=CASE WHEN excluded.origin='other' THEN 'other' ELSE sessions.origin END""",
                (batch.session, now_ms, now_ms, batch.url, batch.user_agent, int(batch.webdriver), visit.sec_fetch,
                 int(batch.test and not visit.public), visit.origin, _json(visit.net)))


def _delivery(batch, visit):
    """Who brought the batch's token, and the upload request's own User-Agent and Accept-Language (kept in the
    request's facts, data/netfacts.json) and address, for take_token to compare with the token's."""
    seen = {name.lower(): value for name, value in visit.facts.get("headers", ())}
    return Delivery(session=batch.session, page_view=batch.page_view, seq=batch.seq,
                    user_agent=seen.get(HEADERS["user_agent"]), language=seen.get(HEADERS["accept_language"]),
                    address=visit.address)


def _records(con, batch, now_ms, c):
    refused = 0
    for stream, records in batch.records.items():
        if stream == REPLAY and not room_for_replay(con, c, now_ms):
            con.execute("UPDATE sessions SET events_dropped=events_dropped+? WHERE id=?", (len(records), batch.session))
            continue
        room = max(0, c["max_events_per_session"] - streams.event_count(con, batch.session, stream))
        kept = records[:room]
        refused += len(records) - len(kept)
        if kept:
            streams.append(con, batch.session, stream, kept, now_ms)
    if refused:
        con.execute("UPDATE sessions SET events_refused=events_refused+? WHERE id=?", (refused, batch.session))
        count(con, "session_limit", refused, now_ms)


def _json(value):
    return json.dumps(value) if value else None
