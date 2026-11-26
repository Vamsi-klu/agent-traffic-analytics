"""Which tab a session's replay shows at each moment while it follows the visitor: PostHog's segmenter.

A session with several tabs is replayed one tab at a time, as PostHog replays a recording of several windows: the
player follows the tab the visitor is active in, or stays on the one tab the owner picks (that tab's own replay, which
needs no schedule). This module makes the schedule the player follows.

Ported from PostHog's common/replay-shared/src/segmenter.ts (createSegments) in https://github.com/PostHog/posthog at
commit f7221a4aec3729a5a75b9d63557444255ba81b9d, MIT licence (THIRD_PARTY.md). Its rules, kept as they are:
  - the events of every window, in time order, are cut into segments of one window each; a segment starts with the
    first event, with an active event after a stretch without one, with any event once an active segment has had no
    active event for follow_activity_ms (data/api.json, PostHog's ACTIVITY_THRESHOLD_MS), with an active event from
    another window, and with the event after a window's last one;
  - the gap between two segments goes to the previous segment's window while that window's events span the gap's
    first moment, else to the first window whose events do (findWindowIdForTimestamp), else to no window;
  - the time before the first segment and after the last is covered by segments of no window.
Here PostHog's window is a tab session, and its events are the moments activity.times() gives (each page opened and
the visitor's input: the activity a session's clock counts, as PostHog's active sources are the visitor's input and a
page's snapshot) and the first and last moment its replay holds, which bound the tab's recording as a window's first
and last snapshot do. Not ported: the tracked window (a picked tab plays its own replay), mobile screenshot frames
(cake records web pages), the "buffer" kind for data still loading (the server holds it all) and durations.

    Event(t, tab, active)                        one moment of one tab, in epoch ms
    segments(events, start=None, end=None)       createSegments: [Segment(tab, start, end, active)]; tab None: none
    schedule(segments) -> [Stretch(tab, start, end)]   the tab the replay shows from start to end, every moment of the
                                                 segments covered once, neighbours of one tab joined; a stretch of no
                                                 window keeps the tab before it, as PostHog's player keeps the window
                                                 it shows (the first stretch takes the tab after it)
"""
from collections import namedtuple

from agentcake.api.answers import numbers

Event = namedtuple("Event", "t tab active")
Segment = namedtuple("Segment", "tab start end active")
Stretch = namedtuple("Stretch", "tab start end")


def segments(events, start=None, end=None):
    """The segments of events (any order: they are put in time order, ties kept in the order given), with the gaps
    between them and, when start and end are given, the stretches before the first and after the last."""
    ordered = sorted(events, key=lambda event: event.t)
    return _with_ends(_with_gaps(_windows(ordered), _ranges(ordered)), start, end)


def schedule(found):
    """The tab shown at each moment of found (segments()), see the module docstring. A segment of a single moment
    shows nothing, so it is no stretch of its own."""
    shown = []
    for index, segment in enumerate(found):
        tab = segment.tab
        if tab is None:
            tab = shown[-1].tab if shown else next((later.tab for later in found[index + 1:] if later.tab is not None),
                                                   None)
        start = shown[-1].end if shown else segment.start
        shown.append(Stretch(tab, start, max(start, segment.end)))
    out = []
    for stretch in [item for item in shown if item.end > item.start] or shown[:1]:
        if out and out[-1].tab == stretch.tab:
            out[-1] = out[-1]._replace(end=stretch.end)
        else:
            out.append(stretch)
    return out


def _windows(events):
    """createSegments' first pass: the window segments, in time order."""
    threshold = numbers()["follow_activity_ms"]
    last_of = {event.tab: index for index, event in enumerate(events)}  # each window's last event
    found, current, last_active = [], None, 0
    for index, event in enumerate(events):
        new = (current is None
               or (event.active and not current["active"])
               or (current["active"] and last_active + threshold < event.t)
               or (current["tab"] != event.tab and event.active)
               or (index > 0 and last_of[events[index - 1].tab] == index - 1))
        if event.active:
            last_active = event.t
        if new:
            if current is not None:
                found.append(Segment(**current))
            current = {"tab": event.tab, "start": event.t, "active": event.active}
        current["end"] = event.t
    if current is not None:
        found.append(Segment(**current))
    return found


def _ranges(events):
    """{tab: (first, last)}: the moments each window's events span, windows in the order they first appear."""
    ranges = {}
    for event in events:
        first, _ = ranges.get(event.tab, (event.t, event.t))
        ranges[event.tab] = (first, event.t)
    return ranges


def _window_at(t, ranges, preferred):
    """findWindowIdForTimestamp: the preferred window when its events span t, else the first that does, else None."""
    for tab in [preferred] + [tab for tab in ranges if tab != preferred]:
        if tab in ranges and ranges[tab][0] <= t <= ranges[tab][1]:
            return tab
    return None


def _with_gaps(found, ranges):
    """The segments with a gap segment wherever one does not begin where the one before it ended."""
    out = []
    for index, segment in enumerate(found):
        before = found[index - 1] if index else None
        if before is not None and segment.start != before.end:
            # the gap's first moment, offset by 1 ms as PostHog's is, so a window ending there does not take it
            out.append(Segment(_window_at(before.end + 1, ranges, before.tab), before.end, segment.start, False))
        out.append(segment)
    return out


def _with_ends(found, start, end):
    """The stretches of no window before the first segment and after the last (createSegments' start and end)."""
    if start is None or end is None:
        return found
    out = list(found)
    latest = out[-1].end if out else None
    if latest is None or latest < end:
        out.append(Segment(None, latest + 1 if latest is not None else start, end, False))
    if out and out[0].start > start:
        out.insert(0, Segment(None, start, out[0].start, False))
    return out
