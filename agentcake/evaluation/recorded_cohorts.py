"""Reference counts for matched recorder cohorts, grouped by label, observed surface and truth."""
from agentcake.evaluation.sessions import TOO_LITTLE
from agentcake.evaluation.stats import tally

AGENT_OR_MIXED = ("agent", "mixed")
DASH = "—"


def build(rows, handoffs, cohorts, limit_s):
    """Use every loaded session in each cohort, including ones with too little data or missing mode."""
    groups = {}
    for row in rows:
        label, truth = row["group"], row["truth"]
        cohort = cohorts.get(label)
        if cohort is None or truth["class"] not in cohort["truth"]:
            continue
        mode = truth.get("mode")
        surface = mode if mode in cohort["modes"] else None
        groups.setdefault((label, surface, truth["class"]), []).append(row)
    cells = []
    for (label, mode, truth), members in groups.items():
        cell = {"label": label, "mode": mode, "truth": truth, "sessions": len(members),
                "classes": tally(row["class"] for row in members)}
        name = cohorts[label].get("name")
        if name and truth == "agent":
            cell["expected_name"] = name
            cell["named_agent_or_mixed"] = sum(row["class"] in AGENT_OR_MIXED and row["name"] == name
                                              for row in members)
        if truth == "mixed":
            cell["handoffs"] = _handoffs([handoffs[r["id"]] for r in members if r["id"] in handoffs], limit_s)
        cells.append(cell)
    return sorted(cells, key=lambda c: (c["label"], c["mode"] or "", c["truth"]))


def _handoffs(rows, limit_s):
    """Count truth boundaries even when the session produced no timeline. Errors match the direction of the handoff."""
    errors = [error for row in rows if row["verdict"] for error in row["verdict"]["handoff_errors_s"]]
    found = [error for error in errors if error is not None]
    return {"true": sum(row["true_handoffs"] for row in rows), "found": len(found),
            "within_limit": sum(error <= limit_s for error in found)}


def markdown(cells, limit_s):
    if not cells:
        return []
    lines = ["## Antigravity recording cohorts", "",
             "| label | mode | truth | sessions | Agent | Mixed | Too little data | Agent or Mixed with expected "
             f"name | hand-offs found / true (within {limit_s} s) |", "|---|---|---|---|---|---|---|---|---|"]
    for cell in cells:
        n, classes = cell["sessions"], cell["classes"]
        name, handoffs = cell.get("expected_name"), cell.get("handoffs")
        named = f"{cell['named_agent_or_mixed']}/{n} (`{name}`)" if name else DASH
        timed = (f"{handoffs['found']}/{handoffs['true']} ({handoffs['within_limit']})"
                 if handoffs and handoffs["true"] else DASH)
        lines.append(f"| {cell['label']} | {cell['mode'] or 'unverified'} | {cell['truth']} | {n} | "
                     f"{classes.get('agent', 0)} | {classes.get('mixed', 0)} | {classes.get(TOO_LITTLE, 0)} | "
                     f"{named} | {timed} |")
    return lines + [""]
