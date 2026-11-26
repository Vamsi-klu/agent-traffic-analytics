"""The visitor's own actions among a session's raw events: what the All actions list shows, where a hand-off is and
what a stretch of the evaluation's splices spans, one definition for all of them (agentcake/data/actions.json says
which events and why).

    load() -> the definition: data/actions.json, read once
    found(events, definition=None) -> [(event, kind)]   the events that are actions, in time order, with their kind
                                                         ("click", "key", "type" or "scroll")
    times(events, definition=None) -> [t]               when each of them happened

events: dicts with at least "t" (ms) and "ty" (the raw event type), as cake.js's raw records and the recorder's are,
or as rrweb_events.py rebuilds them from a recording without raw input. A scroll event is an action only when one of
the visitor's own inputs (definition "caused_by") came at most "cause_ms" before it.
"""
import bisect

from agentcake import datafiles

DEFINITION_FILE = "data/actions.json"


def load():
    """The definition (agentcake/data/actions.json), read once. Shared: copy before changing."""
    return datafiles.load(DEFINITION_FILE)


def found(events, definition=None):
    """The events that are the visitor's actions, in time order, each with its kind (see the module docstring)."""
    definition = definition or load()
    kinds, needs_cause = definition["kinds"], set(definition["needs_cause"])
    events = sorted(events, key=lambda e: e["t"])
    causes = [e["t"] for e in events if e.get("ty") in definition["caused_by"]]
    out = []
    for event in events:
        kind = kinds.get(event.get("ty"))
        if kind is None or (event["ty"] in needs_cause and not _caused(causes, event["t"], definition["cause_ms"])):
            continue
        out.append((event, kind))
    return out


def times(events, definition=None):
    """When each of the visitor's actions happened, in order."""
    return [event["t"] for event, _ in found(events, definition)]


def _caused(causes, t, within_ms):
    """Whether one of the visitor's inputs (their times, in order) came at most within_ms before t."""
    last = bisect.bisect_right(causes, t) - 1
    return last >= 0 and t - causes[last] <= within_ms
