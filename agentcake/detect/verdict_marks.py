"""The reasons a verdict gives for an agent product's indicator: one per mark, whatever the turn spans it was seen in.

    reasons(line, start_ms, table=None) -> [reason]

line: the behaviour timeline (timeline.build's dict: its marks, actions and evidence); start_ms: the visit's start,
from which each reason's moments are kept; table: the mark table (markers.load_table()). A mark's reason says that the
actions made while it was on are the agent's, in the mark table's words and with the mark's evidence grade
("behavior.indicator"). It gives no time: the summary says when the agent was active, from its first to its last
action (api/session.py), and a page gives one time for that; an indicator stays on after the agent's last action, and
each page shows it anew, so its own spans would give others. The spans stay in the reason's value and facts. When the
timeline judged a span's tail on its own evidence (its "held_to") and a step there did not turn out the agent's, the
reason says that the last actions before the indicator went off were the behaviour model's to judge instead
("behavior.indicator-tail"). Part of the verdict's behaviour reasons (verdict.py), kept apart so that each module does
one job.
"""
from agentcake.detect import markers
from agentcake.detect.verdict_text import reason

PAGE = "page"  # where the indicator was seen: the page half (verdict.py)
AGENT = "agent"


def reasons(line, start_ms, table=None):
    """The reasons for the timeline's turn spans, one per mark, in the order its first span came (see the module
    docstring)."""
    table = table or markers.load_table()
    steps = (line.get("actions") or []) + (line.get("evidence") or [])
    by_mark = {}
    for span in line.get("marks") or []:
        by_mark.setdefault(span["marker"], []).append(span)
    out = []
    for marker, spans in by_mark.items():
        first, last = spans[0], spans[-1]
        moments = {"marker": marker, "from_ms": first["from"] - start_ms,
                   "to_ms": None if last["to"] is None else last["to"] - start_ms}
        told = [first["from"], last["to"]]
        tails = [span for span in spans if "held_to" in span
                 and any(span["from"] <= s["t"] <= span["to"] and s["who"] != AGENT for s in steps)]
        if tails:
            said = reason("behavior.indicator-tail", PAGE, told + [tails[-1]["held_to"]],
                          until_ms=tails[-1]["held_to"] - start_ms, **moments)
        else:
            said = reason("behavior.indicator", PAGE, told, **moments)
        out.append(dict(said, grade=table.markers[marker]["grade"]))
    return out
