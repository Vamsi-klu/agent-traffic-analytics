"""Where the actor changed between a session's timeline runs: the hand-offs.

    handoffs(runs_, steps=(), action_times=None, logit_limit=None) -> [{"t", "from", "to", "after", "marker"?}]

Input: the runs timeline.build() made (consecutive steps with the same who), and from build() the steps themselves,
the times of the session's actions and the bound of a score's log-odds. A hand-off is where a decided run follows a
decided run of the other actor, at the new actor's first action: a click, a key or typed input, a wheel, a scroll
the visitor's own input caused; moving the pointer is none (visitor_actions.py: the actions Every action lists and the
splices' truth counts). Between the two runs, the steps the smoothing left unsure go to the side their own scores make
likeliest: one change point's maximum-likelihood position (D. V. Hinkley, "Inference about the change-point in a
sequence of random variables", Biometrika 57(1), 1970). On the spliced take-overs of `agentcake eval` it found the
most hand-offs within 3 s, without changing any step's who, beside the first decided step (the earlier rule), the
posterior's crossing of one half, an explicit-duration segmentation and online change-point detection (Adams and
MacKay 2007). Split from timeline.py, so that each module does one job.
"""
import bisect
import math


def handoffs(runs_, steps=(), action_times=None, logit_limit=None):
    """Where a decided run follows a decided run of the other actor; unsure runs in between are skipped. Next to a
    turn span, the indicator's moment: when it lit, for a hand-off to an agent run that began inside the span, or
    when it went off, for one from an agent run that ended inside it.

    timeline.build() also gives the steps runs_ was made of (in their order), the times of the session's actions
    (action_times: visitor_actions.times(), a click, a key or typed input, a wheel, a scroll the visitor caused) and
    timeline.logit_limit. Then a hand-off is where the new actor first acted: a run with no action of its own (the
    pointer moved, nothing more) is skipped like an unsure one, the steps between the two runs go to the side their own
    scores make likeliest (_likeliest_start), and the hand-off is the first action from there on. Without them (the
    runs a page stores, made-up runs) a hand-off is the new run's start.
    """
    if steps and logit_limit is None:
        raise ValueError("handoffs(): steps need the model's logit_limit (behavior_model.json timeline.logit_limit)")
    members = _members(runs_, steps) if steps else None
    out, previous, previous_index = [], None, None
    for index, run in enumerate(runs_):
        if run["who"] == "unsure" or (action_times is not None and not _acted(run, action_times)):
            continue
        if previous is not None and run["who"] != previous["who"]:
            t = run["start"]
            if members is not None:
                between = [step for group in members[previous_index + 1:index] for step in group]
                t = _likeliest_start(between, run, previous["who"], logit_limit)
            if action_times is not None:
                t = _first_action(action_times, t, previous["end"])
            handoff = {"t": t, "from": previous["who"], "to": run["who"], "after": previous["end"]}
            moment = run.get("lit") if run["who"] == "agent" else previous.get("off")
            if moment:
                handoff["marker"] = moment
            out.append(handoff)
        previous, previous_index = run, index
    return out


def _members(runs_, steps):
    """Each run's steps: runs() makes consecutive runs of the steps in their order, n steps each."""
    out, index = [], 0
    for run in runs_:
        out.append(steps[index:index + run["n"]])
        index += run["n"]
    return out


def _acted(run, action_times):
    """Whether an action happened between the run's start and its last step."""
    first = bisect.bisect_left(action_times, run["start"])
    return first < len(action_times) and action_times[first] <= run["end"]


def _likeliest_start(between, run, old, limit):
    """Where the new run's actor most likely began, given the steps between it and the previous decided run, which
    the smoothing left unsure (or which hold no action of their own): the first k of them stay with the old actor and
    the rest go to the new one, k the split that makes their own scores likeliest, the maximum-likelihood point of one
    change (Hinkley 1970), the earliest of equally likely splits. When all of them stay with the old actor the new run
    keeps its own start."""
    sign = 1 if old == "agent" else -1
    best_k, best, total = 0, 0.0, 0.0
    for k, step in enumerate(between, start=1):
        total += sign * _log_odds(step["score"], limit)
        if total > best:
            best_k, best = k, total
    if best_k == len(between):
        return run["start"]
    chosen = between[best_k]
    return chosen["first"] if run["who"] == "agent" else chosen["start"]


def _log_odds(score, limit):
    """A score's log-odds of an agent, kept within plus or minus limit (no step's score is a certainty)."""
    if score <= 0:
        return -limit
    if score >= 1:
        return limit
    return max(-limit, min(limit, math.log(score / (1 - score))))


def _first_action(action_times, t, after):
    """The first action at or after t and after the previous actor's last step (after); t when there is none."""
    index = bisect.bisect_left(action_times, t)
    while index < len(action_times) and action_times[index] <= after:
        index += 1
    return action_times[index] if index < len(action_times) else t
