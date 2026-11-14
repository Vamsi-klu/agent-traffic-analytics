"""Reading the data sets `agentcake eval` measures on (plan step S3.9). Every reader only reads; none writes a file.

    lab_sessions(path, settings) -> {run: lab session}      our lab's sessions: label, raw events, rrweb events
    lab_signals(path, settings) -> [labelled signals]       the lab's environment signals of 2026-11-09 and 11-11
    cakejs_uploads(folder) -> {name: [{"headers", "batch"}]}   real cake.js uploads of automated browsers
    recordings(folder, truth_path, settings) -> [clean human recording]   the S1.5 recorder's sessions in truth_manual
    recorded(folder, truth_path, settings) -> [agent or hand-off recording]   the same folder's sessions in
                                                            truth_recordings (the data-collection kit), or a
                                                            recorder copy's in the list of our own runs (S9.4)
    posthog(folder, settings) -> {"units", "mixed"}          S1.5's local PostHog dataset and its mixed replays
    named_user_agents(path) -> [case]                       GOAL A7's 10 User-Agents and their answers
    motion_attestation(path) -> [public human]              motion-attestation's 27 captures (tests/fixtures, MIT)
    public_humans(path) -> [public human]                   PSAI and CaptchaSolve30k sessions, converted on this
                                                            computer by the maintainers' converter
    jsonl(path) -> [row]                                    a sample list (truth_goal.jsonl and the like)
    short_hash(prefix, text, settings) -> 12 hex digits     how the sample lists name sessions (eval/README.md)

A public human: {"h", "set", "site", "touch", "events"}: a real person's session from a public data set, in the
raw-event format, never committed except motion-attestation's fixture; the scoreboard counts them as humans (D36), the
gate never does (GOAL T12: A1 counts our own clean recordings only). A lab session: {"gt", "group", "segment_group",
"class", "row", "raw", "rrweb"}, the group and the answer coming from data/eval.json "lab". A recording: {"h", "raw",
"rrweb", "payloads", "requests"}: the lab collectors' reports in arrival order and the recorder server's log rows of the
run, which env_signals.from_lab reads, up to its line's until_ms when it has one (the recorder's 我做完了 plus its
grace: what reached the recorder later was left out of its verdict, eval/README.md); an agent's or a hand-off's adds its
answer: "label", "truth", "mode", "task" and "stretches" [(from_ms, to_ms, who)]. A PostHog unit is S1.5's units/<h>.json with "start" (where its first rrweb
event lies, ms after the session start) and "session" (its session's short hash). A mixed replay rebuilds one of the
site owner's sessions from its units: the events of all of them, and "agent_at" (t -> whether t lies in one of its
agent units), as research note 12 scored them per action.
"""
import gzip
import hashlib
import json
import os

from agentcake.detect import segment, timeline

RAW, RRWEB = "raw", "rrweb"  # the lab collectors' report kinds (lab/static/raw.js)
TOUCH_MOVE = "touchmove"  # the one interaction PostHog's minimal rrweb has no event for (rrweb_events.py)
MOTION_ATTESTATION = "motion-attestation"  # the data set's name and its site (one widget page)
TOUCH = "touch"  # a motion-attestation capture's device: a phone or a tablet


def short_hash(prefix, text, settings):
    return hashlib.sha256((prefix + text).encode("utf-8")).hexdigest()[:settings["short_hash"]["hex"]]


def jsonl(path):
    """The rows of a JSON-lines file; [] when there is no such file."""
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def lab_group(gt, settings):
    """The lab entry of data/eval.json "lab.groups" whose prefix the label starts with (else other automation)."""
    lab = settings["lab"]
    entry = next((g for g in lab["groups"] if (gt or "").startswith(g["prefix"])), None)
    if entry is None:
        other = lab["other_automation"]
        return {"group": gt or other["group"], "segment_group": gt, "class": other["class"], "row": other["row"]}
    return entry


def lab_sessions(path, settings):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        runs = json.load(f)["runs"]
    out = {}
    for run, session in runs.items():
        entry = lab_group(session["gt"], settings)
        out[run] = {"gt": session["gt"], "group": entry["group"], "segment_group": entry["segment_group"],
                    "class": entry["class"], "row": entry["row"],
                    "raw": sorted(session["raw"], key=lambda e: e["t"]),
                    "rrweb": sorted(session["rrweb"], key=lambda e: e.get("timestamp", 0))}
    return out


def lab_signals(path, settings):
    """[{"id", "set", "group", "truth", "class", "row", "signals"}]: answers by the truth label (data/eval.json)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        sessions = json.load(f)["sessions"]
    out = []
    for session in sessions:
        entry = lab_group(session["truth"], settings)
        out.append({"id": session["id"], "set": session["set"], "group": entry["group"], "truth": session["truth"],
                    "class": entry["class"], "row": entry["row"], "signals": session["signals"]})
    return out


def cakejs_uploads(folder):
    out = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith(".ndjson.gz"):
            with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as f:
                out[name[:-len(".ndjson.gz")]] = [json.loads(line) for line in f if line.strip()]
    return out


def recordings(folder, truth_path, settings):
    """The clean human recordings the clean recordings' list names, found in the recorder's data folder by their hash, each
    with the site its line names (the scoreboard counts per site)."""
    lines = {row["h"]: row for row in jsonl(truth_path) if row.get("truth") == settings["truth"]["human"]}
    return [{**item, "site": lines[item["h"]].get("site")}
            for item in _recorder_sessions(folder, _cutoffs(lines), settings)]


def recorded(folder, truth_path, settings):
    """The agent and hand-off recordings the recordings' list names, found in the same folder by their hash, each
    with its line's answer: label, truth (agent or mixed), mode, task, and a hand-off's stretches. The recordings we
    ran ourselves (S9.4) are read the same way from their own folder and list; a line may name its variant (the model
    that drove the agent, or the mouse algorithm)."""
    words = settings["truth"]
    lines = {row["h"]: row for row in jsonl(truth_path) if row.get("truth") in (words["agent"], words["mixed"])}
    out = []
    for item in _recorder_sessions(folder, _cutoffs(lines), settings):
        line = lines[item["h"]]
        out.append({**item, "label": line.get("label"), "truth": line["truth"], "mode": line.get("mode"),
                    "task": line.get("task"), "site": line.get("site"), "variant": line.get("variant"),
                    "stretches": [tuple(s) for s in line.get("stretches") or []]})
    return out


def _cutoffs(lines):
    """{h: the line's until_ms, or None to read the whole recording}."""
    return {h: line.get("until_ms") for h, line in lines.items()}


def _recorder_sessions(folder, wanted, settings):
    """[{"h", "raw", "rrweb", "payloads", "requests"}] of the recorder's sessions whose hash is wanted ({h: until_ms or
    None}): the reports (srv_ts) and server rows (ts) that reached the recorder by until_ms, or all of them."""
    sessions_dir = os.path.join(folder, "sessions")
    if not wanted or not os.path.isdir(sessions_dir):
        return []
    server = jsonl(os.path.join(folder, "logs", "server.jsonl"))
    out = []
    for name in sorted(os.listdir(sessions_dir)):
        run = name.rsplit(".", 1)[0]
        h = short_hash(settings["short_hash"]["recording"], run, settings)
        if h in wanted:
            until = wanted[h]
            payloads = [row.get("data") or {} for row in jsonl(os.path.join(sessions_dir, name))
                        if _received_by(row.get("srv_ts"), until)]
            raw, rrweb = _streams(payloads)
            out.append({"h": h, "raw": raw, "rrweb": rrweb, "payloads": payloads,
                        "requests": [r for r in server if r.get("run") == run and _received_by(r.get("ts"), until)]})
    return out


def _received_by(t, until):
    """Whether a report or server row the recorder stamped at t (ms) is read: every one without a cutoff; one without
    a time cannot be placed, so it is kept."""
    return until is None or not isinstance(t, (int, float)) or t <= until


def _streams(payloads):
    """(raw events tagged with their page, rrweb events) of one lab-collector session, each in time order."""
    raw, rrweb = [], []
    for report in payloads:
        if report.get("kind") == RAW:
            raw.extend({**item, "pg": report.get("page")} for item in report.get("items") or [])
        elif report.get("kind") == RRWEB:
            rrweb.extend(report.get("items") or [])
    return sorted(raw, key=lambda e: e["t"]), sorted(rrweb, key=lambda e: e.get("timestamp", 0))


def posthog(folder, settings):
    """S1.5's units (index order) and the mixed replays rebuilt from them."""
    ph = settings["posthog"]
    units = []
    for row in jsonl(os.path.join(folder, ph["index"])):
        with open(os.path.join(folder, ph["units"], row["h"] + ".json"), encoding="utf-8") as f:
            unit = json.load(f)
        events = sorted(unit["events"], key=lambda e: e["t"])
        visible = [e["t"] for e in events if e.get("ty") != TOUCH_MOVE]
        units.append({**unit, "events": events, "touch": bool((unit.get("device") or {}).get("touch")),
                      "session": short_hash(settings["short_hash"]["posthog"], unit["session_h"], settings),
                      "start": min(visible) if visible and unit.get("rrweb") else None})
    return {"units": units, "mixed": mixed_replays(units, settings)}


def mixed_replays(units, settings):
    """The site owner's sessions an agent drove part of (cake-ph-eval/mixed_eval.py): every unit's events joined,
    kept when they hold at least min_actions action segments, some inside the agent units and some outside."""
    ph, minimum = settings["posthog"], timeline.load_params()["min_actions"]
    by_session = {}
    for unit in units:
        by_session.setdefault(unit["session"], []).append(unit)
    out = []
    for session, members in by_session.items():
        if not any(u["group"] == ph["owner_group"] for u in members):
            continue
        spans = [(min(e["t"] for e in u["events"]), max(e["t"] for e in u["events"])) for u in members
                 if u["label"] == ph["labels"]["agent"] and u["events"]]
        if not spans:
            continue
        events = sorted((e for u in members for e in u["events"]), key=lambda e: e["t"])
        actions = segment.actions(events)
        if len(actions) < minimum or {_inside(spans, s["act_t"]) for s in actions} != {True, False}:
            continue
        starts = [u["start"] for u in members if u["start"] is not None]
        out.append({"h": session, "events": events, "first_rrweb_t": min(starts) if starts else None,
                    "agent_at": lambda t, spans=spans: _inside(spans, t)})
    return out


def named_user_agents(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["cases"]


def motion_attestation(path):
    """tests/fixtures/motion_attestation/humans.json (tests/motion_attestation.py): each capture as a public human."""
    with open(path, encoding="utf-8") as f:
        captures = json.load(f)["captures"]
    return [{"h": c["name"], "set": MOTION_ATTESTATION, "site": MOTION_ATTESTATION, "touch": c["device"] == TOUCH,
             "events": sorted(c["raw"], key=lambda e: e["t"])} for c in captures]


def public_humans(path):
    """The local file of the converted public human data sets: one public human per line (gzip JSON lines)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    return [{**item, "events": sorted(item["events"], key=lambda e: e["t"])} for item in items]


def _inside(spans, t):
    return any(start <= t <= end for start, end in spans)
