"""The lab's per-segment test (its segment-level accuracy) on our behaviour lab's sessions and on its splices.

    single_source(sessions, settings) -> rows     each lab group, mode and method: segments judged right
    splices(sessions, settings, with_logistic) -> rows    the lab's 160 splices: accuracy, shares, switch errors

A session is cut into one-second windows (win) or action segments (act), each segment scored by the lab's rules
(model.rule_score), by the lab's logistic regression (logistic.py, trained on the other sessions, only when they
hold both actors), and by both smoothed with the lab's HMM. The splices join a Claude in Chrome session with a
human-like Playwright script standing in for the human: they show whether cutting and smoothing work, not how well
humans are judged (our study of PostHog replays and the lab both found so). Sessions: {run: {"group", "segment_group", "events"}}.

Ported from our own code with the same arithmetic, so the rows equal the lab's
bh-lab.eval.jsonl (the behaviour lab's analyze.py seg_dataset, evaluate, acc,
shares_of; splice.py predict, switch_errors; make_eval.py; 2026-11-11). Settings: data/eval.json "segments", "lab".
"""
import statistics

from agentcake.detect import features, model, segment, timeline
from agentcake.evaluation import logistic, splice
from agentcake.units import MS_PER_S, PERCENT

MODES = ("win", "act")
METHODS = ("rules", "rules_hmm", "logistic", "logistic_hmm")
MEASURES = ("time", "actions", "events")
WHO = ("human", "agent")


def dataset(events, truth, mode, settings):
    """analyze.seg_dataset: the segments of a session with their features, answer, time weight and event count."""
    rows = []
    if mode == "win":
        previous = None
        for window in segment.windows(events, {"window_ms": settings["window_ms"]}):
            values = features.segment_features(window["events"], events, previous)
            previous = window["events"][-1]["t"]
            middle = statistics.fmean((window["events"][0]["t"], window["events"][-1]["t"]))
            rows.append({"start": window["start"], "end": window["end"], "who": splice.who_at(truth, middle),
                         "features": values, "n_events": len(window["events"]), "active_ms": settings["window_ms"]})
    else:
        for seg in features.session_features(events):
            wall = (seg["end"] - rows[-1]["end"]) if rows else (seg["end"] - seg["start"])
            rows.append({"start": seg["start"], "end": seg["end"], "who": splice.who_at(truth, seg["act_t"]),
                         "features": seg["features"], "n_events": len(seg["events"]),
                         "active_ms": max(settings["min_action_ms"], wall)})
    return [row for row in rows if row["who"] in WHO]


def lab_rules():
    """The packaged parameters with the lab's rules only: cake's own (marked since) are measured by the
    scoreboard, while this table reproduces the lab's published numbers."""
    params = dict(model.load_params())
    params["rules"] = {**params["rules"], "list": [r for r in params["rules"]["list"] if "since" not in r]}
    return params


def score(rows, lr_model, settings):
    """Each row's p for every method; the smoothed ones only when every row has the unsmoothed score."""
    params = lab_rules()
    hmm = params["hmm"]
    for row in rows:
        row["rules"] = model.rule_score(row["features"], params)[0]
        row["logistic"] = logistic.predict(lr_model, _vector(row, settings)) if lr_model else None
    for key in ("rules", "logistic"):
        if rows and all(row[key] is not None for row in rows):
            for row, p in zip(rows, timeline.smooth([row[key] for row in rows], hmm)):
                row[key + "_hmm"] = p
    return rows


def train(rows, settings):
    """The logistic model of the training rows, or None when they do not hold both actors."""
    if {row["who"] for row in rows} != set(WHO):
        return None
    return logistic.fit([_vector(row, settings) for row in rows], [1 if row["who"] == "agent" else 0 for row in rows],
                        settings["logistic"])


def _vector(row, settings):
    """The row's logistic-regression input, made once (a splice's training rows are reused 4 times per mode)."""
    if "x" not in row:
        row["x"] = logistic.vector(row["features"], features.FEATURES, settings["logistic"]["log1p"])
    return row["x"]


def accuracy(rows, key, settings):
    """analyze.acc: segments right, unsure, and the accuracy over all and over the decided ones."""
    labels = [(_label(row[key], settings), row["who"]) for row in rows if row.get(key) is not None]
    unsure = sum(1 for said, _ in labels if said == "unsure")
    right = sum(1 for said, true in labels if said == true)
    digits = settings["round_accuracy"]
    decided = len(labels) - unsure
    return {"n": len(labels), "correct": right, "unsure": unsure,
            "acc_decided": round(right / decided, digits) if decided else None,
            "acc_all": round(right / len(labels), digits) if labels else None}


def single_source(sessions, settings):
    """Per mode, lab group and method: the segments of the lab's single-source sessions judged right."""
    seg, out = settings["segments"], []
    for mode in MODES:
        data = {run: dataset(s["events"], whole_truth(s), mode, seg) for run, s in sessions.items()}
        for run, rows in data.items():  # leave one session out, as the lab trained its logistic regression
            score(rows, train([r for other, rs in data.items() if other != run for r in rs], seg), seg)
        for group in sorted({s["segment_group"] for s in sessions.values()}):
            runs = [run for run, s in sessions.items() if s["segment_group"] == group]
            rows = [row for run in runs for row in data[run]]
            for method in METHODS:
                result = accuracy(rows, method, seg)
                out.append({"mode": mode, "group": group, "method": method, "runs": len(runs),
                            "segments": len(rows), **(result if result["n"] else {"result": None})})
    return out


def splices(sessions, settings, with_logistic=True):
    """The lab's splices of Claude in Chrome with the human-like script standing in: per mode and method."""
    lab, seg = settings["lab"], settings["segments"]
    params = splice.load_params()
    agents, stand_ins = (_long_enough(sessions, group, lab["min_input_events"])
                         for group in (lab["splice_agent"], lab["splice_stand_in"]))
    cache = {}  # (run, mode) -> the run's training rows, answered as the lab answered them
    rows = []
    for agent in agents:
        for stand_in in stand_ins:
            models = {}  # one model per mode: the training set does not depend on the pattern
            for pattern in params["patterns"].values():
                spliced = splice.build(sessions[agent]["events"], sessions[stand_in]["events"], pattern, params,
                                       truth=splice.lab_truth)  # the lab's numbers, as the lab cut them
                if spliced is None:
                    continue
                for mode in MODES:
                    if mode not in models:
                        models[mode] = _train_without(sessions, (agent, stand_in), stand_ins, mode, seg, cache) \
                            if with_logistic else None
                    test = score(dataset(spliced["events"], spliced["truth"], mode, seg), models[mode], seg)
                    if test:
                        rows.append(_splice_row(test, spliced["truth"], mode, seg))
    return [_splice_summary(rows, mode, method, seg) for mode in MODES for method in METHODS
            if any(method in r for r in rows if r["mode"] == mode)]


def _long_enough(sessions, segment_group, minimum):
    """The runs of a lab group with more than `minimum` input events (the lab's splice sources)."""
    return [run for run, s in sessions.items() if s["segment_group"] == segment_group
            and len(segment.input_events(s["events"])) > minimum]


def whole_truth(session, who=None):
    """A single-source session's answer: its whole input span, the lab's way (last input + 1 ms)."""
    inputs = segment.input_events(session["events"])
    who = who or ("human" if session["segment_group"] == "human" else "agent")
    return [(inputs[0]["t"], inputs[-1]["t"] + 1, who)] if inputs else []


def _train_without(sessions, left_out, stand_ins, mode, seg, cache):
    """The lab's training set for one splice: every other session, the stand-ins answered as humans."""
    rows = []
    for run, s in sessions.items():
        if run not in left_out:
            if (run, mode) not in cache:
                truth = whole_truth(s, "human" if run in stand_ins else None)
                cache[run, mode] = dataset(s["events"], truth, mode, seg)
            rows += cache[run, mode]
    return train(rows, seg)


def _splice_row(test, truth, mode, settings):
    """splice.py's row: per method its accuracy, shares by time / action / event, errors and switch errors."""
    true_shares = _shares([row["who"] for row in test], test, settings)
    row = {"mode": mode}
    for method in METHODS:
        if any(r.get(method) is None for r in test):
            continue
        labels = [_label(r[method], settings) for r in test]
        shares = _shares(labels, test, settings)
        errors, predicted, actual = _switch_errors(test, truth, method, settings)
        row[method] = {"acc": accuracy(test, method, settings),
                       "share_err_pp": {m: round(abs(shares[m]["agent"] - true_shares[m]["agent"]) + 0.0,
                                                 settings["round_share"]) for m in MEASURES},
                       "unsure_pp": {m: shares[m]["unsure"] for m in MEASURES},
                       "switch_err_s": errors, "pred_switches": predicted, "true_switches": actual}
    return row


def _splice_summary(rows, mode, method, settings):
    """make_eval.py's row for one mode and method over every splice."""
    results = [r[method] for r in rows if r["mode"] == mode and method in r]
    found = [e for r in results for e in r["switch_err_s"] if e is not None]
    share, digits = settings["round_share"], settings["round_accuracy"]
    return {"mode": mode, "method": method, "splices": len(results),
            "acc_all_mean": round(statistics.mean(r["acc"]["acc_all"] for r in results), digits),
            "share_err_pp_median": {m: round(statistics.median(r["share_err_pp"][m] for r in results), share)
                                    for m in MEASURES},
            "share_err_pp_max": {m: round(max(r["share_err_pp"][m] for r in results), share) for m in MEASURES},
            "unsure_pct_median_time": round(statistics.median(r["unsure_pp"]["time"] for r in results), share),
            "switch_err_s_median": round(statistics.median(found), share) if found else None,
            "switch_err_s_p90": sorted(found)[int(settings["p90"] * (len(found) - 1))] if found else None,
            "true_switches_missed": sum(1 for r in results for e in r["switch_err_s"] if e is None),
            "extra_pred_switches": sum(max(0, r["pred_switches"] - r["true_switches"]) for r in results)}


def _switch_errors(test, truth, method, settings):
    """For each true switch, seconds to the nearest predicted switch between decided runs (None: none predicted)."""
    runs = []
    for row in test:
        who = _label(row[method], settings)
        if runs and runs[-1]["who"] == who:
            runs[-1]["end"] = row["end"]
        else:
            runs.append({"start": row["start"], "end": row["end"], "who": who})
    decided = [r for r in runs if r["who"] != "unsure"]
    predicted = [b["start"] for a, b in zip(decided, decided[1:]) if a["who"] != b["who"]]
    actual = [start for start, _, _ in splice.boundaries(truth)]
    errors = [round(min(abs(t - p) for p in predicted) / MS_PER_S, settings["round_share"])
              if predicted else None for t in actual]
    return errors, len(predicted), len(actual)


def _shares(labels, rows, settings):
    """labcore.shares by time, by action and by event: percentages per who, rounded as the lab rounded them."""
    weights = {"time": [r["active_ms"] for r in rows], "actions": [1] * len(rows),
               "events": [r["n_events"] for r in rows]}
    out = {}
    for measure, values in weights.items():
        total = sum(values) or 1
        sums = {"human": 0.0, "agent": 0.0, "unsure": 0.0}
        for who, weight in zip(labels, values):
            sums[who] += weight
        out[measure] = {who: round(PERCENT * value / total, settings["round_share"]) for who, value in sums.items()}
    return out


def _label(p, settings):
    low, high = settings["band"]
    return timeline.label(p, {"human_max": low, "agent_min": high})
