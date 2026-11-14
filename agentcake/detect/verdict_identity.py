"""Who a session says it is, and whether that holds: the name and verification layers of the verdict.

Name layer (step 1): what the session declares, read from the User-Agent of each half
(the page's navigator.userAgent, cake.js's requests to the collect endpoint, the site's server half), from
navigator.platform and from the signer that Signature-Agent names, each looked up in the bundled lists (lists.py).
Names count only when they agree (botscent's rule, src/core/verdict.ts, MIT, 7f948003: the idea, not the
code). A tool anyone can run (a kind marked generic in kinds.json: HeadlessChrome, curl, Cloudflare Browser Run)
names no product; it only says that the browser is automated.

Verification layer (step 2): a declared name holds when something that cannot be claimed confirms it: a Web Bot Auth
signature verified with the signer's bundled key (webbotauth.py), the operator's published address range
(ip_ranges.json "verifies"), or reverse DNS when such a check is given. Impersonation (after Known Agents'
definition), and so no name: a name that a published range could verify, seen from an address outside it, and a
signature that does not verify. Never impersonation, only self-reported: a missing, expired or unknown key, a
signature outside its time window, local mode (every visit is 127.0.0.1), no address, or a name with nothing to
check it against. A signature that does not verify but covers what a proxy in front of the site may rewrite
(verdict.json "signature_proxy_components") could not be verified, which is not impersonation either.

    identify(evidence, lists_=None, settings=None) -> Identity
    claims_from_signals(signals) -> {"user_agents": {half: [User-Agent]}, "platform"}   from env_signals' dict

Input: the evidence keys "mode", "user_agents", "platform", "signatures", "network" and "rdns" (verdict.py's
docstring describes them). Output: an Identity; verdict.py lists its reasons and candidates as they are.
"""
from dataclasses import dataclass, field

from agentcake import datafiles
from agentcake.detect import lists, webbotauth
from agentcake.detect.verdict_text import reason

SETTINGS_FILE = "data/verdict.json"
KINDS_FILE = "data/lists/kinds.json"
EDGE_FILE = "data/edge.json"  # the header names of the server half, by role
HALVES = ("page", "collector", "server")
PAGE = "page"
LOCAL_MODE = "local"
VERIFIED, SELF_REPORTED, UNVERIFIABLE, IMPERSONATION = "verified", "self_reported", "unverifiable", "impersonation"
AGENT, BOT, NO_HIT, UNSURE, OFF = "agent", "bot", "no_hit", "unsure", "off"  # the interface's layer states
CANDIDATE_LAYER = {"ua": "name", "platform": "name", "signature-agent": "name", "signature": "verify", "ip": "verify",
                   "rdns": "verify"}


@dataclass(frozen=True)
class Identity:
    """What the name and verification layers found.

    entry: the lists entry the session goes by (lists.Lists.match_ua's dict), or None; status: verified,
    self_reported, unverifiable or impersonation for that name (None without one); via: signature, ip or rdns when
    verified; evidence: the kinds of evidence behind the name or the infrastructure (verdict.json "confidence");
    impersonating: the entry a failed check unmasked; infrastructure: the published agent range holding the address
    when nothing names the agent; generic: entries of tools anyone runs that the session declares; declared: the name
    the declarations agree on, whatever its check found (attribute.py says when a verified name outranks it);
    verify_layer: the verification layer's state for the interface ({"state", "why"?}); reasons, candidates: as
    verdict.py lists them.
    """

    entry: dict = None
    status: str = None
    via: str = None
    evidence: tuple = ()
    impersonating: dict = None
    infrastructure: dict = None
    generic: tuple = ()
    declared: dict = None
    verify_layer: dict = field(default_factory=dict)
    reasons: tuple = ()
    candidates: tuple = ()


@dataclass(frozen=True)
class _Claim:
    entry: dict
    halves: tuple
    method: str  # ua, platform or signature-agent


class _Found:
    """Reasons and candidates as they are found, each once."""

    def __init__(self, settings):
        self.levels = settings["confidence"]["evidence"]
        self.reasons, self.candidates = [], []

    def add(self, item):
        if item not in self.reasons:
            self.reasons.append(item)

    def candidate(self, entry, method, kind, **evidence):
        row = {"name": entry["id"], "layer": CANDIDATE_LAYER[method], "method": method,
               "certainty": self.levels[kind], "evidence": evidence}
        if all((c["name"], c["layer"], c["method"]) != (row["name"], row["layer"], row["method"])
               for c in self.candidates):
            self.candidates.append(row)


def claims_from_signals(signals):
    """The User-Agents of each half and navigator.platform, from env_signals' dict (from_cake or from_lab)."""
    ua_header = datafiles.load(EDGE_FILE)["headers"]["user_agent"]
    pages = signals.get("pages") or []
    collector = ((signals.get("collect") or {}).get("headers") or {}).get(ua_header) or {}
    return {"user_agents": {"page": _distinct((page.get("env") or {}).get("userAgent") for page in pages),
                            "collector": _distinct(collector.get("values") or []),
                            "server": _distinct(((page.get("nav") or {}).get("headers") or {}).get(ua_header)
                                                for page in pages)},
            "platform": next((page["env"]["platform"] for page in pages if (page.get("env") or {}).get("platform")),
                             None)}


def identify(evidence, lists_=None, settings=None):
    """The Identity of one session's evidence (see the module docstring)."""
    lists_ = lists_ or lists.current()
    settings = settings or datafiles.load(SETTINGS_FILE)
    found = _Found(settings)
    signature, signature_half = _best_signature(evidence.get("signatures") or {})
    claims = (_ua_claims(evidence.get("user_agents") or {}, lists_, found)
              + _platform_claims(evidence.get("platform"), lists_, found)
              + _signer_claims(signature, signature_half, lists_, found))
    generic = tuple(_distinct_entries(c.entry for c in claims if _is_generic(c.entry)))
    named = _agreed_name([c for c in claims if not _is_generic(c.entry)], found)
    result = _verify(named, signature, signature_half, evidence, lists_, settings, found)
    return Identity(generic=generic, declared=named, verify_layer=_verify_layer(evidence, result),
                    reasons=tuple(found.reasons), candidates=tuple(found.candidates), **result)


# ---------------------------------------------------------------- name layer
def _distinct(values):
    out = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _distinct_entries(entries):
    seen, out = set(), []
    for entry in entries:
        if entry["id"] not in seen:
            seen.add(entry["id"])
            out.append(entry)
    return out


def _is_generic(entry):
    return bool(datafiles.load(KINDS_FILE)["kinds"][entry["kind"]].get("generic"))



def _ua_claims(user_agents, lists_, found):
    """One claim per name the User-Agents declare, with the halves that declare it; each forged shape once."""
    seen, hints = {}, {}
    for half in HALVES:
        for ua in user_agents.get(half) or []:
            for hint in lists_.ua_hints(ua):
                hints.setdefault(hint["id"], (hint, half))
            match = lists_.match_ua(ua)
            if match is None:
                continue
            if match["id"] is None:
                found.add(reason("name.ua-conflict", half, match["conflict"], half=half,
                                 names=", ".join(match["conflict"])))
                continue
            seen.setdefault(match["id"], (match, []))[1].append(half)
    for hint, half in hints.values():
        found.add(reason("name.ua-hint", half, hint["id"], hint=hint["name"]))
    claims = []
    for match, halves in seen.values():
        halves = tuple(_distinct(halves))
        reason_id = "name.ua-generic" if _is_generic(match) else "name.ua"
        found.add(dict(reason(reason_id, halves[0], match["matched"], half=list(halves), name=match["name"],
                              kind_label=match["kind_label"]), halves=list(halves)))
        found.candidate(match, "ua", "declared", halves=list(halves), matched=match["matched"])
        claims.append(_Claim(match, halves, "ua"))
    return claims


def _platform_claims(platform, lists_, found):
    entry = lists_.match_platform(platform)
    if not entry:
        return []
    found.add(reason("name.platform", PAGE, platform, platform=platform, name=entry["name"]))
    found.candidate(entry, "platform", "declared", platform=platform)
    return [_Claim(entry, (PAGE,), "platform")]


def _best_signature(signatures):
    """(the Verification with the best outcome, its half); halves in HALVES order break ties."""
    best, best_half = None, None
    for half in HALVES:
        result = signatures.get(half)
        if result is None or result.outcome == webbotauth.NONE:
            continue
        if best is None or (webbotauth.OUTCOME_ORDER.index(result.outcome)
                            > webbotauth.OUTCOME_ORDER.index(best.outcome)):
            best, best_half = result, half
    return best, best_half


def _signer_entry(lists_, host):
    info = lists_.signer(host) if host else None
    return lists_.name(info["name"]) if info else None


def _signer_claims(signature, half, lists_, found):
    """The signer that Signature-Agent names: a claimed signer other than the one that signed is a reason."""
    if signature is None:
        return []
    if signature.claimed and signature.signer and signature.claimed != signature.signer:
        found.add(reason("name.signer-mismatch", half, signature.claimed, claimed=signature.claimed,
                         signer=signature.signer))
    host = signature.claimed or signature.signer
    if not host:  # a signature that names no signer: verify.signature says why it is self-reported
        return []
    entry = _signer_entry(lists_, host)
    if entry is None:
        found.add(reason("name.unknown-signer", half, host, half=half, signer=host))
        return []
    found.add(reason("name.signer", half, host, half=half, signer=host, name=entry["name"]))
    found.candidate(entry, "signature-agent", "declared", half=half, signer=host)
    return [_Claim(entry, (half,), "signature-agent")]


def _agreed_name(claims, found):
    names = sorted({claim.entry["id"] for claim in claims})
    if len(names) > 1:
        found.add(reason("name.disagree", None, names, names=", ".join(names)))
        return None
    return claims[0].entry if claims else None


# ---------------------------------------------------------------- verification layer
def _verify(named, signature, half, evidence, lists_, settings, found):
    """The fields of the Identity that the verification layer decides."""
    outcome = signature.outcome if signature else None
    signer = _signer_entry(lists_, signature.signer or signature.claimed) if signature else None
    if outcome == webbotauth.INVALID:
        return _invalid_signature(signature, half, signer or named, settings, found)
    if outcome in (webbotauth.VERIFIED, webbotauth.DECLARED):
        found.add(reason("verify.signature", half, signature.signer or signature.claimed,
                         signature=webbotauth.as_facts(signature)))
    if outcome == webbotauth.VERIFIED and signer:
        found.candidate(signer, "signature", "signature", signer=signature.signer, keyid=signature.keyid)
        return {"entry": signer, "status": VERIFIED, "via": "signature", "evidence": ("signature",)}
    if named:
        return _verify_name(named, evidence, lists_, found, signed=outcome == webbotauth.DECLARED)
    return _infrastructure(evidence, found)


def _invalid_signature(signature, half, target, settings, found):
    facts = webbotauth.as_facts(signature)
    covers = signature.facts.get("covers", "")
    covered = {item.split(";")[0].strip('"') for item in covers.split()}  # component names, without parameters
    rewritable = [c for c in settings["signature_proxy_components"] if c in covered]
    if rewritable:
        found.add(reason("verify.signature-proxy", half, covers, signature=facts, components=", ".join(rewritable)))
        return {"entry": target, "status": UNVERIFIABLE, "evidence": ("declared",) if target else ()}
    found.add(reason("verify.signature-forged", half, covers, signature=facts,
                     name=target["name"] if target else signature.signer))
    return {"status": IMPERSONATION, "impersonating": target, "evidence": ("impersonation",)}


def _verify_name(entry, evidence, lists_, found, signed):
    """Check a declared name against reverse DNS, then the published ranges; signed: a signature already said
    why it is self-reported."""
    rdns = evidence.get("rdns")
    if rdns and rdns.get("name") == entry["id"]:
        if rdns.get("verified"):
            found.add(reason("verify.rdns", "collector", entry["id"], name=entry["name"]))
            found.candidate(entry, "rdns", "rdns")
            return {"entry": entry, "status": VERIFIED, "via": "rdns", "evidence": ("rdns",)}
        found.add(reason("verify.rdns-mismatch", "collector", entry["id"], name=entry["name"]))
        return {"status": IMPERSONATION, "impersonating": entry, "evidence": ("impersonation",)}
    self_reported = {"entry": entry, "status": SELF_REPORTED, "evidence": ("declared",)}
    if evidence.get("mode") == LOCAL_MODE:
        found.add(reason("verify.local"))
        return self_reported
    network = evidence.get("network")
    if network is None:
        found.add(reason("verify.no-address"))
        return self_reported
    if entry["id"] in (network.get("verifies") or []):
        found.add(reason("verify.ip-range", "collector", network["range_id"], range=network["range"],
                         operator=network["operator"], name=entry["name"]))
        found.candidate(entry, "ip", "ip_range", range=network["range_id"])
        return {"entry": entry, "status": VERIFIED, "via": "ip", "evidence": ("ip_range",)}
    infrastructure = _agent_range(network, found)  # an operator's agent range settles the infrastructure anyway
    publishers = [spec for spec in lists_.raw_ranges() if entry["id"] in spec.get("verifies", [])]
    if publishers:
        found.add(reason("verify.ip-mismatch", "collector", publishers[0]["id"], name=entry["name"],
                         operator=publishers[0].get("operator")))
        return _with_range({"status": IMPERSONATION, "impersonating": entry, "evidence": ("impersonation",)},
                           infrastructure)
    if not signed:
        found.add(reason("verify.no-range", None, entry["id"], name=entry["name"]))
    return _with_range(self_reported, infrastructure)


def _with_range(result, infrastructure):
    """The result with the operator's agent range the address is in, when it is in one: certain infrastructure."""
    if not infrastructure:
        return result
    return dict(result, infrastructure=infrastructure, evidence=result["evidence"] + ("ip_range",))


def _agent_range(network, found):
    """The published agent range holding the address as the operator's infrastructure, its reason listed; None when
    the address is in none."""
    if (network or {}).get("range_kind") != AGENT:
        return None
    found.add(reason("verify.ip-agent-range", "collector", network["range_id"], range=network["range"],
                     operator=network["operator"]))
    return {"operator": network["operator"], "range": network["range"], "range_id": network["range_id"]}


def _infrastructure(evidence, found):
    """Nothing declares a name: an address in an operator's published agent range is still its infrastructure."""
    network = evidence.get("network") or {}
    if evidence.get("mode") == LOCAL_MODE:
        found.add(reason("verify.local"))
        return {}
    infrastructure = _agent_range(network, found)
    if infrastructure:
        return {"infrastructure": infrastructure, "evidence": ("ip_range",)}
    if network.get("range_kind") == BOT:
        found.add(reason("verify.ip-bot-range", "collector", network["range_id"], range=network["range"],
                         operator=network["operator"]))
    return {}


def _verify_layer(evidence, result):
    """The verification layer's state as the interface shows it (web/src/data/schema/session.schema.json)."""
    if evidence.get("mode") == LOCAL_MODE:
        return {"state": OFF, "why": LOCAL_MODE}
    status, entry = result.get("status"), result.get("entry")
    if status == VERIFIED:
        state = BOT if entry and entry["category"] == BOT else AGENT
    elif status == IMPERSONATION or result.get("infrastructure"):
        state = AGENT
    else:
        state = UNSURE if status == UNVERIFIABLE else NO_HIT
    layer = {"state": state}
    if evidence.get("network") is None:
        layer["why"] = "no_address"
    return layer
