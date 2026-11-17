"""`agentcake eval`: how well AgentCake judges sessions with known answers, and the gate of eval/thresholds.json.

    agentcake eval [--gate] [--out DIR] [--sources FILE] [--recordings DIR] [--posthog DIR] [--cake-home DIR]
                   [--truth-goal FILE] [--truth-manual FILE] [--truth-recordings FILE] [--thresholds FILE]
                   [--lab FILE] [--lab-signals FILE] [--uploads DIR] [--named FILE] [--selfcollect DIR]
                   [--truth-selfcollect FILE] [--site-home DIR] [--truth-site FILE] [--no-logistic]

Reads every data set it finds (agentcake/evaluation/sources.py: the command line, then the sources file, then the
files of a checkout), judges each session with agentcake.detect and prints the report; with --out it writes
eval.md (the report) and eval.json (every session row and the gated take-over rows: lab run names and 12-hex short
hashes, no paths) there. --gate makes
the exit code the verdict of eval/thresholds.json on the thresholds this command measures: 0 when every one passes,
1 when one fails or has no data (what did not run did not pass), 2 for a usage error.
It only reads: it writes no verdict anywhere and sends nothing over the network. Thresholds are never in the code:
A5's hand-off limit, for one, is the A5 value of the thresholds file.
"""
import argparse
import json
import os
import sys

from agentcake import datafiles
from agentcake.evaluation import gate, measures, report, sources, tables, takeovers
from agentcake.wording import product, raw, text

SETTINGS_FILE = "data/eval.json"
EXIT_USAGE = 2  # protocol: exit status of a command-line usage error (POSIX utilities, argparse)
HANDOFF_THRESHOLD = "A5"
OPTIONS = (("--sources", "sources"), ("--recordings", "recordings"), ("--posthog", "posthog"),
           ("--cake-home", "cake_home"), ("--truth-goal", "truth_goal"), ("--truth-manual", "truth_manual"),
           ("--truth-recordings", "truth_recordings"), ("--thresholds", "thresholds"), ("--lab", "lab_sessions"),
           ("--lab-signals", "lab_signals"), ("--uploads", "cakejs_uploads"), ("--named", "named_user_agents"),
           ("--selfcollect", "selfcollect"), ("--truth-selfcollect", "truth_selfcollect"), ("--site-home", "site_home"),
           ("--truth-site", "truth_site"))
REPORT_FILE, DATA_FILE = "eval.md", "eval.json"


def parse(argv):
    words = raw("eval_options")
    parser = argparse.ArgumentParser(prog="agentcake eval", description=words["about"].format(**product()))
    parser.add_argument("--gate", action="store_true", help=words["gate"])
    parser.add_argument("--out", help=words["out"])
    parser.add_argument("--no-logistic", action="store_true", help=words["no_logistic"])
    for flag, key in OPTIONS:
        parser.add_argument(flag, dest=key, help=words[key])
    return parser.parse_args(argv)


def run(options, settings=None):
    """(results, verdicts, where, notes, limit_s) for a dict of command-line values; raises ThresholdsError or
    FileNotFoundError for a thresholds file that is missing or malformed."""
    settings = settings or datafiles.load(SETTINGS_FILE)
    where = sources.locate(options, settings)
    if not where["thresholds"]:
        raise FileNotFoundError(text("eval_no_thresholds"))
    thresholds = gate.load(where["thresholds"])
    limit_s = gate.by_id(thresholds)[HANDOFF_THRESHOLD]["value"]
    data = sources.load(where, settings)
    results = tables.build(data, settings, limit_s, with_logistic=not options.get("no_logistic"))
    verdicts = gate.judge(thresholds, measures.collect(results, settings, limit_s))
    return results, verdicts, where, data["notes"], limit_s


def main(argv=None):
    try:
        args = parse(sys.argv[1:] if argv is None else list(argv))
    except SystemExit as stop:  # argparse has printed its message
        return EXIT_USAGE if stop.code else 0
    options = {key: value for key, value in vars(args).items() if value not in (None, False)}
    try:
        results, verdicts, where, notes, limit_s = run(options)
    except (FileNotFoundError, gate.ThresholdsError) as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    body = report.markdown(results, verdicts, where, notes, limit_s)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, REPORT_FILE), "w", encoding="utf-8") as f:
            f.write(body)
        with open(os.path.join(args.out, DATA_FILE), "w", encoding="utf-8") as f:
            json.dump(as_json(results, verdicts, notes, limit_s), f, ensure_ascii=False, indent=1, sort_keys=True)
        print("\n".join(report.markdown_gate(verdicts)))
        print(text("eval_wrote", folder=args.out, report=REPORT_FILE, data=DATA_FILE))
    else:
        print(body)
    code = gate.exit_code(verdicts)
    if args.gate:
        failing = [v["id"] for v in verdicts if v["status"] not in (gate.PASS, gate.ELSEWHERE)]
        print(text("eval_gate_pass") if code == 0 else text("eval_gate_fail", ids=", ".join(failing)))
        return code
    return 0


def as_json(results, verdicts, notes, limit_s):
    """The results without the in-memory evidence: every session row (its verdict and answer, never a path), the
    take-over rows of the data sets the gate judges, and the reference ones' summaries (both views): their rows,
    thousands of splices, are made again by running the command."""
    rows = {source: [{k: v for k, v in r.items() if k != "evidence"} for r in items]
            for source, items in results["rows"].items()}
    gated = {m["source"] for v in verdicts for m in v["gated"]}
    sets = {source: items if source in gated else {"summary": {view: takeovers.summary(items, view, limit_s)
                                                               for view in takeovers.VIEWS}}
            for source, items in results["takeovers"].items()}
    return {**{k: v for k, v in results.items() if k not in ("rows", "takeovers")}, "rows": rows, "takeovers": sets,
            "gate": verdicts, "notes": notes}


if __name__ == "__main__":
    sys.exit(main())
