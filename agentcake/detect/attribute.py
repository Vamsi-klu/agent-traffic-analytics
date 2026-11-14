"""Which agent or bot a session is (S3.5): its name and how sure, or its category when no product can be named.

Name priority (D5; research note 13 section 5), highest first:
  1 verified: a Web Bot Auth signature checked with the signer's key, the operator's published range, reverse DNS;
  2 a page product rule (env_rules.json, kind product: Muse, Grok Bot, Codex, Cursor, Cloudflare Browser Run, ...);
  3 a self-reported name: the User-Agent, navigator.platform or Signature-Agent, when they agree;
  4 an extension's own trace that points to its product (env.ext.closed-shadow-host: Claude in Chrome), once the
    trace counts (it is soft: agent behaviour or another trace must back it);
  5 an automation tool's own trace (Playwright, Puppeteer or Selenium globals) or the tool's User-Agent token;
  6 no product, a category: infrastructure (an operator's published agent range), automated (Automated browser),
    extension (an extension drove the page), cloud_browser (a cloud computer that does not say who runs it) or
    local_agent (behaviour alone: possibly an agent on the visitor's own computer). A category says where the agent
    runs, which its reason tells; it never names it: the interface calls the agent Unnamed (D39).
The highest level that names a product wins, with the certainty verdict.json "attribution" gives that level (a verified
name is certain; a rule or a trace goes stale when its product changes, so it is likely). A lower level pointing to
another product is listed as outranked; a level whose evidence names several products names none. A Bot (D17) keeps
the list entry that made it one. Products without a trace of their own (browser-use, Playwright MCP and Stagehand
drive Playwright or the DevTools protocol, research note 3) stay unnamed: a name is never guessed.

    strong_name(identity, hits, lists_) -> entry or None   levels 1 to 3, which the class depends on (verdict.py)
    attribute(identity, cls, row, traces, automation, lists_, settings=None) -> Attribution
    env_candidates(hits, settings) -> rows for the labels table: the names environment hits point to

identity: verdict_identity.Identity; traces: the environment hits the class rests on (hard product and extension hits,
soft hits that counted); automation: the hard automation and spoofing hits.
"""
from collections import namedtuple
from dataclasses import dataclass

from agentcake import datafiles
from agentcake.detect.verdict_identity import IMPERSONATION, VERIFIED
from agentcake.detect.verdict_text import reason

SETTINGS_FILE = "data/verdict.json"
AGENT, MIXED, BOT = "agent", "mixed", "bot"
PRODUCT, EXTENSION, CLOUD_HOST = "product", "extension", "cloud_host"
AUTOMATED_ROW = "automated"
DECLARED = "declared"
CATEGORY_REASONS = {"automated": "env.automated", "extension": "env.extension-unnamed",
                    "cloud_browser": "env.cloud-browser", "local_agent": "behavior.local-agent"}
_Level = namedtuple("_Level", "level method entry")  # the level a name comes from, how, and the list entry


@dataclass(frozen=True)
class Attribution:
    """entry: the lists entry named, or None; certainty: certain or likely; method: signature, ip, rdns,
    product-rule, declared, extension-trace or automation-trace; category: without a name, see the module docstring;
    reasons: why (outranked or disagreeing names, a name taken from a trace, the category)."""

    entry: dict = None
    certainty: str = None
    method: str = None
    category: str = None
    reasons: tuple = ()


def strong_name(identity, hits, lists_):
    """A verified name, else the product all product rules agree on, else a declared one (None if impersonated)."""
    if identity.status == VERIFIED:
        return identity.entry
    products = _distinct(_entries(lists_, [hit.names for hit in hits if hit.kind == PRODUCT and hit.names]))
    if len(products) == 1:
        return products[0]
    return identity.entry


def attribute(identity, cls, row, traces, automation, lists_, settings=None):
    """The Attribution of a session whose class is already decided (see the module docstring)."""
    rule = (settings or datafiles.load(SETTINGS_FILE))["attribution"]
    if cls == BOT:
        level, method = ("verified", identity.via) if identity.status == VERIFIED else (DECLARED, DECLARED)
        return Attribution(identity.entry, rule["certainty"][level], method)
    if cls not in (AGENT, MIXED):
        return Attribution()
    levels = (("verified", identity.via, [identity.entry] if identity.status == VERIFIED else []),
              ("product_rule", "product-rule", _entries(lists_, [h.names for h in traces if h.kind == PRODUCT])),
              (DECLARED, DECLARED, [identity.declared] if identity.declared and identity.status != IMPERSONATION
               else []),
              ("extension_trace", "extension-trace", _entries(lists_, [h.suggests for h in traces])),
              ("automation_trace", "automation-trace", _entries(lists_, [h.names for h in automation])),
              ("automation_trace", DECLARED, [e for e in identity.generic if e["id"] not in rule["not_tools"]]))
    chosen, reasons = None, []
    for level, method, entries in levels:
        named = _distinct(entries)
        if len(named) > 1:
            reasons.append(reason("name.disagree", None, [e["id"] for e in named],
                                  names=", ".join(sorted(e["id"] for e in named))))
        elif named and chosen is None:
            chosen = _Level(level, method, named[0])
            reasons += _naming_reasons(level, method, named[0])
        elif named and named[0]["id"] != chosen.entry["id"]:
            reasons.append(reason("name.outranked", None, named[0]["id"], other=named[0]["name"],
                                  name=chosen.entry["name"], other_method=method,
                                  method=chosen.method))
    category = None if chosen else _category(identity, row, traces)
    category_reason = CATEGORY_REASONS.get(AUTOMATED_ROW if row == AUTOMATED_ROW else category)
    if category_reason:  # an agent range already has its reason from the verification layer
        reasons.append(reason(category_reason))
    if chosen:
        return Attribution(chosen.entry, rule["certainty"][chosen.level], chosen.method, None, tuple(reasons))
    return Attribution(category=category, reasons=tuple(reasons))


def env_candidates(hits, settings):
    """Names the environment layer points to: product rules, automation tools, extensions' own traces."""
    levels, out = settings["confidence"]["evidence"], []
    for hit in hits:
        if hit.names:
            method, kind = ("product-rule", "product_rule") if hit.kind == PRODUCT else ("automation-trace", "hard_env")
        elif hit.suggests:
            method, kind = "extension-trace", "extension_trace"
        else:
            continue
        out.append({"name": hit.names or hit.suggests, "layer": "environment", "method": method,
                    "certainty": levels[kind], "evidence": {"rule": hit.rule}})
    return out


def _entries(lists_, ids):
    return [entry for entry in (lists_.name(list_id) for list_id in ids if list_id) if entry]


def _distinct(entries):
    seen, out = set(), []
    for entry in entries:
        if entry and entry["id"] not in seen:
            seen.add(entry["id"])
            out.append(entry)
    return out


def _naming_reasons(level, method, entry):
    if level == "extension_trace":
        return [reason("name.from-trace", "page", entry["id"], name=entry["name"])]
    if level == "automation_trace":
        return [reason("name.tool", None, entry["id"], name=entry["name"], method=method)]
    return []


def _category(identity, row, traces):
    kinds = {hit.kind for hit in traces}
    if identity.infrastructure:
        return "infrastructure"
    if row == AUTOMATED_ROW:
        return "automated"
    if EXTENSION in kinds:
        return "extension"
    return "cloud_browser" if CLOUD_HOST in kinds else "local_agent"
