"""A session's rrweb replay, as cake 0.3.4's judge and replay page read it (S2.1).

Since S2.1 collect keeps rrweb events in chunks (streams.py). A database from cake 0.3.4 still has its replay rows in
the events table: `agentcake migrate` copies them into chunks and keeps them, and a visit that went on across the
upgrade has rows and newer chunks. rrweb_texts(con, session_id) gives every rrweb event once, oldest first: the
chunks, and each 0.3.4 row they do not hold yet (a row and its copy have the same time and the same JSON text; rows of
the same millisecond in the order they were written). missing_rows(con, session_id) is the same comparison for
`agentcake migrate`: the rows still to copy. S5.x's replay and S3.x's judging read the streams directly once 0.3.4
databases are migrated.
"""
import hashlib
import heapq
from collections import Counter
from operator import itemgetter

from agentcake import streams

STREAM = "rrweb"
OLD_ROWS = f"SELECT ts, body FROM events WHERE session_id=? AND {streams.OLD_REPLAY_ROW} ORDER BY ts, rowid"


def old_rows(con, session_id):
    """(ts, JSON text) of a session's 0.3.4 replay rows, in the order 0.3.4 wrote them."""
    return [(ts or 0, body) for ts, body in con.execute(OLD_ROWS, (session_id,))]


def rrweb_texts(con, session_id):
    """Every rrweb event of the session once, as JSON text, oldest first."""
    rows = old_rows(con, session_id)
    events = ((ts, text) for ts, _, text in streams.read_events(con, session_id, [STREAM]))
    if not rows:
        yield from (text for _, text in events)
        return
    copies = Counter(_key(ts, body) for ts, body in rows)

    def not_copies():
        for ts, text in events:
            key = _key(ts, text)
            if copies[key]:
                copies[key] -= 1
                continue
            yield ts, text

    for _, text in heapq.merge(rows, not_copies(), key=itemgetter(0)):
        yield text


def missing_rows(con, session_id, rows=None):
    """The session's 0.3.4 replay rows (ts, JSON text) its rrweb chunks do not hold yet, in order."""
    rows = old_rows(con, session_id) if rows is None else rows
    have = stream_keys(con, session_id)
    return [(ts, body) for ts, body in rows if not take(have, ts, body)]


def stream_keys(con, session_id):
    """How many times each event (time, text digest) is in the session's rrweb chunks."""
    return Counter(_key(ts, text) for ts, _, text in streams.read_events(con, session_id, [STREAM]))


def take(have, ts, text):
    """Whether stream_keys() still holds this event; if so it is used up, so identical rows count one by one."""
    key = _key(ts, text)
    if not have[key]:
        return False
    have[key] -= 1
    return True


def _key(ts, text):
    """What makes two replay events the same event: the time and a digest of the exact text (a digest, so that a
    session's every event fits in memory while it is compared)."""
    return ts, hashlib.sha256(text.encode("utf-8")).digest()
