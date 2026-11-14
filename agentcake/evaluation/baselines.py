"""Whole-session models printed beside Agent Cake's own, never used to judge (plan step S3.9; research note 11).

    flags(events, raw_input, env, settings) -> {method: True (agent) | False | None (cannot tell)}
    table(rows, settings) -> {group: {method: {"n", "agent"}}}     how many sessions of each group each one flags

methods:
- cake: the behaviour model's own session verdict (model.judge_session; S3.7's main model, missing variant).
- rules_hmm: the lab's rules on each action segment smoothed by its HMM, an agent when at least half of the
  segments score 0.5 or more (compare_models.lab_rules_hmm), with no fallback.
- choudhary: Choudhary et al.'s original thresholds: mouse events per second over the input time, or clicks right
  after a jump (compare_models.choudhary). cake's fallback is its variant that counts only time spent moving.
- superline: @superline-ai/agent-detection 0.0.8's logistic model (MIT), on the page's environment when it was
  recorded and on three behaviour features (compare_models.superline).
- logistic: the lab's logistic regression on action segments (logistic.py), smoothed and decided like rules_hmm,
  trained without the session it judges: an agent session's whole lab group is left out (its runs repeat one
  script), a human session alone (logistic_flags). It needs both actors, so it runs only with clean recordings.

Ported from our own code with the same arithmetic: our research code's
compare_models.py (choudhary, superline, lab_rules_hmm; 2026-11-11). The logistic regression of that script trained
on public human data (CaptchaSolve30k, PSAI), which never enters Agent Cake: tables.py trains it here only on
clean recordings, when there are some. Settings: data/eval.json "baselines".
"""
import math
import statistics

from agentcake.detect import features, model, segment, timeline
from agentcake.evaluation import logistic
from agentcake.units import MS_PER_S

METHODS = ("cake", "rules_hmm", "choudhary", "superline", "logistic")
MOVE, CLICK, KEYDOWN = "mousemove", "click", "keydown"
SCROLLS = ("scroll", "wheel")


def flags(events, raw_input, env, settings, session_start=None):
    """Each method's call on one session (None when it cannot tell, e.g. no input at all)."""
    base = settings["baselines"]
    events = sorted(events, key=lambda e: e["t"])
    judged = model.judge_session(events, raw_input=raw_input, session_start=session_start)
    cake = None if judged["verdict"] == "too_little_data" else judged["verdict"] == "agent"
    return {"cake": cake, "rules_hmm": rules_hmm(events, raw_input, base["lab_rules_hmm"]),
            "choudhary": choudhary(events, base["choudhary"]), "superline": superline(events, env, base["superline"])}


def rules_hmm(events, raw_input, settings):
    """The lab's rules + HMM: the share of action segments whose smoothed score reaches agent_p."""
    segments = features.session_features(events, raw_input=raw_input)
    if not segments:
        return None
    smoothed = timeline.smooth([model.rule_score(s["features"])[0] for s in segments], model.load_params()["hmm"])
    return sum(1 for p in smoothed if p >= settings["agent_p"]) / len(smoothed) >= settings["share"]


def choudhary(events, settings):
    """Mouse events per second over the input time below rate_below, or teleport clicks above teleport_above."""
    inputs = segment.input_events(events)
    if not inputs:
        return None
    duration = max(settings["min_duration_s"], (inputs[-1]["t"] - inputs[0]["t"]) / MS_PER_S)
    moves = [e for e in events if e.get("ty") == MOVE]
    clicks = [e for e in events if e.get("ty") == CLICK]
    teleports = sum(1 for click in clicks if _teleport(click, moves, settings))
    ratio = teleports / len(clicks) if clicks else None
    return len(moves) / duration < settings["rate_below"] or (ratio is not None and ratio > settings["teleport_above"])


def _teleport(click, moves, settings):
    """compare_models.choudhary: no move before the click, or its last move right after a long jump."""
    before = [m for m in moves if m["t"] <= click["t"]]
    if not before:
        return True
    last = before[-1]
    earlier = [m for m in before if m["t"] < last["t"]]
    if click["t"] - last["t"] > settings["click_window_ms"]:
        return False
    if not earlier:
        return True
    jump = math.hypot(last["cx"] - earlier[-1]["cx"], last["cy"] - earlier[-1]["cy"])
    return last["t"] - earlier[-1]["t"] < settings["jump_ms"] and jump > settings["jump_px"]


def superline(events, env, settings):
    """superline's score >= threshold, skipping the environment features when the page's were not recorded."""
    times = sorted(e["t"] for e in events if e.get("ty") == MOVE)
    raw = {"keyboard_typing_consistency": _typing_consistency(events, settings),
           "has_active_mouse_movement": float(any(b - a < settings["active_move_gap_ms"]
                                                  for a, b in zip(times, times[1:]))),
           "has_scroll_events": float(any(e.get("ty") in SCROLLS for e in events)), "has_webgl_swiftshader": 0.0}
    raw.update(_environment(env or {}, settings))
    score = settings["bias"]
    for name, weight in settings["weights"].items():
        if name not in raw:
            continue  # superline skips a feature it could not read (agent-detector.js scoreFeatures)
        value = raw[name]
        if name in settings["normalise"]:
            mean, spread = settings["normalise"][name]
            value = (value - mean) / spread
        score += weight * value
    return 1 / (1 + math.exp(-score)) >= settings["threshold"]


def _environment(env, settings):
    """superline's browser features from the page's recorded environment; one the page did not record is left out
    (superline skips it), so a recording without the environment scores on behaviour alone."""
    out = {}
    for feature, key in settings["environment"].items():
        value = env.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[feature] = value
    renderer = (env.get("webgl") or {}).get("renderer")
    if renderer is not None:
        out["has_webgl_swiftshader"] = float(settings["swiftshader"] in str(renderer).lower())
    return out


def _typing_consistency(events, settings):
    """1 - the mean spread of the gaps between keys within typing bursts (no_typing without two keys)."""
    keys = sorted(e["t"] for e in events if e.get("ty") == KEYDOWN)
    bursts, current = [], keys[:1]
    for t in keys[1:]:
        if t - current[-1] > settings["key_burst_gap_ms"]:
            if len(current) > 1:
                bursts.append(current)
            current = [t]
        else:
            current.append(t)
    if len(current) > 1:
        bursts.append(current)
    if not bursts:
        return settings["no_typing"]
    spreads = []
    for burst in bursts:
        gaps = [b - a for a, b in zip(burst, burst[1:])]
        mean = statistics.mean(gaps)
        spreads.append((statistics.pstdev(gaps) if len(gaps) > 1 else 0) / mean if mean > 0 else 0)
    return 1 - min(statistics.mean(spreads), 1)


def logistic_flags(items, settings):
    """items: [(key, truth class, holdout group, raw events)] -> {key: flag}; {} without both actors."""
    seg, rule = settings["segments"], settings["baselines"]["lab_rules_hmm"]
    rows = {key: [{"who": "agent" if truth == "agent" else "human", "group": group,
                   "x": logistic.vector(s["features"], features.FEATURES, seg["logistic"]["log1p"])}
                  for s in features.session_features(raw)] for key, truth, group, raw in items}
    if {r["who"] for rs in rows.values() for r in rs} != {"agent", "human"}:
        return {}
    hmm, groups, models, out = model.load_params()["hmm"], {key: group for key, _, group, _ in items}, {}, {}
    for key, test in rows.items():
        if groups[key] not in models:
            train = [r for other, rs in rows.items() if groups[other] != groups[key] for r in rs]
            models[groups[key]] = logistic.fit([r["x"] for r in train], [r["who"] == "agent" for r in train],
                                               seg["logistic"])
        scores = timeline.smooth([logistic.predict(models[groups[key]], r["x"]) for r in test], hmm)
        out[key] = (sum(1 for p in scores if p >= rule["agent_p"]) / len(scores) >= rule["share"]) if scores else None
    return out


def table(rows):
    """rows: [{"group", "flags": {method: bool|None}}] -> per group and method: sessions it could tell, agents."""
    out = {}
    for r in rows:
        group = out.setdefault(r["group"], {m: {"n": 0, "agent": 0} for m in r["flags"]})
        for method, flag in r["flags"].items():
            cell = group.setdefault(method, {"n": 0, "agent": 0})
            if flag is not None:
                cell["n"] += 1
                cell["agent"] += bool(flag)
    return out
