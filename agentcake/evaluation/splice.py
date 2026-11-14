"""Spliced take-over sessions: real agent stretches and real human stretches on one time axis (plan step S3.7).

A splice cuts each source session's input timeline from its first input event (pattern lengths in seconds, each
source used from where its previous stretch ended), shifts the cuts one after the other with a gap between them and
keeps the truth: for each stretch, (first input, last input, who). The behaviour model never saw these sessions
together, so the splice tests where it puts the hand-offs and how it shares the actions out.

Ported from our own lab code, the behaviour lab's analyze.py (cut, splice) and
splice.py (PATTERNS, build; 2026-11-11), unchanged; patterns, gap and the shortest usable source come from
agentcake/data/splice.json. The lab spliced Claude in Chrome with Playwright scripts standing in for humans; S3.7
splices it with humans (PostHog's probably-human replays now, the clean recordings of S1.5 when they exist).
Moved from the research tools in S3.9, unchanged, so that `agentcake eval` and the research tools share it.
"""
import json

from agentcake import datafiles
from agentcake.detect import segment
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


def build(agent_events, human_events, pattern, params=None):
    """One splice of an agent's and a human's sessions by a pattern [(who, seconds), ...].

    Returns {"events", "truth": [(first input t, last input t, who)]}, or None when a stretch came out empty
    (a source ran out of input), as the lab dropped those.
    """
    params = params or load_params()
    parts, used = [], {"agent": 0.0, "human": 0.0}
    for who, seconds in pattern:
        source = agent_events if who == "agent" else human_events
        parts.append((source, used[who], used[who] + seconds, who))
        used[who] += seconds
    spliced = join(parts, params["gap_ms"])
    return spliced if len(spliced["truth"]) == len(pattern) else None


def join(parts, gap_ms):
    """parts: [(events, from_s, to_s, who)], times relative to each source's first input event."""
    events, truth, t = [], [], 0.0
    for source, from_s, to_s, who in parts:
        first = segment.input_events(source)[0]["t"]
        cut = [dict(e) for e in source if first + from_s * MS_PER_S <= e["t"] < first + to_s * MS_PER_S]
        if not cut:
            continue
        shift = t - cut[0]["t"]
        for e in cut:
            e["t"] += shift
        events += cut
        inputs = segment.input_events(cut) or cut  # page markers are no input: the truth spans the input only
        truth.append((inputs[0]["t"], inputs[-1]["t"], who))
        t = cut[-1]["t"] + gap_ms
    return {"events": events, "truth": truth}


def who_at(truth, t):
    """Who acted at t by the truth, or None in the gaps between stretches."""
    for start, end, who in truth:
        if start <= t <= end:
            return who
    return None


def boundaries(truth):
    """True hand-offs: (t, from, to) where the next stretch is the other actor's, at its first input."""
    return [(start, before, after) for (_, _, before), (start, _, after) in zip(truth, truth[1:]) if before != after]
