"""One conclusion per session from the four layers: class, Agent row, name, confidence, segments and reasons.

The synthesis of our research on agent signals: four layers (name, verification, environment, behaviour), signatures
name the infrastructure but never who acts at a moment, and only a certain name makes a Bot. Its conflict table is
the specification and tests/test_verdict.py pins it rule by rule (the browser names: test_verdict_browsers.py).

 0  Exclusion. A page requested as a prefetch or prerender (the server half's token carries Sec-Purpose) keeps its
    page half, but its server half is not used; a page prerendered and never shown is left out; a session with no
    page left is no visit ("excluded").
 1, 2  Name and verification: verdict_identity.py. A verified signature or published range names the infrastructure
    (certain), never who acts at a given moment; a failed check is impersonation: no name, Automated browser.
 3  Bot: a listed program that is not an agent, its name not impersonated, is a Bot (verified or self-reported
    only) and the behaviour model is not run. Guessed patterns never make a Bot.
 4  Environment: hard automation and spoofing traces are not overturned by behaviour: an Agent, never Mixed, in its
    name's row (attribute.py), else the Automated browser row. Any other hard trace (a product rule, an extension acting
    on the page) says an agent is here, like a signature: a human may take over; a rule naming a browser people also use
    by hand only names it. Soft traces count only with company: another trace that is not weak, or the behaviour model
    judging an agent; alone, human behaviour gives Human and anything else Not sure. Weak traces only go in reasons.
 5  Behaviour (the behaviour model through behavior.py): with agent evidence, a long enough human run (verdict.json "mixed")
    makes the session Mixed; without any, Mixed needs long enough runs of both (a hand-off lies between them, and
    the timeline marks it). Behaviour alone judging an agent is "possibly an agent on the visitor's own computer":
    AI in a real browser, no name. Assistive-tool signs keep the behaviour's agent judgement from counting (Not
    sure). Only weak signals: Human.
 6  Confidence (verdict.json "confidence"): certain, likely, possible or unsure.
 7  Crawler-like patterns (crawler.py) and the other weak signals (weak.py) only add reasons.
 8  Each of the interface's four layers gets a state; a layer that did not run says why. The name layer's is the
    list category of the name the session goes by; an impersonated name is an agent's, whatever its list says.
The name, or the category when no product can be named, comes from attribute.py (its name priority).

    decide(evidence, settings=None, lists_=None) -> verdict (a dict, below)
    needs_behavior(evidence, settings=None, lists_=None) -> (False, "bot" | "excluded") or (True, None)
    judge(evidence, raw=None, rrweb=None, model=None, settings=None, lists_=None) -> decide() after behavior.run()

Evidence, one session, every layer's result already computed (nothing here reads the database or the network):
    mode         "local" (every visit is 127.0.0.1: no verification layer) or "server"
    pages        [{"t": start ms, "sp": the server half's Sec-Purpose, "prerendered": bool, "shown": bool}], in the
                 order of env_signals' pages (the page indexes of the environment hits)
    user_agents  {"page" | "collector" | "server": [User-Agent]}; platform: navigator.platform
                 (verdict_identity.claims_from_signals() reads both from env_signals' dict)
    signatures   {"collector" | "server": webbotauth.Verification}  (the server half carries Signature-Agent only)
    network      lists.match_ip() of the visitor's address, None when none was seen; rdns: {"name", "verified"}
    env          env_rules.evaluate() of the session's signals; None when it recorded none (cake 0.3.x)
    behavior     behavior.run()'s result, None when it did not run; touch: a phone or tablet
    marks        markers.turn_spans() of the session's signals: when an agent product's indicator said its agent was
                 working, which judge() hands to the behaviour timeline (it gives those actions to the agent)
    assistive    behavior.assistive_signs(); visits: start ms of the same network's earlier sessions
    weak         weak.facts() of the session (evidence.py adds address_sessions), None when not read

Verdict:
    class        human | agent | mixed | not_sure | too_little_data | bot | excluded
    row          "ai" (AI in a real browser) or "automated" (Automated browser) for agent and mixed, else None
    judging      the judging.en.json class whose sentence explains it (JUDGING_KEYS): an agent's by its Agent row, named
                 or not (a name is the third level, never a class of its own)
    name, display_name, operator, kind       the list entry of a named agent or bot, else None (operator also for
                 an operator's agent range); name_certainty: certain | likely; name_method: how it was named
    category     without a name: infrastructure | automated | extension | cloud_browser | local_agent (attribute.py):
                 where it runs, which its reasons say; the interface calls such an agent Unnamed
    verification verified | self_reported | unverifiable | impersonation for a declared name, else None
    impersonating the list id a failed check unmasked; confidence: certain | likely | possible | unsure (or None)
    segments     [{"who", "model_who", "start", "end", "n", "p"}]: behaviour runs, "who" as the class decides it
    shares       {"human", "agent", "unsure"}: shares of the actions by "who"; handoffs: Mixed only
    layers       {"name" | "verify" | "environment" | "behavior": {"state", "why"?, "leans", "percent"}}, as the
                 interface reads them; percent: the session's chance of being right (confidence.py, 1 to 99)
    reasons      [{"id", "layer", "source", "value", "grade", "tone", "text", ...}], layer by layer
    candidates   [{"name", "layer", "method", "certainty", "evidence"}]: every name a layer found (labels table)
"""
import dataclasses

from agentcake import datafiles
from agentcake.detect import (attribute, behavior, confidence, crawler, lists, model as behavior_model,
                              verdict_identity, verdict_marks, weak)
from agentcake.detect.verdict_identity import IMPERSONATION, SELF_REPORTED, VERIFIED
from agentcake.detect.verdict_text import reason
from agentcake.units import MS_PER_S, PERCENT

SETTINGS_FILE = "data/verdict.json"
HUMAN, AGENT, MIXED, NOT_SURE, TOO_LITTLE, BOT, EXCLUDED = (
    "human", "agent", "mixed", "not_sure", "too_little_data", "bot", "excluded")
UNSURE, NO_HIT, OFF = "unsure", "no_hit", "off"
AI_ROW, AUTOMATED_ROW = "ai", "automated"
JUDGING_KEYS = ("human", "agent_ai", "agent_automated", "bot", "mixed", "too_little_data", "not_sure", "excluded")
HARD, SOFT, WEAK = "hard", "soft", "weak"
PRODUCT, EXTENSION, CLOUD_HOST = "product", "extension", "cloud_host"
SERVER, PAGE = "server", "page"
LAYER_ORDER = ("exclusion", "name", "verify", "environment", "behavior", "weak")
INTERFACE_LAYERS = ("name", "verify", "environment", "behavior")  # web/src/data/schema/session.schema.json
STRENGTH_ORDER = (HARD, SOFT, WEAK)
WHO = (HUMAN, AGENT, UNSURE)
SOFT_KIND_EVIDENCE = {CLOUD_HOST: "cloud_host", EXTENSION: "extension_trace"}


def load_settings():
    return datafiles.load(SETTINGS_FILE)


def needs_behavior(evidence, settings=None, lists_=None):
    """Whether the behaviour model should run: not for a session with no page left, nor for a Bot known by name."""
    settings = settings or load_settings()
    pages = evidence.get("pages") or []
    if pages and len(_exclusion(pages, settings)[0]) == len(pages):
        return False, EXCLUDED
    if _is_bot(verdict_identity.identify(evidence, lists_, settings)):
        return False, BOT
    return True, None


def judge(evidence, raw=None, rrweb=None, model=None, settings=None, lists_=None):
    """decide() after running the behaviour layer on the session's events when it needs it (needs_behavior)."""
    needed, _ = needs_behavior(evidence, settings, lists_)
    result = behavior.run(raw=raw, rrweb=rrweb, touch=bool(evidence.get("touch")), model=model,
                          turns=evidence.get("marks") or ()) if needed else None
    assistive = behavior.assistive_signs(raw, settings) if raw else None
    return decide(dict(evidence, behavior=result, assistive=assistive), settings, lists_)


def decide(evidence, settings=None, lists_=None):
    """The verdict of one session's evidence (see the module docstring)."""
    settings = settings or load_settings()
    lists_ = lists_ or lists.current()
    pages = evidence.get("pages") or []
    dropped, no_server, reasons = _exclusion(pages, settings)
    if pages and len(dropped) == len(pages):
        return confidence.annotate(_excluded(reasons + [reason("exclude.all")]), evidence)
    env = evidence.get("env")  # None: the session recorded no environment signals (cake 0.3.x)
    identity = verdict_identity.identify(evidence, lists_, settings)
    hits = attribute.unexplained(_usable_hits(env.hits if env else (), dropped, no_server), identity)
    case = _Case(identity, hits, evidence, settings, lists_)
    reasons += list(identity.reasons) + attribute.env_reasons(hits, case.browsers) + case.reasons
    kept = [page.get("t") for index, page in enumerate(pages) if index not in dropped]
    crawler_like = crawler.reason(crawler.patterns(kept, evidence.get("network"), evidence.get("visits") or (),
                                                   settings), settings)
    candidates = list(identity.candidates) + attribute.env_candidates(hits, settings)
    reasons += ([crawler_like] if crawler_like else []) + weak.reasons(evidence.get("weak"), settings)
    return confidence.annotate(_verdict(case, reasons, candidates, settings), evidence)  # the percents


# ---------------------------------------------------------------- rule 0: exclusion
def _purpose(sec_purpose, settings):
    """The Sec-Purpose token that makes a page no visit yet ("prefetch;prerender" is a prerender), or None."""
    tokens = {token.strip().lower() for part in (sec_purpose or "").split(",") for token in part.split(";")}
    found = [token for token in settings["exclude"]["sec_purpose"] if token in tokens]
    return found[-1] if found else None


def _exclusion(pages, settings):
    """(pages left out, pages whose server half is not used, reasons): page indexes, as the hits count them."""
    dropped, no_server, reasons = set(), set(), []
    for index, page in enumerate(pages):
        if page.get("prerendered") and page.get("shown") is False:
            dropped.add(index)
            reasons.append(reason("exclude.never-shown", PAGE, index, page=index + 1))
            continue
        purpose = _purpose(page.get("sp"), settings)
        if purpose:
            no_server.add(index)
            reasons.append(reason("exclude.prefetch", SERVER, page.get("sp"), page=index + 1, purpose=purpose))
    return dropped, no_server, reasons


def _usable_hits(hits, dropped, no_server):
    """The hits that still hold on a page that counts; a session-wide hit holds on no page and stays."""
    usable = []
    for hit in hits:
        if hit.pages is None:
            usable.append(hit)
            continue
        gone = dropped | (no_server if hit.half == SERVER else set())
        pages = tuple(index for index in hit.pages if index not in gone)
        if pages:
            usable.append(hit if pages == tuple(hit.pages) else dataclasses.replace(hit, pages=pages))
    return usable


def _excluded(reasons):
    return {"class": EXCLUDED, "row": None, "judging": EXCLUDED, "name": None, "display_name": None,
            "operator": None, "kind": None, "name_certainty": None, "name_method": None, "category": None,
            "verification": None, "impersonating": None, "confidence": None,
            "segments": [], "shares": _shares([]), "handoffs": [],
            "layers": {layer: {"state": OFF, "why": EXCLUDED} for layer in INTERFACE_LAYERS},
            "reasons": reasons, "candidates": []}


def _is_bot(identity):
    """A listed program that is not an agent; an impersonated name never reaches here (identify() drops it)."""
    return bool(identity.entry) and identity.entry["category"] == BOT


# ---------------------------------------------------------------- rules 3 to 5: the class
class _Case:
    """The class of one session and what it rests on: cls, row, the kinds of evidence (kinds), reasons; naming is
    attribute.py's name for it."""

    def __init__(self, identity, hits, evidence, settings, lists_):
        self.identity, self.settings, self.lists = identity, settings, lists_
        self.result = evidence.get("behavior")
        self.env_recorded = evidence.get("env") is not None
        self.assistive = evidence.get("assistive")
        self.session_start = next((page.get("t") for page in evidence.get("pages") or [] if page.get("t")), None)
        overruling = settings["overruling_kinds"]
        self.overruling = [h for h in hits if h.strength == HARD and h.kind in overruling]
        self.browsers = attribute.browser_rules(hits, lists_)  # they name where the page is open, never who acts
        self.present = [h for h in hits if h.strength == HARD and h.kind not in overruling and h not in self.browsers]
        self.soft = [h for h in hits if h.strength == SOFT]
        self.reasons, self.traces = [], []
        self.cls, self.row, self.kinds = self._classify()
        self.naming = attribute.attribute(identity, self.cls, self.row, self.traces, self.overruling, lists_, settings,
                                          marked=bool(((self.result or {}).get("timeline") or {}).get("marks")))
        self.reasons = self._behavior_reasons() + self.reasons + list(self.naming.reasons)

    @property
    def verdict(self):
        return (self.result or {}).get("verdict")

    @property
    def runs(self):
        return ((self.result or {}).get("timeline") or {}).get("runs") or []

    @property
    def handoffs(self):
        return ((self.result or {}).get("timeline") or {}).get("handoffs") or []

    def long_runs(self, who):
        """The runs of `who` long enough to count as one side of a Mixed session (verdict.json "mixed")."""
        rule = self.settings["mixed"]
        return [r for r in self.runs if r["who"] == who and r["n"] >= rule["min_actions"]
                and (r["end"] - r["start"]) / MS_PER_S >= rule["min_span_s"]]

    def _classify(self):
        identity, says_agent = self.identity, self.verdict == AGENT and not self.assistive
        if self.assistive and self.verdict == AGENT:
            self.reasons.append(reason("behavior.assistive", PAGE, self.assistive))
        if _is_bot(identity):
            self.reasons.append(reason("behavior.not-run-bot"))
            return BOT, None, list(identity.evidence)
        # a soft trace counts with another trace that is not weak (any other rule), or with agent behaviour
        others = {h.rule for h in self.overruling + self.present + self.soft}
        soft_ok = bool(self.soft) and (len(others) > 1 or says_agent)
        traces = self.present + (self.soft if soft_ok else [])
        self.traces = traces + self.browsers  # what names the agent: a browser's own product rule too
        named = attribute.strong_name(identity, self.present, self.lists)
        if self.overruling or identity.status == IMPERSONATION or (identity.generic and not named):
            return self._automated(named)
        if named or identity.infrastructure or traces:
            kinds = attribute.class_evidence(identity) + [self._trace_kind(h) for h in traces] + ["behavior"] * says_agent
            row = attribute.row_of(named, identity, self.browsers, self.lists) or _env_row(traces, self.settings) or AI_ROW
            return (MIXED if self.long_runs(HUMAN) else AGENT), row, kinds
        if self.soft:
            self.reasons.append(reason("env.soft-alone"))
            return (HUMAN, None, ["behavior"]) if self.verdict == HUMAN else (NOT_SURE, None, [])
        return self._behavior_alone()

    def _trace_kind(self, hit):
        if hit.strength == HARD:
            return "product_rule" if hit.kind == PRODUCT else "hard_env"
        return SOFT_KIND_EVIDENCE.get(hit.kind, "soft_env")

    def _automated(self, named):
        """Rule 4's hard automation, an impersonated name or a tool anyone runs: behaviour does not overturn it."""
        kinds = attribute.class_evidence(self.identity) + ["hard_env"] * bool(self.overruling)
        if self.identity.generic and not self.identity.evidence:
            kinds.append("declared")
        row = attribute.row_of(named, self.identity, self.browsers, self.lists) or AUTOMATED_ROW
        if self.verdict == HUMAN:  # only the model's own conclusion is "judged the session human"
            self.reasons.append(reason("behavior.overruled"))
        return AGENT, row, kinds

    def _behavior_alone(self):
        verdict = self.verdict
        if self.assistive and verdict == AGENT:
            return NOT_SURE, None, []
        if self.long_runs(HUMAN) and verdict == AGENT:  # a confirmed agent part beside a human's (11/13)
            return MIXED, AI_ROW, ["behavior"]
        if verdict == AGENT:
            return AGENT, AI_ROW, ["behavior"]
        if verdict == HUMAN:
            return HUMAN, None, ["behavior"]
        return (NOT_SURE if verdict == UNSURE else TOO_LITTLE), None, []

    def _model_said(self, result):
        """The behaviour model's verdict in words: its share of segments, and for an agent what decided it (with the
        kinds of agent evidence it saw, which its words name)."""
        pct = {f"{who}_pct": round(share * PERCENT) for who, share in _segment_shares(result).items()}
        if result["verdict"] == AGENT:
            return reason("behavior.agent", PAGE, result["basis"], basis=list(result.get("basis") or ["rules"]),
                          kinds=list(result["evidence"].get("agent_kinds") or []), **pct)
        one_kind = result["evidence"].get("one_kind")
        if result["verdict"] == UNSURE and one_kind:  # agent evidence of one kind only (model.py corroboration)
            return reason("behavior.one-kind", PAGE, one_kind, kind=one_kind)
        said = {HUMAN: "behavior.human", UNSURE: "behavior.unsure"}[result["verdict"]]
        return reason(said, PAGE, result["verdict"], **pct)

    def _behavior_reasons(self):
        result = self.result
        if result is None or self.cls == BOT:
            return []
        if result["verdict"] == TOO_LITTLE:
            if result["evidence"].get("reason") == "touch":
                return [reason("behavior.touch", PAGE)]
            minimum = behavior_model.load_params()["min_actions"]
            return [reason("behavior.too-little-data", PAGE, result["n_actions"], n=result["n_actions"], min=minimum)]
        out = [self._model_said(result)] + self._indicator_reasons(result)
        if self.cls == MIXED:
            start = self.session_start or min(r["start"] for r in self.runs)
            out += [reason("behavior.handoff", PAGE, h["t"], to=h["to"], at=round((h["t"] - start) / MS_PER_S),
                           **{"from": h["from"]}) for h in self.handoffs]
        elif self.cls in (AGENT, HUMAN):
            short = [r for r in self.runs if r["who"] in (HUMAN, AGENT) and r["who"] != self.cls
                     and r not in self.long_runs(r["who"])]
            out += [reason("behavior.short-run", PAGE, r["n"], who=r["who"], n=r["n"],
                           span=round((r["end"] - r["start"]) / MS_PER_S, 1)) for r in short]
        return out

    def _indicator_reasons(self, result):
        """One reason per turn span the timeline was given (an indicator said its agent was working), with its times
        from the session's start (verdict_marks.py)."""
        spans = (result.get("timeline") or {}).get("marks") or []
        if not spans:
            return []
        start = self.session_start or min([r["start"] for r in self.runs] + [s["from"] for s in spans])
        return verdict_marks.reasons(result["timeline"], start)


def _segment_shares(result):
    """The model's own shares of its action segments (judge_session's evidence), else the timeline's."""
    found = {who: result["evidence"].get(f"{who}_share") for who in WHO}
    return found if None not in found.values() else result["timeline"]["shares"]


def _env_row(hits, settings):
    rows = {settings["env_rows"][hit.kind] for hit in hits}
    return AI_ROW if AI_ROW in rows else (AUTOMATED_ROW if rows else None)


# ---------------------------------------------------------------- rules 6 and 8: the result
def _confidence(case, settings):
    levels, table = settings["confidence"]["levels"], settings["confidence"]["evidence"]
    if case.cls in (NOT_SURE, TOO_LITTLE) or not case.kinds:
        return levels[-1]
    best = min(levels.index(table[kind]) for kind in case.kinds)
    if case.cls == MIXED:
        best = max(best, levels.index(table["behavior"]))
    return levels[best]


def _segments(case):
    """The behaviour runs with "who" as the class decides it: an Agent's or a Human's decided runs are all theirs."""
    whole = case.cls if case.cls in (AGENT, HUMAN) else None
    return [{"who": whole if (whole and r["who"] != UNSURE) else r["who"], "model_who": r["who"], "start": r["start"],
             "end": r["end"], "n": r["n"], "p": r["p"]} for r in case.runs]


def _shares(segments):
    total = sum(s["n"] for s in segments)
    if not total:
        return {HUMAN: 0.0, AGENT: 0.0, UNSURE: 1.0}
    return {who: sum(s["n"] for s in segments if s["who"] == who) / total for who in WHO}


def _layers(case):
    identity, result = case.identity, case.result
    # an impersonated name (never an entry too) is an automation lying about what it is (rules 1 to 3): not a Bot
    name_state = (identity.entry["category"] if identity.entry and not identity.entry.get("browser")
                  else AGENT if identity.impersonating or identity.generic else NO_HIT)
    counted = case.overruling or case.present or (case.soft and case.cls in (AGENT, MIXED))
    environment = {"state": AGENT if counted else (UNSURE if case.soft else NO_HIT)}
    if not case.env_recorded:
        environment = {"state": OFF, "why": "not_recorded"}
    if result is None or case.cls == BOT:
        behavior_layer = {"state": OFF, "why": BOT if case.cls == BOT else "no_events"}
    elif result["verdict"] == TOO_LITTLE:
        behavior_layer = {"state": UNSURE, "why": result["evidence"].get("reason")}
    else:
        # Human + agent only in a session that is one (hand-offs) and where behaviour itself saw both sides
        both = case.long_runs(HUMAN) and (result["verdict"] == AGENT or case.long_runs(AGENT))
        behavior_layer = {"state": MIXED if case.cls == MIXED and both else result["verdict"]}
    return {"name": {"state": name_state}, "verify": identity.verify_layer, "environment": environment,
            "behavior": behavior_layer}


def _verdict(case, reasons, candidates, settings):
    naming, identity = case.naming, case.identity
    entry = naming.entry
    segments = _segments(case) if case.cls != BOT else []
    verification = None
    if identity.status == IMPERSONATION:
        verification = IMPERSONATION
    elif entry and identity.entry and entry["id"] == identity.entry["id"]:
        verification = SELF_REPORTED if (case.cls == BOT and identity.status != VERIFIED) else identity.status
    judging = case.cls if case.cls != AGENT else ("agent_automated" if case.row == AUTOMATED_ROW else "agent_ai")
    operator = entry.get("operator") if entry else (identity.infrastructure or {}).get("operator")
    rank = {layer: i for i, layer in enumerate(LAYER_ORDER)}
    ordered = sorted(reasons, key=lambda r: (rank[r["layer"]], STRENGTH_ORDER.index(r.get("strength", HARD))))
    return {"class": case.cls, "row": case.row if case.cls in (AGENT, MIXED) else None, "judging": judging,
            "name": entry["id"] if entry else None, "display_name": entry["name"] if entry else None,
            "operator": operator, "kind": entry["kind"] if entry else None, "name_certainty": naming.certainty,
            "name_method": naming.method, "category": naming.category, "verification": verification,
            "impersonating": identity.impersonating["id"] if identity.impersonating else None,
            "confidence": _confidence(case, settings), "segments": segments, "shares": _shares(segments),
            "handoffs": list(case.handoffs) if case.cls == MIXED else [], "layers": _layers(case),
            "reasons": ordered, "candidates": candidates}
