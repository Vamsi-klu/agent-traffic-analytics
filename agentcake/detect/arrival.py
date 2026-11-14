"""How the pointer arrives at what it presses: a hand slows down into its target, a path generator that traces its
curve at an even or rising pace arrives at full speed. The model's session-level check fast_arrivals (model.py)
reads it, with raw input and a mouse only.

    judge(events, params) -> {"movements", "fast", "share", "holds", "span"} or None
    end_shares(events, params) -> [(start_ms, press_ms, end_share)] for each aimed movement

An aimed movement is the pointer's path before a mouse button goes down: its moves back to the first pause of join_ms
or more, the last move at most press_within_ms before the press, at least min_samples moves and min_px from where it
starts to where it ends; a press with no new move since the last one adds nothing. Its end share: the path is put on
a grid of grid_ms (the samples' positions interpolated, so a 15 ms sampler and a 25 ms one compare), and the mean
step over its last end_part of steps is divided by its largest step; a path of fewer than min_steps steps has none.
A hand that stops on a target slows down for its last part (the public human data sets' median movement ends at 7%
to 16% of its top speed); the movement arrives fast when its end share is at least fast_end_share. A session's
arrivals are evidence only with at least min_fast movements; the check holds when at least min_fast of them arrive
fast and they are at least fast_share_at_least of all (None, no evidence, with fewer movements: a short visit says
nothing).
One fast arrival says nothing (people make some), so the stretch the check covers is where the fast ones gather: the
run of consecutive movements that exceeds the check's own share the most (each fast one counts
1 - fast_share_at_least, each other one -fast_share_at_least, and the run is the one of largest sum, Kadane's scan),
from its first move to the click its last press made (the first click before the next press), so that click is in it.
A person's hand-off to a script gives the script's part; a script whose arrivals slow down now and then can leave
some of its own movements outside (measured: of the seven ghost-cursor sessions it names an agent, three are an Agent
and four a Human + agent).
Measured with agentcake eval and on the public human data sets: no person's session holds it, nor would at the next
looser value of either number (6 fast arrivals, or a share of 0.4).
"""
import bisect
import math


def end_shares(events, params):
    """(first move, press, end share) of each aimed movement that has an end share, in time order."""
    moves = [(e["t"], e["cx"], e["cy"]) for e in events if e.get("ty") == "mousemove" and e.get("cx") is not None]
    presses = [e["t"] for e in events if e.get("ty") == "mousedown"]
    out, j, last_used = [], 0, None
    for press in presses:
        while j < len(moves) and moves[j][0] <= press:
            j += 1
        end = j - 1
        if end < 0 or end == last_used or press - moves[end][0] > params["press_within_ms"]:
            continue
        last_used = end
        start = end
        while start > 0 and moves[start][0] - moves[start - 1][0] < params["join_ms"]:
            start -= 1
        path = moves[start:end + 1]
        if len(path) < params["min_samples"] or math.dist(path[0][1:], path[-1][1:]) < params["min_px"]:
            continue
        share = _end_share(path, params)
        if share is not None:
            out.append((path[0][0], press, share))
    return out


def judge(events, params):
    """The session's arrivals (see the module docstring): how many aimed movements, how many arrive fast, their share,
    whether the check holds, and the stretch where the fast ones gather [from, to]; None with fewer than min_fast."""
    found = end_shares(events, params)
    if len(found) < params["min_fast"]:
        return None
    fast = [share >= params["fast_end_share"] for _, _, share in found]
    share = sum(fast) / len(found)
    first, last = _densest(fast, 1 - params["fast_share_at_least"], -params["fast_share_at_least"])
    presses = sorted(e["t"] for e in events if e.get("ty") == "mousedown")
    clicks = sorted(e["t"] for e in events if e.get("ty") == "click")
    return {"movements": len(found), "fast": sum(fast), "share": share,
            "holds": sum(fast) >= params["min_fast"] and share >= params["fast_share_at_least"],
            "span": [found[first][0], _click_after(found[last][1], presses, clicks)]}


def _densest(fast, fast_weight, slow_weight):
    """(first, last) index of the maximum-sum run of consecutive movements, a fast one weighing fast_weight and any
    other slow_weight (Kadane's scan, starting anew only after a part of negative sum: of runs with the same sum, the
    last to end and the longest, so a slower movement between fast ones is in it)."""
    best, best_at, total, start = None, (0, 0), 0.0, 0
    for i, is_fast in enumerate(fast):
        if total < 0:
            total, start = 0.0, i
        total += fast_weight if is_fast else slow_weight
        if best is None or total >= best:
            best, best_at = total, (start, i)
    return best_at


def _click_after(press, presses, clicks):
    """The time of the click a press made: the first click from the press on, before the next press (the press's own
    time when it made none, as a drag does)."""
    after = bisect.bisect_right(presses, press)
    next_press = presses[after] if after < len(presses) else math.inf
    i = bisect.bisect_left(clicks, press)
    return clicks[i] if i < len(clicks) and clicks[i] < next_press else press


def _end_share(path, params):
    grid = _on_grid(path, params["grid_ms"])
    steps = [math.dist(a, b) for a, b in zip(grid, grid[1:])]
    if len(steps) < params["min_steps"] or max(steps) <= 0:
        return None
    last = steps[-max(1, int(len(steps) * params["end_part"])):]
    return sum(last) / len(last) / max(steps)


def _on_grid(path, grid_ms):
    """The path's positions every grid_ms from its first move to its last, linearly interpolated."""
    out, i, n = [], 0, 0
    t0, t1 = path[0][0], path[-1][0]
    while t0 + n * grid_ms <= t1:
        t = t0 + n * grid_ms
        while i + 1 < len(path) - 1 and path[i + 1][0] < t:  # stop at the last pair of samples
            i += 1
        (ta, xa, ya), (tb, xb, yb) = path[i], path[i + 1]
        f = 0.0 if tb == ta else min(max((t - ta) / (tb - ta), 0.0), 1.0)
        out.append((xa + f * (xb - xa), ya + f * (yb - ya)))
        n += 1
    return out
