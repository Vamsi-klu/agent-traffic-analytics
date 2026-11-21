"""The environment layer's rules: automation, product, cloud-host and extension traces in a session.

Every rule is data, in agentcake/data/env_rules.json: its id, kind, the half it is read from (the page script, cake's
collect endpoint or the site's server half), where it comes from, what is known to collide with it, when it was last
checked and whether it is on by default. This module loads that table, checks it, and evaluates each rule's `match`
(written in predicate.py's language) against a session's signals (env_signals.py turns recorded data into signals).
A rule that is off by default can wait for a page-script setting (`setting`): it runs on the visits cake.js recorded
with that setting on, as their page records say (signals' script_settings), whatever the setting is now. Rules of
one `family` (the legend's families) are one kind of evidence together: the verdict counts them as one
(verdict_soft.py).

    evaluate(signals, table=None, enabled=None) -> EnvResult(hits, unknown, off)

A hit gives the rule id, layer, kind, half, strength, evidence grade and the value that matched, and the pages it held
on; the verdict combines the hits with the other three layers. A rule whose inputs the session did not record is listed as
unknown, never as a miss.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache

from agentcake import paths
from agentcake.detect import predicate

RULES_FILE = os.path.join(paths.PACKAGE_DIR, "data", "env_rules.json")

# Where a rule is evaluated: on each page view, on the first page view only, or on the session as a whole.
SCOPES = ("page", "landing", "session")
_REQUIRED = ("id", "layer", "kind", "half", "scope", "strength", "enabled", "title", "match", "grade", "date",
             "evidence", "sources", "collisions")
_OPTIONAL = ("botscent", "names", "suggests", "report", "detail", "setting", "family")


class EnvRulesError(ValueError):
    """The rule table is malformed: raised when it is loaded, so a typo never reaches a judgement."""


@dataclass(frozen=True)
class Rule:
    id: str
    layer: str
    kind: str
    half: str
    scope: str
    strength: str
    enabled: bool
    title: str
    match: dict
    grade: str
    date: str
    evidence: str
    sources: tuple
    collisions: str
    botscent: tuple = ()
    names: str | None = None
    suggests: str | None = None
    report: tuple = ()
    detail: str | None = None  # what was seen, in technical words: the reason's second line
    setting: str | None = None  # the page-script setting this rule waits for (see evaluate)
    family: str | None = None  # the rules that are one kind of evidence with this one (the legend's families)


@dataclass(frozen=True)
class RuleTable:
    version: int
    updated: str
    legend: dict
    signals: dict
    botscent: dict
    rules: tuple

    def rule(self, rule_id):
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        raise KeyError(rule_id)


@dataclass(frozen=True)
class Hit:
    """One rule that held: what the verdict writes into a session's reasons."""
    rule: str
    layer: str
    kind: str
    half: str
    strength: str
    grade: str
    value: object
    pages: tuple | None = None
    names: str | None = None
    suggests: str | None = None
    family: str | None = None


@dataclass(frozen=True)
class EnvResult:
    hits: tuple
    unknown: tuple  # rule ids whose inputs this session did not record
    off: tuple  # rule ids switched off (off by default and not turned on in the config)


def _value(rule, outcome, data):
    if rule.report:
        return {path: predicate.plain(predicate.resolve(data, path)) for path in rule.report}
    return predicate.plain(outcome.witness)


def _run(rule, signals):
    """(state, value, pages) of one rule on one session. A page-scope rule holds when it holds on any page; it is
    unknown only when no page recorded its inputs (a page that did and did not match counts as checked)."""
    if rule.scope == "session":
        outcome = predicate.check(rule.match, signals)
        return outcome.state, _value(rule, outcome, signals), None
    pages = signals.get("pages")
    if not isinstance(pages, list) or not pages:
        return None, None, None
    if rule.scope == "landing":
        pages = pages[:1]
    held, value, checked = [], None, False
    for index, page in enumerate(pages):
        outcome = predicate.check(rule.match, page)
        if outcome.state:
            if not held:
                value = _value(rule, outcome, page)
            held.append(index)
        elif outcome.state is False:
            checked = True
    if held:
        return True, value, tuple(held)
    return (False if checked else None), None, None


def evaluate(signals, table=None, enabled=None):
    """Run every rule that is on against one session's signals.

    A rule runs when it is on by default, or when the page-script setting it waits for (`setting`) was on while the
    visit was recorded: the setting at the time, not the current one, so that a verdict follows from what the visit
    recorded and turning the setting off later keeps the conclusions it paid for (cake.js only sends what such a rule
    reads while the setting is on). `enabled` maps rule ids to True/False from the user's config and overrides both;
    ids it does not know are ignored here (config validation checks them against table.rules).
    """
    table = table or load_rules()
    overrides = enabled or {}
    recorded = signals.get("script_settings") or {}
    hits, unknown, off = [], [], []
    for rule in table.rules:
        default = rule.enabled or (rule.setting is not None and recorded.get(rule.setting) is True)
        if not overrides.get(rule.id, default):
            off.append(rule.id)
            continue
        state, value, pages = _run(rule, signals)
        if state:
            hits.append(Hit(rule.id, rule.layer, rule.kind, rule.half, rule.strength, rule.grade, value, pages,
                            rule.names, rule.suggests, rule.family))
        elif state is None:
            unknown.append(rule.id)
    return EnvResult(tuple(hits), tuple(unknown), tuple(off))


def _rule(entry, legend, script_settings):
    if not isinstance(entry, dict):
        raise EnvRulesError(f"a rule must be an object, got {entry!r}")
    rule_id = entry.get("id", "?")
    missing = [key for key in _REQUIRED if key not in entry]
    unknown = [key for key in entry if key not in _REQUIRED + _OPTIONAL]
    if missing or unknown:
        raise EnvRulesError(f"{rule_id}: missing {missing}, unknown {unknown}")
    for field, values in (("kind", legend["kinds"]), ("half", legend["halves"]), ("strength", legend["strengths"]),
                          ("grade", legend["grades"]), ("scope", SCOPES)):
        if entry[field] not in values:
            raise EnvRulesError(f"{rule_id}: {field} {entry[field]!r} is not one of {sorted(values)}")
    if not isinstance(entry["enabled"], bool):
        raise EnvRulesError(f"{rule_id}: enabled must be true or false")
    if "setting" in entry and (entry["enabled"] or entry["setting"] not in script_settings):
        raise EnvRulesError(f"{rule_id}: setting is for a rule that is off by default, and must be one of "
                            f"signals.script_settings {sorted(script_settings)}")
    if "family" in entry and entry["family"] not in legend.get("families", {}):
        raise EnvRulesError(f"{rule_id}: family {entry['family']!r} is not one of {sorted(legend.get('families', {}))}")
    try:
        predicate.validate(entry["match"], rule_id)
    except predicate.PredicateError as err:
        raise EnvRulesError(str(err)) from err
    fields = dict(entry)
    for key in ("sources", "botscent", "report"):
        if key in fields:
            fields[key] = tuple(fields[key])
    return Rule(**fields)


def parse_rules(data):
    """A RuleTable from the decoded JSON; raises EnvRulesError on anything malformed."""
    try:
        legend = data["legend"]
        rules = tuple(_rule(entry, legend, data["signals"]["script_settings"]) for entry in data["rules"])
        table = RuleTable(data["version"], data["updated"], legend, data["signals"], data["botscent"], rules)
    except (KeyError, TypeError) as err:
        raise EnvRulesError(f"rule table is missing {err}") from err
    ids = [rule.id for rule in rules]
    duplicates = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
    if duplicates:
        raise EnvRulesError(f"duplicate rule ids: {duplicates}")
    known = set(table.botscent.get("page_reasons", []))
    strays = sorted({reason for rule in rules for reason in rule.botscent if reason not in known})
    if strays:
        raise EnvRulesError(f"botscent reasons not in botscent.page_reasons: {strays}")
    return table


@lru_cache(maxsize=None)
def load_rules(path=RULES_FILE):
    """The rule table shipped with AgentCake (or another file, for tests); read once per path."""
    with open(path, encoding="utf-8") as handle:
        return parse_rules(json.load(handle))
