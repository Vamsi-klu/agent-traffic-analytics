"""The words of a verdict (S3.4): each reason's layer, evidence grade, tone, facts and words, and what each class means.

Reasons come from agentcake/data/reasons.json, the meaning of each class (the dashboard's "how cake judges", S5.3)
from agentcake/data/judging.en.json; both ship with the release and are read once per process. A reason keeps the
facts it was given, and is put into words each time it is shown (words()): a session judged before the wording
changed reads in today's words (D34: the words are display, the facts are what is kept). Its words are two: text, a
sentence that says what it means, and detail, what was seen (the technical evidence), None when it has none. An
environment rule's hit is worded by the rule (its title and detail in env_rules.json), a Web Bot Auth result by
webbotauth.json, an agent product's indicator by agent_markers.json. A reason kept before facts were kept gets its
facts back from its own text (reasons_past.py), else keeps the text it was given.

    reason(reason_id, source=None, value=None, **facts)
        -> {"id", "layer", "source", "value", "grade", "tone", "facts", "text", "detail"}
    env_reason(hit, table=None) -> the same for an env_rules.Hit, with its "strength" and "pages"
    words(kept, origin=None) -> (text, detail): a kept reason in today's words; its moments on the replay's clock
                       when origin (the replay's start) is given
    half(name) -> how a half is named in a reason ("the page", "cake.js's requests", "the page request")
    reasons(), judging() -> reasons.json and judging.en.json as dicts

Facts are plain values (they are kept as JSON). A few name a phrase instead of holding words, and are put into words
with it:
    half              a half ("page", "collector", "server"), or a list of them: reasons.json "halves", joined
    method, other_method   how a name was found: reasons.json "methods"
    basis             what made the behaviour model judge an agent (a list): reasons.json "behavior_basis", each
                      filled in from the facts and joined; the segments' majority ("rules") with kinds, the kinds
                      of agent evidence it saw (reasons.json "behavior_kinds", joined)
    kind              the one kind of behaviour evidence an uncorroborated session showed (a rule's kind,
                      behavior_model.json): reasons.json "behavior_kinds"
    signals           crawler-like patterns (a list): reasons.json "crawler_signals", filled in from pages and every_s
                      (a gap in seconds, said as reasons.json "durations")
    marker            an agent product's mark, with from_ms and to_ms (from the visit's start; to_ms None: still
                      there at the end): {marker} its text and {marker_detail} its detail (agent_markers.json)
    at                a hand-off's moment, in whole seconds from the visit's start: said as the player writes a moment
                      (markers.clock, "0:47")

A reason that says a moment (MOMENTS: a hand-off, an indicator's span) also keeps it in its value, in epoch ms on the
events' clock. Given the replay's start (origin: the session's first recorded event, from which the player, the
timeline and every list of the session page count), words() says those moments from it, so that a reason and the
timeline beside it name the same moment the same way (D34; PostHog's replay counts its player, its list and its events
from the recording's start); without one, from the visit's start the facts keep.
    signature         a Web Bot Auth result (webbotauth.as_facts()): {signature} its reason and {signature_detail}
                      its detail (webbotauth.json)

source is where the evidence was read (G6): "page" (cake.js in the visitor's page), "collector" (cake's own collect
endpoint, which also sees the visitor's address) or "server" (the site's server half), or None for a conclusion.
tone is how the interface marks a reason: "agent", "human" or "none" (a fact for neither).
"""
import string

from agentcake import datafiles
from agentcake.detect import env_rules, markers, webbotauth
from agentcake.units import MS_PER_S, S_PER_MIN
from agentcake.wording import product

REASONS_FILE = "data/reasons.json"
JUDGING_FILE = "data/judging.en.json"
ENV_LAYER = "environment"
WEAK = "weak"
AGENT_TONE, NO_TONE = "agent", "none"
PRODUCT_FACT = "product"
RULES_BASIS, RULES_ONE, RULES_UNNAMED = "rules", "rules_one", "rules_unnamed"  # behavior_basis: kinds, one kind, none
# The facts that say a reason's moments, in the order its value keeps them (epoch ms on the events' clock, verdict.py)
MOMENTS = {"behavior.handoff": ("at",), "behavior.indicator": ("from_ms", "to_ms")}
SECONDS_FACTS = frozenset({"at"})  # moment facts kept in whole seconds from the visit's start (the others in ms)


def reasons():
    return datafiles.load(REASONS_FILE)


def judging():
    return datafiles.load(JUDGING_FILE)


class _Facts(dict):
    """The facts of a reason for str.format_map; a fact that is not known prints as the file's $missing text."""

    def __missing__(self, name):
        return reasons()["$missing"]


def _fill(template, facts):
    known = {name: value for name, value in facts.items() if value is not None}
    return template.format_map(_Facts({PRODUCT_FACT: product()["name"], **known}))


def _plain(value):
    """A fact as JSON keeps it: tuples and lists as lists, dicts with str keys, numbers, text, true/false, null."""
    if isinstance(value, dict):
        return {str(key): _plain(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_plain(inner) for inner in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def reason(reason_id, source=None, value=None, **facts):
    """One reason of a verdict with its facts and their words; raises KeyError for an id reasons.json lacks."""
    entry = reasons()["reasons"][reason_id]
    kept = {"id": reason_id, "layer": entry["layer"], "source": source, "value": value, "grade": entry["grade"],
            "tone": entry["tone"], "facts": _plain(facts)}
    kept["text"], kept["detail"] = words(kept)
    return kept


def env_reason(hit, table=None):
    """The reason an environment rule's hit gives: the rule's id and words, read from the half that holds it."""
    rule = (table or env_rules.load_rules()).rule(hit.rule)
    out = {"id": hit.rule, "layer": ENV_LAYER, "source": hit.half, "value": hit.value, "grade": hit.grade,
           "tone": NO_TONE if hit.strength == WEAK else AGENT_TONE, "strength": hit.strength, "facts": {},
           "text": rule.title, "detail": rule.detail}
    if hit.pages is not None:
        out["pages"] = list(hit.pages)
    return out


def words(kept, origin=None):
    """(text, detail) of a kept reason in today's words. An environment rule's hit needs only its id; any other
    reason fills its facts into today's sentences for its id. A reason kept before facts were kept gets them back
    from its own text (reasons_past.py); one whose sentence needs no facts is worded at once; failing both, and for
    an id this release does not know, it keeps the words it was given. origin: the replay's start (epoch ms on the
    events' clock), from which a reason's moments are said (see the module docstring)."""
    reason_id = kept.get("id")
    entry = reasons()["reasons"].get(reason_id)
    if entry is None:
        rule = _env_rule(reason_id)
        return (rule.title, rule.detail) if rule else (kept.get("text"), kept.get("detail"))
    facts = kept.get("facts")
    if facts is None:
        from agentcake.detect import reasons_past  # it reads this module's tables: imported when first needed
        facts = reasons_past.facts(kept)
    if facts is None:
        if _needs_facts(entry):
            return kept.get("text"), kept.get("detail")
        facts = {}
    said = _phrases(_moments(reason_id, kept.get("value"), facts, origin))
    return _fill(entry["text"], said), (_fill(entry["detail"], said) if entry.get("detail") else None)


def _moments(reason_id, value, facts, origin):
    """facts with each moment the reason says (MOMENTS) in ms: from origin, read off the value, when both are there;
    else from the visit's start, as the facts keep it."""
    names = MOMENTS.get(reason_id)
    if not names:
        return facts
    out = dict(facts)
    times = value if isinstance(value, (list, tuple)) else [value]
    for name, moment in zip(names, times):
        if origin is not None and isinstance(moment, (int, float)):
            out[name] = moment - origin
        elif name in SECONDS_FACTS and isinstance(facts.get(name), (int, float)):
            out[name] = facts[name] * MS_PER_S
    return out


def _env_rule(rule_id):
    try:
        return env_rules.load_rules().rule(rule_id)
    except KeyError:
        return None


def _needs_facts(entry):
    names = {name for template in (entry["text"], entry.get("detail") or "")
             for _, name, _, _ in string.Formatter().parse(template) if name}
    return bool(names - {PRODUCT_FACT})


def _phrases(facts):
    """The facts with each one that names a phrase put into its words (see the module docstring)."""
    table, said = reasons(), dict(facts)
    if "half" in facts:
        said["half"] = halves_words(facts["half"])
    for key in ("method", "other_method"):
        if key in facts:
            said[key] = table["methods"].get(facts[key])
    if "basis" in facts:
        kinds = [table["behavior_kinds"].get(kind) for kind in facts.get("kinds") or ()]
        seen = {"kinds": _joined(kinds), "kinds_n": len([kind for kind in kinds if kind])}
        said["basis"] = "; ".join(_fill(table["behavior_basis"][_basis_phrase(name, seen)], {**facts, **seen})
                                  for name in facts["basis"] or () if name in table["behavior_basis"]) or None
    if "kind" in facts:
        said["kind"] = table["behavior_kinds"].get(facts["kind"])
    if "signals" in facts:
        every = {"pages": facts.get("pages"), "every": duration(facts.get("every_s"))}
        said["signals"] = ", ".join(_fill(table["crawler_signals"][key], every) for key in facts["signals"] or ()
                                    if key in table["crawler_signals"]) or None
    if "marker" in facts:
        for key, field in (("marker", "text"), ("marker_detail", "detail")):
            said[key] = markers.words(facts["marker"], facts.get("from_ms"), facts.get("to_ms"), field)
    if "signature" in facts:
        said["signature"], said["signature_detail"] = webbotauth.words(facts["signature"] or {})
    if isinstance(facts.get("at"), (int, float)):
        said["at"] = markers.clock(facts["at"])  # a hand-off's moment, in ms by now (_moments)
    return said


def _basis_phrase(name, seen):
    """The phrase for one basis: the segments' majority ("rules") names the kinds of agent evidence the model saw, or,
    for a verdict kept before it kept them, says so without them (never as a share: the page counts actions once)."""
    if name != RULES_BASIS:
        return name
    return (RULES_ONE if seen["kinds_n"] == 1 else RULES_BASIS) if seen["kinds"] else RULES_UNNAMED


def _joined(words):
    found = [word for word in words if word]
    if len(found) <= 1:
        return found[0] if found else None
    return ", ".join(found[:-1]) + " and " + found[-1]


def half(name):
    return reasons()["halves"][name]


def halves_words(names):
    """One half or a list of them in words: "the page", "the page and the page request", "a, b and c"."""
    found = [reasons()["halves"].get(name) for name in ([names] if isinstance(names, str) else names or ())]
    found = [word for word in found if word]
    if len(found) <= 1:
        return found[0] if found else None
    return ", ".join(found[:-1]) + " and " + found[-1]


def duration(seconds):
    """A gap as the reasons say it: whole minutes from a minute up, whole seconds below; None when not known."""
    if seconds is None:
        return None
    units = reasons()["durations"]
    if seconds >= S_PER_MIN:
        return units["minutes"].format(n=round(seconds / S_PER_MIN))
    return units["seconds"].format(n=round(seconds))
