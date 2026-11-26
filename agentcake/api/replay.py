"""A session's replay, read a chunk at a time (the session page's player): its ReplayInfo, and GET
.../replay?chunk=<n>&tab=<id>.

The replay is the session's rrweb stream (streams.py: sealed chunks and the windows still open). The player reads it
in chunks of storage.json's chunk_ms of event time, aligned as the stream's own windows are, so each event belongs to
exactly one chunk whether it is sealed, still open, or in the one archived chunk the night recompression made of a
whole session; a chunk is listed for each window the stream's chunks touch. Chunk n's events are the stream's events
of that window (streams.read_events reads only the chunks that touch it), each as rrweb recorded it.

    windows(con, session_id) -> [(window start, first event, last event)] in time order, epoch ms
    info(con, session_id, epoch, freed, dropped, c) -> ReplayInfo
    chunk(request, address_id) -> the answer to GET /api/session/<id>/replay?chunk=<n>&tab=<id>

A session spans its browser's tabs, and each tab session keeps its own stream: tab names the tab session
whose replay is read, one of the session's (tabs.py); without it, the tab an address from before sessions spanned
tabs named, else the session's first tab (a session of one tab: its only one). Every chunk's times are on the
session's clock (tabs.clock), so the player can move from one tab's replay to another's at the same moment.

missing says why the replay is gone or cut short: "freed" (freeing space removed it, space.py: the verdict, timeline
and server half stay), "dropped" (a full disk budget kept some events out), "none" (the visit sent no page events);
null when it is all there.
"""
import json
from http import HTTPStatus

from agentcake.api import answers, tabs, visits
from agentcake.session_replay import STREAM
from agentcake.storage_config import SETTINGS
from agentcake import streams

BLANK_PAGE = "about:blank"  # protocol: the address of a page that names none (WHATWG URL)


def windows(con, session_id):
    size, found = SETTINGS["chunk_ms"], {}
    for t_start, t_end in con.execute("SELECT t_start, t_end FROM chunks WHERE session_id=? AND stream=? UNION ALL "
                                      "SELECT t_start, t_end FROM open_chunks WHERE session_id=? AND stream=?",
                                      (session_id, STREAM, session_id, STREAM)):
        for window in range(t_start - t_start % size, t_end + 1, size):
            low, high = max(t_start, window), min(t_end, window + size - 1)
            if window in found:
                low, high = min(found[window][0], low), max(found[window][1], high)
            found[window] = (low, high)
    return [(window, low, high) for window, (low, high) in sorted(found.items())]


def info(con, session_id, epoch, freed, dropped, c):
    found = windows(con, session_id)
    chunks = [{"start_ms": max(0, low - epoch), "end_ms": max(0, high - epoch)} for _, low, high in found]
    missing = "freed" if freed else "dropped" if dropped else None if found else "none"
    return {"start_ms": chunks[0]["start_ms"] if chunks else 0, "start_url": _first_address(con, session_id),
            "epoch_ms": epoch, "handoff_lead_ms": c["handoff_lead_ms"], "chunks": chunks, "missing": missing}


def end(con, session_id):
    """The last replay event's time, or None."""
    found = windows(con, session_id)
    if not found:
        return None
    _, _, last = found[-1]
    return last


def chunk(request, address_id):
    number = (request.query.get("chunk") or [""])[0]
    if not (number.isascii() and number.isdigit()):
        raise answers.Refused(answers.error(HTTPStatus.BAD_REQUEST, "bad_count", field="chunk"))
    con = visits.connect()
    try:
        named = tabs.resolve(con, address_id)
        listed = tabs.parts(con, [named[0]]).get(named[0]) if named else None
        if not listed:
            return answers.error(HTTPStatus.NOT_FOUND, "no_session")
        ids = {part.id for part in listed}
        wanted = (request.query.get("tab") or [named[1] if named[1] in ids else listed[0].id])[0]
        if wanted not in ids:
            return answers.error(HTTPStatus.NOT_FOUND, "no_chunk")
        found = windows(con, wanted)
        if int(number) >= len(found):
            return answers.error(HTTPStatus.NOT_FOUND, "no_chunk")
        window, low, high = found[int(number)]
        epoch, _ = tabs.clock(listed)
        events = [_event(text) for _, _, text in
                  streams.read_events(con, wanted, [STREAM], window, window + SETTINGS["chunk_ms"] - 1)]
    finally:
        con.close()
    return answers.ok({"chunk": int(number), "start_ms": max(0, low - epoch), "end_ms": max(0, high - epoch),
                       "events": [event for event in events if event]})


def _event(text):
    """An rrweb event as the player reads it, or None for a record that is not one."""
    event = json.loads(text)
    if not (isinstance(event, dict) and isinstance(event.get("type"), int) and not isinstance(event["type"], bool)
            and isinstance(event.get("timestamp"), (int, float)) and isinstance(event.get("data"), dict)):
        return None
    return {"type": event["type"], "timestamp": round(event["timestamp"]), "data": event["data"]}


def _first_address(con, session_id):
    row = con.execute("SELECT url FROM batches WHERE session_id=? AND url IS NOT NULL ORDER BY t, seq LIMIT 1",
                      (session_id,)).fetchone()
    if row is None:
        row = con.execute("SELECT url FROM sessions WHERE id=?", (session_id,)).fetchone()
    return (row and row[0]) or BLANK_PAGE
