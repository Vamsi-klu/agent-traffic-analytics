"""Web Bot Auth: is this request signed by the signer it names? The verification layer of the judgement.

A Web Bot Auth request (draft-ietf-webbotauth-httpsig-protocol-01 over RFC 9421) carries Signature-Input, Signature
and Signature-Agent. A verified signature is the only signal that names a cloud agent such as ChatGPT agent, which
sends an ordinary browser User-Agent. verify_request() answers, on this computer and
without any network access, one of four outcomes, each with a reason code:

  verified  the signature verifies with a bundled key of the signer it is attributed to, inside its time window;
  invalid   everything needed was there and the signature does not verify: the signed parts of the request were
            changed or the signature is forged (the judgement reads this as impersonating that signer);
  declared  self-reported only: the signer or its key is not bundled, not valid or a known test key, the signature
            is outside its time window, uses an algorithm not supported here, or what it signed cannot be rebuilt.
            Never impersonation: this is also what an outdated key list or a clock difference looks like;
  none      no Web Bot Auth signature and no Signature-Agent.

Attribution follows draft -01: a signature belongs to the Signature-Agent member it covers (section 5.2.2) and only
that signer's keys can verify it (section 5.4). A signature covering no usable member is checked with the key its
keyid names, wherever that key is bundled, and attributed to the signer publishing it, no further (section 4.3).

Input: an httpsig.Request, a KeyDirectory (or the {signer: keys} mapping it is built from), the time in seconds and
the settings of agentcake/data/webbotauth.json. Output: a Verification. SessionVerifier verifies the first signed
request of a session and keeps the result for the rest of it, as one verification is a few milliseconds of
pure-Python arithmetic. Structure after botscent src/server/webbotauth.ts (MIT, commit 7f948003), which has two
outcomes; the four outcomes, key attribution and the code are this module's own.
"""
import dataclasses
import functools
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from agentcake import paths
from agentcake.detect import ed25519, httpsig, sfv
from agentcake.detect.keydirectory import KeyDirectory, signer_identifier

SETTINGS_FILE = os.path.join(paths.PACKAGE_DIR, "data", "webbotauth.json")

VERIFIED, INVALID, DECLARED, NONE = "verified", "invalid", "declared", "none"
OUTCOME_ORDER = (NONE, DECLARED, INVALID, VERIFIED)  # a request takes the outcome of its best signature
CODES = {
    "verified": VERIFIED, "verified-by-key": VERIFIED,
    "bad-signature": INVALID,
    "unsupported-algorithm": DECLARED, "unsupported-key": DECLARED, "incomplete": DECLARED,
    "unknown-signer": DECLARED, "key-missing": DECLARED, "key-shared": DECLARED, "test-key": DECLARED,
    "key-not-yet-valid": DECLARED, "key-expired": DECLARED, "not-yet-valid": DECLARED, "expired": DECLARED,
    "too-old": DECLARED, "no-signature-value": DECLARED, "unrebuildable": DECLARED, "claim-only": DECLARED,
    "unsigned": NONE,
}
PARAMETER_TYPES = {"created": int, "expires": int, "nonce": str, "alg": str, "keyid": str, "tag": str}  # RFC 9421 2.3
CHECKED_PARAMETERS = {"created", "expires", "keyid"}  # the checks below read these, so the settings must require them
BY_SIGNATURE_AGENT, BY_KEY = "signature-agent", "key"
RESULT_FIELDS = ("code", "signer", "keyid", "label", "via", "claimed")  # what as_facts() keeps besides the check's facts


@dataclass(frozen=True)
class Settings:
    """agentcake/data/webbotauth.json; its $doc describes each setting."""

    tag: str
    algorithms: tuple
    required_parameters: tuple
    required_components_any: tuple
    signature_agent_schemes: tuple
    directory_well_known_path: str
    clock_skew_s: float
    max_age_s: float
    max_signatures: int
    rejected_key_thumbprints: dict
    verify_budget_ms: float
    session_cache_size: int
    reasons: dict
    details: dict = dataclasses.field(default_factory=dict)  # code -> what was checked, in technical words

    def __post_init__(self):
        if not CHECKED_PARAMETERS <= set(self.required_parameters):
            raise ValueError(f"required_parameters must include {', '.join(sorted(CHECKED_PARAMETERS))}")


@dataclass(frozen=True)
class SignatureCheck:
    """What one Web Bot Auth signature of a request came to.

    signer: the signer the signature is attributed to, or for some declared outcomes the one it names; via: how it
    was attributed (BY_SIGNATURE_AGENT or BY_KEY); claimed: the signer Signature-Agent names for this label, signed
    or not (it can differ from signer); facts: values for the reason text (seconds, missing parameters, ...).
    """

    label: str
    outcome: str
    code: str
    signer: object = None
    keyid: object = None
    via: object = None
    claimed: object = None
    facts: dict = dataclasses.field(default_factory=dict)


@dataclass(frozen=True)
class Verification:
    """What a request came to: the outcome of its best signature, and every signature checked, best first.

    skipped counts the signatures beyond settings.max_signatures, which were not checked.
    """

    outcome: str
    code: str
    signer: object = None
    keyid: object = None
    label: object = None
    via: object = None
    claimed: object = None
    facts: dict = dataclasses.field(default_factory=dict)
    checks: tuple = ()
    skipped: int = 0


def load_settings(path=SETTINGS_FILE):
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    missing = [setting.name for setting in dataclasses.fields(Settings) if setting.name not in data
               and setting.default is dataclasses.MISSING and setting.default_factory is dataclasses.MISSING]
    if missing:
        raise ValueError(f"{path} lacks {', '.join(missing)}")
    return Settings(**{setting.name: _frozen(data[setting.name]) for setting in dataclasses.fields(Settings)
                       if setting.name in data})


@functools.cache
def default_settings():
    return load_settings()


def verify_request(request, directory, now_s, settings=None):
    """The Verification of ``request`` against the bundled keys in ``directory`` at time ``now_s`` (seconds).

    ``directory`` is a KeyDirectory, built once and reused, or the {signer: keys} mapping to build one from.
    Header values are str, as http.server gives them.
    """
    settings = settings or default_settings()
    if not isinstance(directory, KeyDirectory):
        directory = KeyDirectory(directory, settings)
    agents = _signature_agents(request.field("signature-agent"))
    inputs = _dictionary(request.field("signature-input"))
    values = _dictionary(request.field("signature"))
    tagged = [(label, member) for label, member in inputs.items()
              if isinstance(member, sfv.InnerList) and member.params.get("tag") == settings.tag]
    checks = [_check(request, label, member, values, agents, directory, now_s, settings)
              for label, member in tagged[:settings.max_signatures]]
    skipped = len(tagged) - len(checks)
    if checks:
        best_first = tuple(sorted(checks, key=lambda check: OUTCOME_ORDER.index(check.outcome), reverse=True))
        best = best_first[0]
        return Verification(best.outcome, best.code, best.signer, best.keyid, best.label, best.via, best.claimed,
                            best.facts, best_first, skipped)
    if agents:
        named = [_member_signer(item, settings) for item in agents.values()]
        claimed = named[0] if len(named) == 1 else None
        return Verification(DECLARED, "claim-only", claimed=claimed)
    return Verification(NONE, "unsigned")


def explain(result, settings=None):
    """The reason text of a Verification or SignatureCheck, from settings.reasons."""
    return words(as_facts(result), settings)[0]


def as_facts(result):
    """A Verification or SignatureCheck as a reason keeps it: its code, signer, key, label and claimed signer and the
    facts of its check, as plain values (verdict_text keeps them and words() says them)."""
    out = {name: getattr(result, name) for name in RESULT_FIELDS if getattr(result, name, None) is not None}
    out.update({str(key): list(value) if isinstance(value, (tuple, set, frozenset)) else value
                for key, value in (result.facts or {}).items()})
    return out


def words(facts, settings=None):
    """(reason, detail) of a result's facts (as_facts): its text in settings.reasons and its technical words in
    settings.details, None when the code has none."""
    settings = settings or default_settings()
    reasons, code = settings.reasons, facts.get("code")
    filled = _Facts(reasons["$missing"], {}, {key: value for key, value in facts.items() if value is not None})
    text = reasons[code].format_map(filled) if code in reasons else None
    detail = settings.details.get(code)
    return text, (detail.format_map(filled) if detail else None)


class SessionVerifier:
    """Verifies the first signed request of each session and keeps the result for the session's later requests.

    A request without a signature is not remembered, since a later request of the same session may be signed.
    Up to settings.session_cache_size sessions are kept, the least recently used leaving first. Thread-safe.

    authorities: other names the request's site goes by, tried in order as its @authority when the signature does not
    verify with the request's own. A front door that replaces Host (nginx's default proxy_set_header
    Host $proxy_host, CloudFront, Azure Front Door) changes the authority the verifier rebuilds, not the one the agent
    signed. A signature binds the name it was made for, so a forgery verifies with none of them and stays invalid as
    checked with the request's own name; each extra name costs one more verification, once per session.
    """

    def __init__(self, directory, settings=None, clock=time.time):
        self.settings = settings or default_settings()
        self.directory = directory if isinstance(directory, KeyDirectory) else KeyDirectory(directory, self.settings)
        self.clock = clock
        self._results = OrderedDict()
        self._lock = threading.Lock()

    def verify(self, session_id, request, authorities=()):
        with self._lock:
            if session_id in self._results:
                self._results.move_to_end(session_id)
                return self._results[session_id]
        now_s = self.clock()
        result = verify_request(request, self.directory, now_s, self.settings)
        if result.outcome == INVALID:
            result = self._other_names(request, authorities, now_s) or result
        if result.outcome != NONE:
            with self._lock:
                self._results[session_id] = result
                while len(self._results) > self.settings.session_cache_size:
                    self._results.popitem(last=False)
        return result

    def _other_names(self, request, authorities, now_s):
        """The Verification of the request as made for the first of the other names that verifies it, else None."""
        tried = {request.authority.strip().lower()}
        for authority in authorities:
            name = (authority or "").strip().lower()
            if not name or name in tried:
                continue
            tried.add(name)
            result = verify_request(dataclasses.replace(request, authority=name), self.directory, now_s, self.settings)
            if result.outcome == VERIFIED:
                return result
        return None


def _check(request, label, member, values, agents, directory, now_s, settings):
    """The SignatureCheck of the signature ``label``: cheap checks first, the Ed25519 arithmetic last."""
    covered, claimed = _attribution(member, label, agents, settings)
    params = member.params
    keyid = params["keyid"] if _has_type(params, "keyid") else None

    def result(code, signer=covered, via=None, **facts):
        return SignatureCheck(label, CODES[code], code, signer, keyid, via, claimed, facts)

    if "alg" in params and params["alg"] not in settings.algorithms:
        return result("unsupported-algorithm", alg=params["alg"])
    missing = [name for name in settings.required_parameters if not _has_type(params, name)]
    if not any(_is_component(item, name) and not item.params
               for item in member.items for name in settings.required_components_any):
        missing.append(" or ".join(settings.required_components_any))
    if missing:
        return result("incomplete", missing=", ".join(missing))

    problem, signer, key, via = _find_key(covered, claimed, keyid, directory, settings)
    if problem:
        code, facts = problem
        return result(code, signer, via, **facts)
    problem = _time_problem(key, params["created"], params["expires"], now_s, settings)
    if problem:
        code, facts = problem
        return result(code, signer, via, **facts)

    value = values.get(label)
    if not isinstance(value, sfv.Item) or not isinstance(value.value, bytes):
        return result("no-signature-value", signer, via)
    try:
        base = httpsig.signature_base(request, member)
    except httpsig.ComponentError as error:
        return result("unrebuildable", signer, via, detail=str(error))
    covers = " ".join(sfv.serialize(item) for item in member.items)  # if invalid: what a proxy could have changed
    if ed25519.verify(key.public_key, base.encode("ascii"), value.value):
        return result("verified" if via == BY_SIGNATURE_AGENT else "verified-by-key", signer, via, covers=covers)
    return result("bad-signature", signer, via, covers=covers)


def _find_key(covered, claimed, keyid, directory, settings):
    """((code, facts) or None, signer, key, via): the key that may verify the signature, or why there is none.

    With a covered Signature-Agent member only that signer's keys count (draft -01 5.4); without one, the key
    the keyid names counts wherever it is bundled, provided a single signer publishes it (draft -01 4.3).
    """
    if covered is not None:
        if not directory.knows(covered):
            return ("unknown-signer", {}), covered, None, None
        key = directory.find(covered, keyid)
        signer, via = covered, BY_SIGNATURE_AGENT
        if key is None:
            return ("key-missing", {}), signer, None, None
    else:
        holders = directory.holders(keyid)
        if not holders:
            return ("key-missing", {}), claimed, None, None
        if len(holders) > 1:
            return ("key-shared", {"signers": ", ".join(name for name, _ in holders)}), None, None, None
        (signer, key), via = holders[0], BY_KEY
    if key.thumbprint in settings.rejected_key_thumbprints:
        return ("test-key", {"why": settings.rejected_key_thumbprints[key.thumbprint]}), signer, key, via
    if key.public_key is None:
        return ("unsupported-key", {}), signer, key, via
    return None, signer, key, via


def _time_problem(key, created, expires, now_s, settings):
    """(code, facts) when the key or the signature is not valid at this time, else None."""
    if key.not_before is not None and created < key.not_before:
        return "key-not-yet-valid", {}
    if key.expires is not None and created > key.expires:
        return "key-expired", {}
    if now_s < created - settings.clock_skew_s:
        return "not-yet-valid", {"seconds": round(created - now_s)}
    if now_s > expires + settings.clock_skew_s:
        return "expired", {"seconds": round(now_s - expires)}
    if now_s > created + settings.max_age_s + settings.clock_skew_s:
        return "too-old", {"seconds": round(now_s - created), "max_age_s": settings.max_age_s}
    return None


def _attribution(member, label, agents, settings):
    """(signer of the Signature-Agent member the signature covers, signer named for its label); None for none."""
    covered_keys = [item.params.get("key") for item in member.items if _is_component(item, "signature-agent")]
    if None in agents:  # the legacy bare String names the signer of every signature, covered whole
        claimed_item = agents[None]
        covered_item = claimed_item if None in covered_keys else None
    else:
        keyed = [key for key in covered_keys if key is not None]
        only = next(iter(agents)) if len(agents) == 1 else None
        if label in keyed or (None in covered_keys and label in agents):
            key = label
        elif len(keyed) == 1:
            key = keyed[0]
        else:
            key = only if None in covered_keys else None
        covered_item = agents.get(key)
        claimed_item = covered_item or agents.get(label) or agents.get(only)
    return _member_signer(covered_item, settings), _member_signer(claimed_item, settings)


def _member_signer(item, settings):
    """The signer a Signature-Agent member names; None for a member with parameters (draft -01 5.2.1) or no URL."""
    if not isinstance(item, sfv.Item) or item.params or isinstance(item.value, sfv.Token):
        return None
    return signer_identifier(item.value, settings) if isinstance(item.value, str) else None


def _signature_agents(value):
    """Signature-Agent as {key: member}; its legacy form, one String, as {None: item}; {} when absent or unreadable."""
    try:
        if value is not None and value.lstrip(" \t").startswith('"'):
            return {None: sfv.parse_item(value)}
        return _dictionary(value)
    except sfv.ParseError:
        return {}


def _dictionary(value):
    if value is None:
        return {}
    try:
        return sfv.parse_dictionary(value)
    except sfv.ParseError:
        return {}


def _has_type(params, name):
    """True when the parameter is present, with the type RFC 9421 2.3 gives it when it defines one."""
    value, kind = params.get(name), PARAMETER_TYPES.get(name)
    if kind is None:
        return value is not None
    return isinstance(value, kind) and not isinstance(value, (bool, sfv.Token))


def _is_component(item, name):
    """True when a covered component is ``name``; component names are Strings, never Tokens (RFC 9421 2)."""
    return isinstance(item.value, str) and not isinstance(item.value, sfv.Token) and item.value == name


def _frozen(value):
    return tuple(value) if isinstance(value, list) else value


class _Facts(dict):
    """The fields of a result for str.format_map; an unknown value prints as the settings' $missing text."""

    def __init__(self, missing, fields, facts):
        super().__init__({name: value for name, value in fields.items() if value is not None}, **facts)
        self.missing = missing

    def __missing__(self, name):
        return self.missing
