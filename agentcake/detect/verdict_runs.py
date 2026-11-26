"""Which runs of the behaviour timeline count as one side of a Human + agent session (class mixed), and the reasons
for the runs too short to count. Split from verdict.py, which decides the class (rule 5) with them.

    long_runs(runs, who, rule) -> the runs of who that count
    short_reasons(runs, cls, rule) -> one behavior.short-run reason per run of the other side that does not count

runs: timeline.build()'s runs ({"who", "start", "end", "n", "acts", ...}: n steps, acts of them clicks or inputs);
rule: agentcake/data/verdict.json "mixed". A human's run counts with at least min_actions steps over at least
min_span_s seconds (a hand needs time: lab session cic-03's 12 "human" actions in 0.66 s were Claude in Chrome
typing). An agent's counts with at least min_actions clicks or inputs of its own, however fast (actions the session
page lists under All actions, so a Human + agent session that behaviour alone decided shows its agent acting). Its
scrolling and pointer movement alone, however much evidence they carry, never make an agent's part: a person must not
be taken for an agent, and missing an agent is the safer side (a person scrolling and hovering the browser beside
their editor was shown as Human + agent with an agent share of 0%).
"""
from agentcake.detect.verdict_text import reason
from agentcake.units import MS_PER_S

HUMAN, AGENT = "human", "agent"
PAGE = "page"


def long_runs(runs, who, rule):
    """The runs of `who` that count as one side of a Human + agent session (see the module docstring)."""
    if who == AGENT:
        return [r for r in runs if r["who"] == AGENT and counted(r) >= rule["min_actions"]]
    return [r for r in runs if r["who"] == who and r["n"] >= rule["min_actions"]
            and (r["end"] - r["start"]) / MS_PER_S >= rule["min_span_s"]]


def counted(run):
    """What a run's length is counted in: an agent's clicks and inputs, a human's steps."""
    return run.get("acts", 0) if run["who"] == AGENT else run["n"]


def short_reasons(runs, cls, rule):
    """A behavior.short-run reason for each human or agent run of the side that is not the session's class (cls) and
    is too short to count: the side does not take part in the session."""
    short = [r for r in runs if r["who"] in (HUMAN, AGENT) and r["who"] != cls
             and r not in long_runs(runs, r["who"], rule)]
    return [reason("behavior.short-run", PAGE, counted(r), who=r["who"], n=counted(r),
                   span=round((r["end"] - r["start"]) / MS_PER_S, 1)) for r in short]
