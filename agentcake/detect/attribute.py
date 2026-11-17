"""Which agent or bot a session is: its name and how sure, or its category when no product can be named.

Name priority, highest first:
  1 verified: a Web Bot Auth signature checked with the signer's key, the operator's published range, reverse DNS;
  2 a page product rule (env_rules.json, kind product: Muse, Grok Bot, Codex, Cursor, Cloudflare Browser Run, ...);
  3 a self-reported name: the User-Agent, navigator.platform or Signature-Agent, when they agree;
  4 an extension's own trace that points to its product (env.ext.closed-shadow-host: Claude in Chrome), once the
    trace counts (it is soft: agent behaviour or another trace must back it);
  5 an automation tool's own trace (Playwright, Puppeteer or Selenium globals) or the tool's User-Agent token;
  6 no product, a category: infrastructure (an operator's published agent range), automated (Automated browser),
    extension (an extension drove the page), cloud_browser (a cloud computer that does not say who runs it) or
    local_agent (behaviour alone: possibly an agent on the visitor's own computer). A category says where the agent
    runs, which its reason tells; it never names it: the interface calls the agent Unnamed. When an agent product's
    indicator said its agent was working (marked), local_agent's reason, that only behaviour points to an agent and
    the page shows no agent trace, is not given: the behaviour reasons tell the indicator's span instead.
The highest level that names a product wins, with the certainty verdict.json "attribution" gives that level (a verified
name is certain; a rule or a trace goes stale when its product changes, so it is likely). A lower level pointing to
another product is listed as outranked; a level whose evidence names several products names none. A Bot keeps
the list entry that made it one. Products without a trace of their own (browser-use, Playwright MCP and Stagehand
drive Playwright or the DevTools protocol) stay unnamed: a name is never guessed.

A browser people also use by hand (a kind marked "browser" in kinds.json, such as an AI desktop app's own browser,
named by its User-Agent or by a product rule) says where the page is open, not who acts in it. Its name never counts
toward the class (strong_name, class_evidence; the name layer finds no agent in it) and its product rule is a fact for
neither side (env_reasons): automation traces and behaviour decide, as in any other browser, and when they find an
agent, the browser's name is the agent's (levels 2 and 3) unless another product's rule names it. A rule its list entry
says that browser matches by design (names.json "by_design", measured) is left out (unexplained): it says nothing about
automation in that browser.

    strong_name(identity, hits, lists_) -> entry or None   levels 1 to 3, which the class depends on (verdict.py)
    attribute(identity, cls, row, traces, automation, lists_, settings=None, marked=False) -> Attribution
    env_candidates(hits, settings) -> rows for the labels table: the names environment hits point to
    browser_rules(hits, lists_) -> the hard product rules among hits that name a browser people also use by hand
    unexplained(hits, identity) -> the hits without the rules the declared browser matches by design
    class_evidence(identity) -> the kinds of evidence the name and verification layers give the class
    row_of(named, identity, browsers, lists_) -> the Agent row of the name the class rests on, else the browser's
    env_reasons(hits, browsers) -> the environment layer's reasons, a browser's own product rule in no side's tone

identity: verdict_identity.Identity; traces: the environment hits the class rests on (hard product and extension hits,
soft hits that counted); automation: the hard automation and spoofing hits; marked: whether the behaviour timeline was
given an indicator's turn span (markers.turn_spans).
"""
from collections import namedtuple
from dataclasses import dataclass

from agentcake import datafiles
from agentcake.detect.verdict_identity import IMPERSONATION, VERIFIED
from agentcake.detect.verdict_text import NO_TONE, env_reason, reason

SETTINGS_FILE = "data/verdict.json"
AGENT, MIXED, BOT = "agent", "mixed", "bot"
HARD = "hard"  # env_rules.json strength of a trace that counts alone
PRODUCT, EXTENSION, CLOUD_HOST = "product", "extension", "cloud_host"
AUTOMATED_ROW = "automated"
DECLARED = "declared"
LOCAL_AGENT = "local_agent"
CATEGORY_REASONS = {"automated": "env.automated", "extension": "env.extension-unnamed",
                    "cloud_browser": "env.cloud-browser", LOCAL_AGENT: "behavior.local-agent"}
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
    """A verified name, else the product all product rules agree on, else a declared one (None if impersonated); a
    browser people also use by hand is none of them (see the module docstring)."""
    if identity.status == VERIFIED:
        return identity.entry
    products = [entry for entry in _distinct(_entries(lists_, [hit.names for hit in hits
                                                                 if hit.kind == PRODUCT and hit.names]))
                if not entry.get("browser")]
    if len(products) == 1:
        return products[0]
    return None if _is_browser(identity.entry) else identity.entry


def browser_rules(hits, lists_):
    """The hard product rules among the hits that name a browser people also use by hand."""
    return [hit for hit in hits if hit.strength == HARD and hit.kind == PRODUCT and hit.names
            and _is_browser(lists_.name(hit.names))]


def unexplained(hits, identity):
    """The hits, without those the browser the session declares matches by design (its list entry's by_design)."""
    explained = set((identity.declared or {}).get("by_design") or ())
    return [hit for hit in hits if hit.rule not in explained]


def class_evidence(identity):
    """The kinds of evidence the name and verification layers give the class: a browser's declared name gives none,
    the published agent range its address is in still counts."""
    if _is_browser(identity.entry) and identity.status != VERIFIED:
        return [kind for kind in identity.evidence if kind != DECLARED]
    return list(identity.evidence)


def row_of(named, identity, browsers, lists_):
    """The Agent row of the name the class rests on, else of the browser the page is open in, else None."""
    declared = [identity.declared] if _is_browser(identity.declared) else []
    found = _distinct(declared + _entries(lists_, [hit.names for hit in browsers]))
    shown = named or (found[0] if len(found) == 1 else None)
    return (shown or {}).get("row")


def env_reasons(hits, browsers):
    """The environment layer's reasons: a browser's own product rule says where the page is open, for neither side."""
    return [dict(env_reason(hit), tone=NO_TONE) if hit in browsers else env_reason(hit) for hit in hits]


def attribute(identity, cls, row, traces, automation, lists_, settings=None, marked=False):
    """The Attribution of a session whose class is already decided (see the module docstring)."""
    rule = (settings or datafiles.load(SETTINGS_FILE))["attribution"]
    if cls == BOT:
        level, method = ("verified", identity.via) if identity.status == VERIFIED else (DECLARED, DECLARED)
        return Attribution(identity.entry, rule["certainty"][level], method)
    if cls not in (AGENT, MIXED):
        return Attribution()
    levels = (("verified", identity.via, [identity.entry] if identity.status == VERIFIED else []),
              ("product_rule", "product-rule",
               _agents_first(_entries(lists_, [h.names for h in traces if h.kind == PRODUCT]))),
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
    if marked and category_reason == CATEGORY_REASONS[LOCAL_AGENT]:
        category_reason = None  # an indicator in the page said an agent worked: behaviour is not alone
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


def _is_browser(entry):
    return bool(entry and entry.get("browser"))


def _agents_first(entries):
    """The entries that are no browser people also use by hand, else all of them: a browser's own product rule names
    the agent only when no other product rule does (strong_name leaves it out the same way)."""
    return [entry for entry in entries if not _is_browser(entry)] or entries


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
    return "cloud_browser" if CLOUD_HOST in kinds else LOCAL_AGENT
