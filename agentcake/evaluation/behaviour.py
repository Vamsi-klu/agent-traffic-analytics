"""The behaviour model's tables on every dataset with known answers (thresholds A1–A5).

Each table function takes loaded data and returns {"rows": one per session, "summary": counts and medians}:
- lab(sessions): our lab's 26 agent sessions, each judged on its raw events and on its rrweb recording.
- posthog(units, groups): the units of tartini.ai's PostHog replays (probably human, and agent windows).
- mixed(replays): the 13 mixed replays among them, per action: the timeline (0.3.4's judge) and the main model's
  segments, truth by the agent windows.
- recordings(clean_humans): the clean human sessions we recorded, on raw events and on rrweb (threshold A1).
The lab sessions and the recordings are datasets.lab_sessions()' and datasets.recordings()', as `agentcake eval`
reads them.
- splices(agents, humans, ...): take-over sessions spliced from real agent and human stretches, both per-action
  methods, with hand-off errors.

Rows carry short hashes and lab run names only; agentcake.detect does the judging. Moved from
the research tools' behaviour_tables.py so that `agentcake eval` and the research tools share it.
"""
import collections
import statistics

from agentcake.detect import model, rrweb_events, timeline
from agentcake.evaluation import scoring, splice
from agentcake.evaluation.stats import median, tally
from agentcake.units import MS_PER_S, PERCENT

VERDICTS = ("agent", "human", "unsure", "too_little_data")


def lab(sessions):
    """sessions: datasets.lab_sessions() (the lab's sessions). Groups by the lab's own three (segment_group)."""
    rows = []
    for run, session in sessions.items():
        rrweb = session["rrweb"]
        rows.append({"run": run, "group": session["segment_group"],
                     "raw": brief(model.judge_session(session["raw"], raw_input=True)),
                     "rrweb": brief(model.judge_session(rrweb_events.events_from_rrweb(rrweb), raw_input=False,
                                                        session_start=rrweb[0]["timestamp"]))})
    summary = {}
    for recording in ("raw", "rrweb"):
        for group, members in _by(rows, "group").items():
            summary[f"{group} / {recording}"] = _verdict_counts([r[recording] for r in members])
    return {"rows": rows, "summary": summary}


def posthog(units, groups):
    """units: posthog_data.units(); groups: posthog group rules (the research tools' own)."""
    rows = []
    for unit in units:
        start = unit["rrweb"][0]["timestamp"] - unit["start_ms"] if unit["rrweb"] else None
        result = model.judge_session(unit["events"], raw_input=False, touch=unit["touch"], session_start=start)
        rows.append({"h": unit["h"], "group": posthog_group(unit, groups), "label": unit["label"],
                     "touch": unit["touch"], **brief(result)})
    summary = {group: _verdict_counts(members) for group, members in _by(rows, "group").items()}
    return {"rows": rows, "summary": summary}


def mixed(replays):
    """replays: posthog_data.mixed_replays(). Truth: inside an agent window or not, by the action's time."""
    rows = []
    for replay in replays:
        result = model.judge_session(replay["events"], raw_input=False, session_start=replay["first_rrweb_t"])
        actions = result["timeline"]["actions"]
        segments = result["segments"]
        rows.append({"session": replay["h"], "verdict": result["verdict"],
                     "timeline": scoring.action_scores([a["who"] for a in actions],
                                                       [_truth(replay, a["t"]) for a in actions]),
                     "segments": scoring.action_scores([s["who"] for s in segments],
                                                       [_truth(replay, s["act_t"]) for s in segments])})
    return {"rows": rows, "summary": {method: _action_summary([r[method] for r in rows])
                                      for method in ("timeline", "segments")}}


def recordings(clean_humans):
    """clean_humans: datasets.recordings(), the recorder's clean human sessions (threshold A1), judged both ways."""
    rows = []
    for human in clean_humans:
        rrweb = human["rrweb"]
        start = rrweb[0]["timestamp"] if rrweb else None
        rows.append({"h": human["h"], "raw": brief(model.judge_session(human["raw"], raw_input=True)),
                     "rrweb": brief(model.judge_session(rrweb_events.events_from_rrweb(rrweb), raw_input=False,
                                                        session_start=start))})
    return {"rows": rows, "summary": {recording: _verdict_counts([r[recording] for r in rows])
                                      for recording in ("raw", "rrweb")}}


def splices(agents, humans, params, raw_input, handoff_limit_s):
    """agents, humans: [(name, events)]; every agent with every human by every pattern of params."""
    rows = [{"agent": agent, "human": human, "pattern": pattern, **_splice_row(spliced, raw_input)}
            for agent, human, pattern, spliced in splice.each(agents, humans, params)]
    judged = [r for r in rows if r["verdict"] != "too_little_data"]
    summary = {"splices": len(rows), "judged": len(judged), "verdicts": tally(r["verdict"] for r in rows),
               "agent_or_mixed": sum(1 for r in judged if r["verdict"] == "agent" or r["timeline_handoffs"]),
               "all": _splice_summary(judged, handoff_limit_s),
               "every_stretch_has_an_action": _splice_summary([r for r in judged if r["every_stretch_has_an_action"]],
                                                              handoff_limit_s)}
    summary["by_pattern"] = {name: {"splices": len(members),
                                    "timeline_share_error_pp_median": median(
                                        [m["timeline"]["share_error_pp"] for m in members]),
                                    "timeline_handoff_error_s_median": median(
                                        [e for m in members for e in m["timeline_handoff_errors_s"]])}
                             for name, members in _by(judged, "pattern").items()}
    return {"rows": rows, "summary": summary}


def brief(result):
    """The parts of a judge_session() result a table keeps."""
    line = result["timeline"]
    shares = line["shares"] if line else None
    return {"verdict": result["verdict"], "confidence": result["confidence"], "basis": result["basis"],
            "n_actions": result["n_actions"], "timeline_shares": shares,
            "timeline_majority": _majority(shares) if shares else None,
            "timeline_handoffs": len(line["handoffs"]) if line else 0}


def validation_sessions(units, mixed_replays, groups, agent_group):
    """Short hashes of the held-out sessions: those of the mixed replays and of every unit of agent_group."""
    return {replay["h"] for replay in mixed_replays} | \
        {unit["session"] for unit in units if posthog_group(unit, groups) == agent_group}


def posthog_group(unit, groups):
    """The PostHog study's groups: the unit's own group when the dataset names one, else the kind of agent from the unit's kt
    or reason; the probably-human group for people. In the PostHog training set the units the user labelled are a group of
    their own, and so are the site owner's presumed humans (weak answers: settings "untrusted")."""
    strength = unit.get("truth_strength")  # the training set says how each answer is known; the first dataset not
    if unit.get("pending") and "pending" in groups:  # a label the user has yet to confirm
        return groups["pending"]
    if strength is not None and strength == groups.get("user_strength"):
        return groups["user_labelled"]
    if unit["label"] != "agent":
        weak = unit.get("owner") and strength in (groups.get("untrusted") or {}).get("owner_strengths", ())
        return groups["owner_presumed"] if weak else (unit["group"] or unit["label"])
    if unit.get("group"):  # a dataset that names each agent unit's group (the PostHog training set) keeps it
        return unit["group"]
    if unit["reason"] in groups["by_reason"]:
        return groups["by_reason"][unit["reason"]]
    kt = unit["unit_id"].split(":", 1)[-1].split("#")[0]
    return next((group for part, group in groups["by_kt_part"].items() if part in kt), groups["other_agent"])


def _splice_row(spliced, raw_input):
    truth = spliced["truth"]
    result = model.judge_session(spliced["events"], raw_input=raw_input)
    row = {"verdict": result["verdict"], "truth_agent_s": _truth_seconds(truth)}
    if result["verdict"] == "too_little_data":
        return row
    true_handoffs = splice.boundaries(truth)
    actions = [(a, splice.who_at(truth, a["t"])) for a in result["timeline"]["actions"]]
    segments = [(s, splice.who_at(truth, s["act_t"])) for s in result["segments"]]
    segment_runs = timeline.runs([{"t": s["end"], "first": s["act_t"], "start": s["start"], "who": s["who"],
                                   "p": s["p"]} for s in result["segments"]])
    row["every_stretch_has_an_action"] = all(any(start <= a["t"] <= end for a, _ in actions)
                                             for start, end, _ in truth)
    for method, items, handoffs in (("timeline", actions, result["timeline"]["handoffs"]),
                                    ("segments", segments, timeline.handoffs(segment_runs))):
        predicted = [(h["t"], h["from"], h["to"]) for h in handoffs]
        kept = [(item, who) for item, who in items if who is not None]
        row[method] = scoring.action_scores([item["who"] for item, _ in kept], [who for _, who in kept])
        row[method + "_handoff_errors_s"], row[method + "_handoffs_extra"] = scoring.handoff_errors(
            predicted, true_handoffs)
    row["timeline_handoffs"] = len(result["timeline"]["handoffs"])
    return row


def _splice_summary(rows, handoff_limit_s):
    """Per method: the per-action scores and the hand-off errors of the splices in rows."""
    summary = {"splices": len(rows)}
    for method in ("timeline", "segments"):
        errors = [e for r in rows for e in r[method + "_handoff_errors_s"]]
        summary[method] = {**_action_summary([r[method] for r in rows]),
                           "handoff_error_s": scoring.summary(errors), "handoffs_true": len(errors),
                           "handoffs_missed": sum(1 for e in errors if e is None),
                           "handoffs_within_limit": scoring.share_within(errors, handoff_limit_s),
                           "handoffs_extra": sum(r[method + "_handoffs_extra"] for r in rows)}
    return summary


def _action_summary(scores):
    scores = [s for s in scores if s["n"]]
    return {"sessions": len(scores), "actions": sum(s["n"] for s in scores),
            "accuracy_decided": scoring.summary([s["accuracy_decided"] for s in scores]),
            "accuracy_all_mean": _mean([s["accuracy_all"] for s in scores]),
            "share_error_pp": scoring.summary([s["share_error_pp"] for s in scores]),
            "unsure_share_median": median([s["unsure_share"] for s in scores])}


def _verdict_counts(results):
    counts = tally(r["verdict"] for r in results)
    judged = [r for r in results if r["verdict"] != "too_little_data"]
    return {"units": len(results), **{v: counts.get(v, 0) for v in VERDICTS},
            "agent_or_mixed": sum(1 for r in judged if r["verdict"] == "agent" or r["timeline_handoffs"]),
            "timeline_majority_agent": sum(1 for r in judged if r["timeline_majority"] == "agent")}


def _majority(shares):
    """0.3.4's session verdict from the timeline: the largest rounded percentage (human, agent, unsure order)."""
    pct = {who: round(PERCENT * share) for who, share in shares.items()}
    return max(timeline.WHO, key=lambda who: pct[who])


def _truth(replay, t):
    return "agent" if replay["agent_at"](t) else "human"


def _truth_seconds(truth):
    return sum(end - start for start, end, who in truth if who == "agent") / MS_PER_S


def _by(rows, key):
    out = collections.OrderedDict()
    for row in rows:
        out.setdefault(row[key], []).append(row)
    return out


def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None
