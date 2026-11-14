"""Spliced take-over sessions: real agent stretches and real human stretches on one time axis.

A splice cuts each source session's input timeline from its first input event (pattern lengths in seconds, each
source used from where its previous stretch ended), shifts the cuts one after the other with a gap between them and
keeps the truth: for each stretch, (first action, last action, who). The behaviour model never saw these sessions
together, so the splice tests where it puts the hand-offs and how it shares the actions out.

A stretch runs from its first action to its last, as the hand-off recorder counts one: an action as
agentcake/data/actions.json defines one for the whole of Agent Cake (visitor_actions.py: a click, a key or typed input,
a wheel, a scroll the visitor's own input caused, the events the timeline's hand-offs take too); moving the pointer is
none. A cut with no action is no stretch, so the splice is dropped, as the lab dropped a stretch that came out empty: a
source can run out of input while its page events go on (the lab's Claude in Chrome session cic-03 has 15 s of input and
90 s of page events), and the stretch cut from those had no one acting in it (22 of the 176 splices of recording_splices
had one).

Ported from our own lab code, the behaviour lab's analyze.py (cut, splice) and
splice.py (PATTERNS, build; 2026-11-11); patterns, gap and the shortest usable source come from
agentcake/data/splice.json. The lab's own truth (a stretch from its first input event to its last, or over all its
events when it has no input) is lab_truth(), which the lab's per-segment table (segments.py) keeps to reproduce the
lab's numbers. The lab spliced Claude in Chrome with Playwright scripts standing in for humans; here it is spliced with
humans (PostHog's probably-human replays now, our clean human recordings when they exist). Moved from the research
tools so that `agentcake eval` and the research tools share it.
"""
import json

from agentcake import datafiles
from agentcake.detect import segment, visitor_actions
from agentcake.units import MS_PER_S

PARAMS_FILE = "data/splice.json"


def load_params(path=None):
    """The splice parameters: the packaged data/splice.json, or another file (tests)."""
    if path is None:
        return datafiles.load(PARAMS_FILE)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def usable(events, params=None):
    """Whether a session has enough input to give every stretch of a pattern (the lab's > min_input_events)."""
    return len(segment.input_events(events)) > (params or load_params())["min_input_events"]


def build(agent_events, human_events, pattern, params=None, truth=None):
    """One splice of an agent's and a human's sessions by a pattern [(who, seconds), ...].

    Returns {"events", "truth": [(first action t, last action t, who)]}, or None when a stretch came out without an
    action (a source ran out of input), as the lab dropped those. truth(cut) gives the events a stretch spans
    (default: actions(), see the module docstring; lab_truth() is the lab's own).
    """
    params = params or load_params()
    parts, used = [], {"agent": 0.0, "human": 0.0}
    for who, seconds in pattern:
        source = agent_events if who == "agent" else human_events
        parts.append((source, used[who], used[who] + seconds, who))
        used[who] += seconds
    spliced = join(parts, params["gap_ms"], truth or actions())
    return spliced if len(spliced["truth"]) == len(pattern) else None


def join(parts, gap_ms, truth):
    """parts: [(events, from_s, to_s, who)], times relative to each source's first input event; truth(cut): the events
    of the cut its stretch spans, none for a cut that is no stretch."""
    events, stretches, t = [], [], 0.0
    for source, from_s, to_s, who in parts:
        first = segment.input_events(source)[0]["t"]
        cut = [dict(e) for e in source if first + from_s * MS_PER_S <= e["t"] < first + to_s * MS_PER_S]
        if not cut:
            continue
        shift = t - cut[0]["t"]
        for e in cut:
            e["t"] += shift
        events += cut
        spanned = truth(cut)
        if spanned:
            stretches.append((spanned[0]["t"], spanned[-1]["t"], who))
        t = cut[-1]["t"] + gap_ms
    return {"events": events, "truth": stretches}


def actions(definition=None):
    """truth() for build(): a cut's actions (visitor_actions.found(), data/actions.json), in their order."""
    return lambda cut: [event for event, _ in visitor_actions.found(cut, definition)]


def lab_truth(cut):
    """The lab's own truth (bh-lab-1111/splice.py): a cut's input events, or all of its events when it has none (page
    markers are no input)."""
    return segment.input_events(cut) or cut


def who_at(truth, t):
    """Who acted at t by the truth, or None in the gaps between stretches."""
    for start, end, who in truth:
        if start <= t <= end:
            return who
    return None


def boundaries(truth):
    """True hand-offs: (t, from, to) where the next stretch is the other actor's, at its first input."""
    return [(start, before, after) for (_, _, before), (start, _, after) in zip(truth, truth[1:]) if before != after]
