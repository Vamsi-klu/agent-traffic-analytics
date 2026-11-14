"""The thresholds of GOAL section 6 and the gate that judges measured values against them (plan step S3.9).

    load(path) -> thresholds        eval/thresholds.json, checked (ThresholdsError when it is malformed)
    judge(thresholds, measurements) -> [verdict per threshold]
    exit_code(verdicts) -> 0 when every threshold the gate judges passes, else 1

A measurement is one data set's value for one threshold, made by measures.py:
    {"threshold": "A1", "source": "recordings", "value": number or None, "n": samples, "count": k (optional),
     "groups": {group: {"right", "n"}} (optional, for a per-group minimum), "what": ..., "statistic": ...}
value None with samples means the statistic could not be made from them (A5: a hand-off the timeline missed), which
fails. A threshold passes when every measurement of a gated source that has samples passes and at least one has;
with none it has no data, which the gate does not count as a pass (GOAL section 2: what did not run did not pass).
Reference sources are carried along and never judged. Thresholds another step measures are listed as "elsewhere".
"""
import json
import math
import operator

MEASURED_HERE = "agentcake eval"
PASS, FAIL, NO_DATA, ELSEWHERE = "pass", "fail", "no_data", "elsewhere"
OPERATORS = {"<=": operator.le, ">=": operator.ge, "<": operator.lt, ">": operator.gt}
UNITS = ("share", "points", "s", "ms")
REQUIRED = ("id", "goal", "op", "value", "unit", "measure", "statistic", "data", "measured_by")


class ThresholdsError(ValueError):
    """eval/thresholds.json is malformed: raised on loading, so a typo never reaches a gate."""


def load(path):
    """The thresholds file, checked: every entry complete, operators and units known, ids unique."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("thresholds")
    if not isinstance(entries, list) or not entries:
        raise ThresholdsError(f"{path}: no thresholds")
    seen = set()
    for entry in entries:
        _check(entry, path)
        if entry["id"] in seen:
            raise ThresholdsError(f"{path}: {entry['id']} twice")
        seen.add(entry["id"])
    return data


def by_id(thresholds):
    return {entry["id"]: entry for entry in thresholds["thresholds"]}


def passes(entry, value):
    """Whether a value meets the threshold's comparison (None never does)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return OPERATORS[entry["op"]](value, entry["value"])


def judge(thresholds, measurements):
    """One verdict per threshold, in the file's order (see the module docstring)."""
    out = []
    for entry in thresholds["thresholds"]:
        mine = [m for m in measurements if m["threshold"] == entry["id"]]
        gated_ids, reference_ids = entry["data"]["gated"], entry["data"]["reference"]
        gated = [_judged(entry, m) for m in mine if m["source"] in gated_ids]
        reference = [m for m in mine if m["source"] in reference_ids]
        if entry["measured_by"] != MEASURED_HERE:
            status = ELSEWHERE
        elif not any(m["n"] for m in gated):
            status = NO_DATA
        else:
            status = PASS if all(m["status"] == PASS for m in gated if m["n"]) else FAIL
        out.append({"id": entry["id"], "status": status, "goal": entry["goal"], "op": entry["op"],
                    "value": entry["value"], "unit": entry["unit"], "measure": entry["measure"],
                    "statistic": entry["statistic"], "measured_by": entry["measured_by"],
                    "gated": gated, "reference": reference,
                    "missing": [source for source in gated_ids if not any(m["source"] == source and m["n"]
                                                                          for m in gated)]})
    return out


def exit_code(verdicts):
    """0 when every threshold measured here passes; 1 when one fails or has no data."""
    judged = [v for v in verdicts if v["status"] != ELSEWHERE]
    return 0 if judged and all(v["status"] == PASS for v in judged) else 1


def _judged(entry, measurement):
    """The measurement with its own status: pass, fail, or no data (no samples)."""
    if not measurement["n"]:
        return dict(measurement, status=NO_DATA)
    ok = passes(entry, measurement["value"])
    if ok and "n" in entry and measurement["n"] < entry["n"]:
        ok = False  # A7 asks for all 10: fewer cases are not a pass
    if ok and "min_per_group" in entry:
        ok = all(group["n"] >= entry["min_per_group"] for group in measurement.get("groups", {}).values())
    return dict(measurement, status=PASS if ok else FAIL)


def _check(entry, path):
    if not isinstance(entry, dict):
        raise ThresholdsError(f"{path}: an entry must be an object, got {entry!r}")
    missing = [key for key in REQUIRED if key not in entry]
    if missing:
        raise ThresholdsError(f"{path}: {entry.get('id', '?')} lacks {missing}")
    for part in (entry, entry.get("and")):
        if part is None:
            continue
        if part["op"] not in OPERATORS:
            raise ThresholdsError(f"{path}: {entry['id']}: unknown operator {part['op']!r}")
        if part["unit"] not in UNITS:
            raise ThresholdsError(f"{path}: {entry['id']}: unknown unit {part['unit']!r}")
        if isinstance(part["value"], bool) or not isinstance(part["value"], (int, float)):
            raise ThresholdsError(f"{path}: {entry['id']}: value must be a number")
    data = entry["data"]
    if not (isinstance(data, dict) and isinstance(data.get("gated"), list) and isinstance(data.get("reference"), list)):
        raise ThresholdsError(f"{path}: {entry['id']}: data needs gated and reference lists")
