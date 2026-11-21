"""When a session's soft environment traces count (rule 4 of verdict.py): a soft trace needs company.

    counts(soft, hard, says_agent, settings) -> bool

soft: the session's soft hits; hard: its hard hits (automation and spoofing that overrule, and the other hard traces);
says_agent: the behaviour model judged an agent and no assistive tool made that doubtful; settings: verdict.json.

A rule outside every family counts with any other trace that is not weak, or with agent behaviour, as since the
verdict began. The rules of one family (env_rules.json legend.families) are one kind of evidence however many of them
hold: they count with agent behaviour, or with a hit of a rule outside every family whose kind and id are not among
what the family's own collisions leave too (verdict.json families). The rules for a computer passing as a phone or
tablet are such a family: Chrome DevTools' device emulation and user-agent switchers, which people use, make all of
them hold and leave other spoofing traces and the DevTools-protocol leak behind. A family's hits never
take company away from the other rules, so adding one can only add an Agent where a trace of another kind stood
beside it, and a session with no family hit is judged exactly as before.
"""


def counts(soft, hard, says_agent, settings):
    """Whether the soft hits count (see the module docstring)."""
    others = [found for found in list(soft) + list(hard) if not found.family]
    if any(not found.family for found in soft) and (len({found.rule for found in others}) > 1 or says_agent):
        return True
    for family in {found.family for found in soft if found.family}:
        alike = settings["families"][family]
        if says_agent or any(found.kind not in alike["kinds"] and found.rule not in alike["rules"]
                             for found in others):
            return True
    return False
