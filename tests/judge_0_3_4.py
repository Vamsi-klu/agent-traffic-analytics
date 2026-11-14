"""cake 0.3.4's judge, kept with the tests as the reference agentcake/detect/timeline.py is checked against.

Nothing in Agent Cake runs it: the four-layer verdict (agentcake/detect/verdict.py, S3.4) took its place, and
timeline.py is its per-action half read from the raw-event format (S3.7). tests/test_timeline.py runs both on the same
input and expects the same numbers, and expects research note 12's results for this judge on the lab's rrweb
recordings. It was agentcake/detect/legacy.py (cake.py 0.3.4's judge, S1.1; its numbers in data/model.json, S1.2;
its User-Agent names from the bundled lists since S3.5) until the M3 clean-up moved it and its numbers here
(tests/fixtures/judge_0_3_4/model.json).

judge(ua, events, webdriver, srv, net) -> (source, group, verdict, shares, segments). The source comes from names in
the User-Agent, the automation flag, the server half's verdict and the published IP range; the shares come from a
per-action logistic model (rr_actions -> p_agent) smoothed over the session by a two-state HMM (hmm_smooth).
"""
import functools
import json
import math
import os
from collections import namedtuple

from agentcake.detect import lists
from agentcake.units import MS_PER_S, PERCENT

# rrweb's event format (rrweb 2.0.0-alpha.18, packages/types)
INCREMENTAL_SNAPSHOT = 3  # protocol: rrweb EventType.IncrementalSnapshot
MOUSE_MOVE, MOUSE_INTERACTION, INPUT = 1, 2, 5  # protocol: rrweb IncrementalSource MouseMove, MouseInteraction, Input
CLICK = 2  # protocol: rrweb MouseInteractions.Click
HUMAN, AGENT = 0, 1  # the session model's two hidden states
STATES = (HUMAN, AGENT)
Move = namedtuple("Move", "t x y")
MODEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "judge_0_3_4", "model.json")


@functools.lru_cache(maxsize=None)
def model():
    with open(MODEL_FILE, encoding="utf-8") as f:
        return json.load(f)


def rr_actions(ev):
    """rrweb events -> list of action segments with features (clicks, and typing bursts merged into one action)."""
    f = model()["features"]
    acts, moves = [], []
    t_prev_act = ev[0]["timestamp"] if ev else 0
    for e in ev:
        if e.get("type") != INCREMENTAL_SNAPSHOT:
            continue
        d = e.get("data") or {}; s = d.get("source"); t = e["timestamp"]
        if s == MOUSE_MOVE:
            for p in d.get("positions") or []:
                moves.append(Move(t + p.get("timeOffset", 0), p.get("x", 0), p.get("y", 0)))
        elif (s == MOUSE_INTERACTION and d.get("type") == CLICK) or s == INPUT:
            if s == INPUT and acts and acts[-1]["kind"] == "input" and t - acts[-1]["t"] < f["input_merge_ms"]:
                acts[-1]["t"] = t; continue
            win = [m for m in moves if t - f["move_window_ms"] <= m.t <= t]
            path = sum(math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(win, win[1:]))
            chord = math.hypot(win[-1].x - win[0].x, win[-1].y - win[0].y) if len(win) > 1 else 0
            span = max(1.0, (t - t_prev_act) / MS_PER_S)
            nmv = len([m for m in moves if t_prev_act <= m.t <= t])
            acts.append({"t": t, "kind": "click" if s == MOUSE_INTERACTION else "input",
                         "f": {"moves_per_s": min(nmv / span, f["max_moves_per_s"]),
                               "moves_before_act": min(len(win), f["max_moves_before_act"]),
                               "straight": (chord / path) if path > 0 and len(win) >= f["min_moves_for_straightness"] else 1.0,
                               "pause_s": min((t - t_prev_act) / MS_PER_S, f["max_pause_s"]),
                               "no_move_act": 1.0 if len(win) <= 1 else 0.0}})
            t_prev_act = t
    return acts


def p_agent(f):
    m = model()
    z = m["bias"] + sum(w * f[k] for k, w in m["weights"].items())
    return 1 / (1 + math.exp(-max(-m["logit_clamp"], min(m["logit_clamp"], z))))


def hmm_smooth(ps, switch=None, temper=None):
    """Forward-backward over the two states: each action's probability that the agent acted, given the whole session."""
    hmm = model()["hmm"]
    switch = hmm["switch"] if switch is None else switch
    temper = hmm["temper"] if temper is None else temper
    if not ps:
        return []
    T = [[1 - switch, switch], [switch, 1 - switch]]
    em = [[(1 - p) ** temper, p ** temper] for p in ps]  # state 0 human, 1 agent
    prior = 1 / len(STATES)
    fw = [[prior * em[0][HUMAN], prior * em[0][AGENT]]]
    for i in range(1, len(ps)):
        a = [sum(fw[-1][j] * T[j][k] for j in STATES) * em[i][k] for k in STATES]
        s = sum(a) or 1; fw.append([x / s for x in a])
    bw = [[1.0, 1.0]]
    for i in range(len(ps) - 1, 0, -1):
        b = [sum(T[k][j] * em[i][j] * bw[0][j] for j in STATES) for k in STATES]
        s = sum(b) or 1; bw.insert(0, [x / s for x in b])
    return [f[AGENT] * b[AGENT] / ((f[HUMAN] * b[HUMAN] + f[AGENT] * b[AGENT]) or 1) for f, b in zip(fw, bw)]


def judge(ua, ev, webdriver=False, srv=(), net=None):
    source, gid = "Not self-declared (browser, AI browser or extension)", "H1/L?"
    if webdriver:
        source, gid = "Automation-controlled browser (navigator.webdriver)", "D3?"
    # 0.3.3: the server half (botscent's server verdict on the page request) and the published range of the address
    for p in srv:
        bs = p.get("bs") or {}
        if bs.get("t") == "agent":
            source, gid = f"{bs.get('a') or 'Agent'} (server: botscent)", "server"; break
    if net and net.get("range_kind") == "agent":
        source, gid = f"{net['range']} (published IP range)", "range"
    named = _listed_name(ua)
    if named:
        source, gid = named["name"], named["kind"]
    acts = rr_actions(ev)
    post = hmm_smooth([p_agent(a["f"]) for a in acts])
    v = model()["verdict"]
    segs = []
    for a, p in zip(acts, post):
        who = "agent" if p >= v["agent_from_p"] else "human" if p <= v["human_up_to_p"] else "unsure"
        if segs and segs[-1]["who"] == who:
            segs[-1]["t1"] = a["t"]; segs[-1]["n"] += 1
        else:
            segs.append({"t0": a["t"], "t1": a["t"], "who": who, "n": 1, "p": round(p, v["p_decimals"])})
    n = len(acts)
    pct = {k: round(PERCENT * sum(s["n"] for s in segs if s["who"] == k) / n) if n else 0 for k in ("human", "agent", "unsure")}
    if not n:
        pct["unsure"] = PERCENT
    verdict = max(pct, key=pct.get)
    if verdict == "agent" and gid == "H1/L?":
        source, gid = "Agent, vendor not identified (no self-declared name)", "L?/V?"
    return source, gid, verdict, pct, segs


def _listed_name(ua):
    """The bundled lists' entry for the name a User-Agent declares; None for none, for several, or when the lists
    cannot be read (a broken install, which `agentcake lists` and doctor report; judging goes on without names)."""
    try:
        found = lists.current().match_ua(ua or "")
    except lists.ListsError:
        return None
    return found if found and found["id"] else None
