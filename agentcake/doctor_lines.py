"""How `doctor` says its checks (S1.1, S6.1): one line each, then one line for the whole.

A check is (name, verdict, info). verdict True passes and False fails, as since 0.3.x; WARN works but needs attention
(lists past their age, another `agentcake` first on PATH); SKIP was not checked here (a sandbox in the way, the server
half of a static site, a page doctor was not given). Only a failed check fails doctor. The words are in
data/copy.en.json.
"""
from agentcake.wording import text

WARN, SKIP = "warn", "skip"
VERDICT_WORDS = {True: "doctor_pass", False: "doctor_fail", WARN: "doctor_warn", SKIP: "doctor_skip"}


def passed(checks):
    """Whether no check failed: each passed, or was a WARN or a SKIP."""
    return all(verdict is True or verdict in (WARN, SKIP) for _, verdict, _ in checks)


def print_checks(checks):
    for check, verdict, info in checks:
        print(text("doctor_line", verdict=text(VERDICT_WORDS[verdict]), check=check, info=info))


def summary(checks, base):
    """The last line: all passed (and how many warnings), or some failed."""
    if not passed(checks):
        return text("doctor_some_failed")
    warnings = sum(1 for _, verdict, _ in checks if verdict == WARN)
    return text("doctor_all_passed_warn", count=warnings, base=base) if warnings else text("doctor_all_passed", base=base)
