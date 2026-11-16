"""The collector's half of cutting sessions by PostHog's time rules.

cake.js begins a new session id after 30 minutes without activity or once a session has lasted 24 hours
(static/src/session.js). A script that does not (an older cake.js still open in a tab, a copy a site serves itself,
anything else that posts to collect) may keep one id for days. route(con, batch) puts each version 1 batch into the
session its activity belongs to under the same rules, from the same settings (data/cakejs.json "session"): the same
idle time, the same longest session, and the same records counted as activity (the raw input records of a user
interaction, a geometry record made by a resize, a page view). So whichever script sent them, a session means the
same thing. A cake 0.3.4 batch (no page view, no record kinds) keeps the id it came with.

The id the script sent is the tab's (session_web.tab_id). A tab's first session keeps it; when a batch's first activity
comes more than idle_ms after the last activity of the tab's latest session, or more than max_ms after that session's
first activity, it begins the next session, whose id is continuation_id(tab, n) for the first n past the tab's
sessions that no session has (retention may have deleted its oldest ones), and every later batch of the tab goes
there. A batch goes to the session of the tab whose first activity is the latest one not after the batch's own
first activity (or first record), so a batch sent again, or one that waited in sessionStorage, still finds the session
it was sent in, and a copy is still known as one. A batch without activity never begins a session: it goes where its
time puts it, as cake.js keeps sending such records under the session they belong to. The new session starts with what
web_props.py knew of the one before (the visitor and its identify hash, the entry source, the device, the place), as
cake.js's session record carries the page's source to a session it begins on the page.

    route(con, batch) -> Batch                 the batch, with the session id the rules give it
    continuation_id(tab, n) -> id              the id of a tab's n-th session (n >= 2), 32 hex digits like cake.js's
    with_continuations(con, ids) -> [id]        the ids and every session cut from them (agentcake delete)
"""
import dataclasses
import hashlib

from agentcake.datafiles import load
from agentcake.upload import RECORD_FIELDS

RULES = load("data/cakejs.json")["script"]["session"]
ID_HEX_DIGITS = load("data/cakejs.json")["script"]["id_bytes"] * 2  # protocol: two hex digits per byte, as cake.js
STREAM_OF_FIELD = {key: stream for key, stream, _ in RECORD_FIELDS}
RAW, SIGNALS = STREAM_OF_FIELD["r"], STREAM_OF_FIELD["x"]
# A record's kind as its compact JSON text writes it (upload.record_text): only these few fields are looked for, so
# no record is parsed.
RAW_MARKS = tuple(f'"ty":"{kind}"' for kind in RULES["activity_raw"])
GEO_MARK = '"ty":"geo"'
GEO_WHY_MARKS = tuple(f'"why":"{why}"' for why in RULES["activity_geo"])
SIGNAL_MARKS = tuple(f'"ty":"{kind}"' for kind in RULES["activity_signals"])
# What a continuation begins with from the session before it (web_props.py's columns).
CARRIED = ("visitor", "person", "entry_t", "referring_domain", "utm_source", "utm_medium", "utm_campaign",
           "utm_content", "utm_term", "gad_source", "click_ids", "channel", "browser", "os", "device_type", "country",
           "subdivision", "city", "language", "tz_offset")


def _is_activity(stream, text):
    if stream == RAW:
        return any(mark in text for mark in RAW_MARKS) or (GEO_MARK in text and any(m in text for m in GEO_WHY_MARKS))
    return stream == SIGNALS and any(mark in text for mark in SIGNAL_MARKS)


def activity_times(batch):
    """The times (epoch ms) of the batch's activity records, oldest first."""
    return sorted(record.ts for stream, records in batch.records.items() for record in records
                  if _is_activity(stream, record.text))


def _first_time(batch):
    times = [record.ts for records in batch.records.values() for record in records]
    return min(times) if times else batch.made_ms


def continuation_id(tab, n):
    return hashlib.sha256(f"{tab}|{n}".encode()).hexdigest()[:ID_HEX_DIGITS]


def _expired(row, t):
    _, active_from, active_last = row
    if active_last is None:
        return False
    return t - active_last > RULES["idle_ms"] or (active_from is not None and t - active_from > RULES["max_ms"])


def route(con, batch):
    """The batch with the session id its activity belongs to (see the module docstring); writes the tab's clock."""
    if batch.page_view is None:
        return batch
    tab, times = batch.session, activity_times(batch)
    rows = con.execute("SELECT session_id, active_from, active_last FROM session_web WHERE tab_id=? "
                       "ORDER BY active_from", (tab,)).fetchall()
    if not rows:
        _clock(con, tab, tab, times, insert=True)
        return batch
    t = times[0] if times else _first_time(batch)
    row = _session_at(rows, t)
    if times and row is rows[-1] and _expired(row, times[0]):
        session = _next_id(con, tab, len(rows) + 1)
        _clock(con, session, tab, times, insert=True)
        _carry(con, row[0], session)
    else:
        session = row[0]
        _clock(con, session, tab, times, insert=False)
    return batch if session == batch.session else dataclasses.replace(batch, session=session)


def with_continuations(con, ids):
    """The ids, then every session the collector cut from a tab one of them names, each once."""
    found = list(ids)
    for session_id in ids:
        found += [cut for (cut,) in con.execute(
            "SELECT session_id FROM session_web WHERE tab_id=? ORDER BY active_from", (session_id,))]
    return list(dict.fromkeys(found))


def _next_id(con, tab, n):
    """continuation_id(tab, n), or of the first number after n that no session of the tab has: once retention deleted
    a tab's oldest sessions, it has fewer of them than ids were given."""
    while con.execute("SELECT 1 FROM session_web WHERE session_id=?", (continuation_id(tab, n),)).fetchone():
        n += 1
    return continuation_id(tab, n)


def _session_at(rows, t):
    """The row of the tab's session that time t falls in: the latest one begun at or before t, else the first."""
    found = rows[0]
    for row in rows:
        if row[1] is not None and t is not None and row[1] <= t:
            found = row
    return found


def _clock(con, session, tab, times, insert):
    first, last = (times[0], times[-1]) if times else (None, None)
    if insert:
        con.execute("INSERT OR IGNORE INTO session_web(session_id, tab_id, active_from, active_last) VALUES(?,?,?,?)",
                    (session, tab, first, last))
    elif times:
        con.execute("UPDATE session_web SET active_from=MIN(COALESCE(active_from, ?), ?), "
                    "active_last=MAX(COALESCE(active_last, ?), ?) WHERE session_id=?",
                    (first, first, last, last, session))


def _carry(con, before, session):
    columns = ", ".join(CARRIED)
    con.execute(f"UPDATE session_web SET ({columns}) = (SELECT {columns} FROM session_web WHERE session_id=?) "
                "WHERE session_id=?", (before, session))
