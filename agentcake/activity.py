"""When a session's recorded activity began and ended: what a session's length is made of.

A session's length runs from its first to its last recorded activity. Activity is a page the visitor opened (cake.js's
page record, or the rrweb Meta event of a cake 0.3.x recording) or the visitor's own input: pointer, keys, wheel or
touch (detect/segment.py's INPUT_TYPES; detect/rrweb_events.py rebuilds them from a 0.3.x recording). Records of
anything else (focus, visibility, window geometry, elements added to the page, the page leaving, page mutations) move
neither end, so a tab left open after the last activity adds nothing to the length (as the owner worded the measure;
later PostHog web analytics' "Session duration" is also first to last event).

Activity is wider than an action as the Every action list, its shares and the hand-offs count one (data/actions.json,
detect/visitor_actions.py): pointer movement and every scroll move a session's ends, though they are no action.

    span(raw, rrweb, page_starts) -> (first, last) in epoch ms on the events' clock, or (None, None)
    page_starts(con, session_id) -> when each page record of the session's signals stream was made, oldest first

judging.py keeps the span in sessions.first_action_ms and last_action_ms with every verdict, so the dashboard's
averages are a query (agentcake/api/visits.py) instead of a read of every session's events.
"""
import json

from agentcake import streams
from agentcake.detect import rrweb_events
from agentcake.detect.segment import INPUT_TYPES

SIGNALS_STREAM = "env"
PAGE_RECORD = "page"  # protocol: the record cake.js sends when a page view begins (cake_main.js)
PAGE_MARK = '"ty":"page"'  # how a page record's JSON text says so; other records are not parsed


def span(raw, rrweb, page_starts):
    """(first, last) recorded action: the page starts, and the visitor's input in raw (cake.js's raw records) or,
    for a recording without them, in rrweb."""
    times = list(page_starts)
    if raw:
        times += [record["t"] for record in raw if record.get("ty") in INPUT_TYPES]
    elif rrweb:
        times += [event["timestamp"] for event in rrweb if event.get("type") == rrweb_events.META]
        times += [event["t"] for event in rrweb_events.events_from_rrweb(rrweb) if event.get("ty") in INPUT_TYPES]
    if not times:
        return None, None
    return round(min(times)), round(max(times))


def page_starts(con, session_id):
    """When each page view of the session began: the times of its page records, oldest first."""
    starts = []
    for _, _, text in streams.read_events(con, session_id, [SIGNALS_STREAM]):
        if PAGE_MARK not in text.replace(" ", ""):
            continue
        record = json.loads(text)
        if record.get("ty") == PAGE_RECORD and isinstance(record.get("t"), (int, float)):
            starts.append(round(record["t"]))
    return starts
