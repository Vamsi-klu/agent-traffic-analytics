"""The reasons a verdict gives for an agent product's indicator: one per turn span the behaviour timeline was given.

    reasons(line, start_ms, table=None) -> [reason]

line: the behaviour timeline (timeline.build's dict: its marks, actions and evidence); start_ms: the visit's start,
from which each reason's moments are said; table: the mark table (markers.load_table()). A span says when the
indicator was on, in the mark table's words and with the mark's evidence grade, and that the actions in that time are
the agent's ("behavior.indicator"). An indicator stays on for a while after the agent's last action, so when the
timeline judged a span's tail on its own evidence (its "held_to") and a step there did not turn out the agent's, the
span says until when the actions are the agent's instead ("behavior.indicator-tail"). Part of the verdict's behaviour
reasons (verdict.py), kept apart so that each module does one job.
"""
from agentcake.detect import markers
from agentcake.detect.verdict_text import reason

PAGE = "page"  # where the indicator was seen: the page half (verdict.py)
AGENT = "agent"


def reasons(line, start_ms, table=None):
    """The reasons for the timeline's turn spans (see the module docstring), in the spans' order."""
    table = table or markers.load_table()
    steps = (line.get("actions") or []) + (line.get("evidence") or [])
    out = []
    for span in line.get("marks") or []:
        moments = {"marker": span["marker"], "from_ms": span["from"] - start_ms,
                   "to_ms": None if span["to"] is None else span["to"] - start_ms}
        told = [span["from"], span["to"]]
        if "held_to" in span and any(span["from"] <= s["t"] <= span["to"] and s["who"] != AGENT for s in steps):
            said = reason("behavior.indicator-tail", PAGE, told + [span["held_to"]],
                          until_ms=span["held_to"] - start_ms, **moments)
        else:
            said = reason("behavior.indicator", PAGE, told, **moments)
        out.append(dict(said, grade=table.markers[span["marker"]]["grade"]))
    return out
