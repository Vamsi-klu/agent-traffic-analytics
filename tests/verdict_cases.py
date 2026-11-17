"""Made-up sessions for the verdict step's tests: builders for each layer's result, and the 16 control
sessions with the verdict the design table gives each one.

No real visitor is in here: User-Agents are the public forms of each product's, addresses are the first address of a
range read from the bundled lists at test time (or RFC 5737 documentation addresses), and times are invented.
"""
import ipaddress
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from agentcake.detect import env_rules, lists, timeline, webbotauth  # noqa: E402  (needs the repository first)

T0 = 1_794_500_000_000  # an invented session start, epoch ms
S = 1000  # ms per second

CHROME_MAC = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/157.0.0.0 Safari/537.36")
CHROME_LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
HEADLESS = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "HeadlessChrome/149.0.7827.55 Safari/537.36")
GOOGLEBOT = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; "
             "+http://www.google.com/bot.html) Chrome/157.0.0.0 Safari/537.36")
UPTIMEROBOT = "Mozilla/5.0+(compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)"
LIGHTHOUSE = CHROME_LINUX + " Chrome-Lighthouse"
CHATGPT_USER = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot"
MANUS = CHROME_LINUX + " Manus-User/1.0"
ANTIGRAVITY = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/152.0.7977.167 Safari/537.36 Antigravity/2.32.1")
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          "Version/19.0 Mobile/15E148 Safari/604.1")
NOWHERE = "203.0.113.7"  # RFC 5737 documentation address: in no published range
HALVES = ("page", "collector", "server")


def first_address(range_id):
    """The first host address of a bundled range's first IPv4 block."""
    with open(os.path.join(REPO, "agentcake", "data", "lists", "ip_ranges.json"), encoding="utf-8") as f:
        spec = next(r for r in json.load(f)["ranges"] if r["id"] == range_id)
    return str(next(ipaddress.ip_network(spec["v4"][0]).hosts()))


def network(address):
    """What the collect endpoint keeps of an address: the lists' answer, never the address."""
    return lists.current().match_ip(address)


def hit_fields(found):
    """An environment hit as JSON: its rule, layer, kind, half, strength, grade and value, with the pages it held on and
    the names it gives or suggests when it has them (the lab fixtures write hits this way)."""
    out = {"rule": found.rule, "layer": found.layer, "kind": found.kind, "half": found.half,
           "strength": found.strength, "grade": found.grade, "value": found.value}
    if found.pages is not None:
        out["pages"] = list(found.pages)
    for key in ("names", "suggests"):
        if getattr(found, key) is not None:
            out[key] = getattr(found, key)
    return out


def botscent_reasons(hits, table=None):
    """The botscent page-half reason ids these hits stand for: what botscent's own verdict should have listed (the
    rules' "botscent" field, in the order the hits name them)."""
    table = table or env_rules.load_rules()
    reasons = []
    for found in hits:
        for reason in table.rule(found.rule).botscent:
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def hit(rule_id, pages=(0,), value=True):
    """An environment rule's hit, as env_rules.evaluate() makes it (session rules hold on no page)."""
    rule = env_rules.load_rules().rule(rule_id)
    held = None if rule.scope == "session" else tuple(pages)
    return env_rules.Hit(rule.id, rule.layer, rule.kind, rule.half, rule.strength, rule.grade, value, held,
                         rule.names, rule.suggests)


def env(*hits):
    return env_rules.EnvResult(tuple(hits), (), ())


def verified(signer, keyid="key-1"):
    return webbotauth.Verification(webbotauth.VERIFIED, "verified", signer, keyid, "sig1", "signature-agent", signer,
                                   {"covers": '"@authority" "signature-agent"'})


def forged(signer, covers='"@authority" "signature-agent"', claimed=None):
    return webbotauth.Verification(webbotauth.INVALID, "bad-signature", signer, "key-1", "sig1", "signature-agent",
                                   claimed or signer, {"covers": covers})


def declared(claimed, code="key-missing", signer=None):
    return webbotauth.Verification(webbotauth.DECLARED, code, signer or claimed, "key-9", "sig1", "signature-agent",
                                   claimed, {})


def run(who, start_s, end_s, n, p):
    return {"who": who, "start": T0 + start_s * S, "end": T0 + end_s * S, "n": n, "p": p}


AGENT_RUN = run("agent", 0, 60, 20, 0.97)
HUMAN_RUN = run("human", 0, 59, 15, 0.08)


def behavior(verdict, *runs):
    """A behaviour result in model.judge_session's shape, its timeline made of these runs."""
    runs = [dict(r) for r in runs]
    labels = [r["who"] for r in runs for _ in range(r["n"])]
    return {"verdict": verdict, "confidence": 1.0, "basis": ["rules"], "evidence": {}, "n_actions": len(labels),
            "raw_input": True, "segments": [],
            "timeline": {"actions": [], "runs": runs, "shares": timeline.shares(labels),
                         "handoffs": timeline.handoffs(runs)}}


def too_little(reason="few_actions", n_actions=1):
    return {"verdict": "too_little_data", "confidence": None, "basis": [], "evidence": {"reason": reason},
            "n_actions": n_actions, "raw_input": True, "segments": [], "timeline": None}


def evidence(mode="server", uas=CHROME_MAC, platform="MacIntel", hits=(), behavior_result=None, address=NOWHERE,
             signatures=None, pages=None, rdns=None, touch=False, assistive=None, visits=()):
    """One session's evidence (agentcake/detect/verdict.py's docstring). uas: one User-Agent for every half, or a
    {half: [User-Agent]} dict. address: the visitor's address in server mode (None: no address was seen)."""
    agents = {half: [uas] for half in HALVES} if isinstance(uas, str) else uas
    return {"mode": mode, "pages": pages if pages is not None else [{"t": T0}],
            "user_agents": agents, "platform": platform, "signatures": signatures or {},
            "network": network(address) if (mode == "server" and address) else None, "rdns": rdns,
            "env": env(*hits), "behavior": behavior_result, "touch": touch, "assistive": assistive,
            "visits": list(visits)}


def crawl_pages(n, every_s):
    return [{"t": T0 + i * every_s * S} for i in range(n)]


AUTOMATION_HITS = ("env.auto.webdriver", "env.auto.headless-ua", "env.auto.headless-ua-collector",
                   "env.auto.headless-ua-server", "env.auto.collect-no-accept-language")

# The 16 control sessions, and what the design table says of each:
# class, Agent row, name, verification, confidence, reasons that must be listed, the behaviour layer's state.
CONTROLS = [
    ("signed-human", "Web Bot Auth signature of chatgpt.com verified, every action a human's",
     lambda: evidence(uas=CHROME_LINUX, platform="Linux x86_64", signatures={"collector": verified("chatgpt.com")},
                      behavior_result=behavior("human", HUMAN_RUN)),
     {"class": "mixed", "row": "ai", "name": "chatgpt", "verification": "verified", "confidence": "possible",
      "reasons": ["verify.signature", "behavior.human"], "behavior": "human"}),
    ("signed-agent", "Web Bot Auth signature of chatgpt.com verified, every action an agent's",
     lambda: evidence(uas=CHROME_LINUX, platform="Linux x86_64", signatures={"collector": verified("chatgpt.com")},
                      behavior_result=behavior("agent", AGENT_RUN)),
     {"class": "agent", "row": "ai", "name": "chatgpt", "verification": "verified", "confidence": "certain",
      "reasons": ["verify.signature", "behavior.agent"], "behavior": "agent"}),
    ("muse", "Muse's page rule, no signature, one page without a click",
     lambda: evidence(uas=CHROME_LINUX, platform="Linux x86_64", hits=[hit("env.product.muse")],
                      address=first_address("cloudflare"), behavior_result=too_little(n_actions=0)),
     {"class": "agent", "row": "ai", "name": "muse", "verification": None, "confidence": "likely",
      "reasons": ["env.product.muse", "behavior.too-little-data"], "behavior": "unsure"}),
    ("playwright-headless", "Playwright without a window on this computer",
     lambda: evidence(mode="local", uas=HEADLESS, hits=[hit(r) for r in AUTOMATION_HITS]
                      + [hit("env.auto.cdp-runtime-leak")], behavior_result=behavior("agent", AGENT_RUN)),
     {"class": "agent", "row": "automated", "name": None, "verification": None, "confidence": "likely",
      "reasons": ["env.auto.webdriver", "env.auto.headless-ua", "env.automated", "name.ua-generic"],
      "behavior": "agent"}),
    ("playwright-headed-humanlike", "Playwright with a window, moving like a hand",
     lambda: evidence(mode="local", hits=[hit("env.auto.webdriver"), hit("env.auto.cdp-runtime-leak"),
                                          hit("env.auto.chromium-only-brand")],
                      behavior_result=behavior("human", HUMAN_RUN)),
     {"class": "agent", "row": "automated", "name": None, "verification": None, "confidence": "likely",
      "reasons": ["env.auto.webdriver", "env.automated", "behavior.overruled"], "behavior": "human"}),
    ("cloud-crawler-script", "A script on a cloud server loading a page every 5 s, twelve pages",
     lambda: evidence(uas=HEADLESS, hits=[hit(r) for r in AUTOMATION_HITS] + [hit("env.cloud.datacenter-ip")],
                      address=first_address("aws"), pages=crawl_pages(12, 5), behavior_result=too_little(n_actions=0)),
     {"class": "agent", "row": "automated", "name": None, "verification": None, "confidence": "likely",
      "reasons": ["env.automated", "crawler.like"], "behavior": "unsure"}),
    ("googlebot-verified", "Googlebot's User-Agent from Google's published crawler range",
     lambda: evidence(uas=GOOGLEBOT, platform="Linux x86_64", address=first_address("google-common-crawlers")),
     {"class": "bot", "row": None, "name": "googlebot", "verification": "verified", "confidence": "certain",
      "reasons": ["name.ua", "verify.ip-range", "behavior.not-run-bot"], "behavior": "off"}),
    ("googlebot-impersonated", "Googlebot's User-Agent from an address outside Google's ranges",
     lambda: evidence(uas=GOOGLEBOT, platform="Linux x86_64", behavior_result=behavior("agent", AGENT_RUN)),
     {"class": "agent", "row": "automated", "name": None, "verification": "impersonation", "confidence": "likely",
      "impersonating": "googlebot", "reasons": ["verify.ip-mismatch", "env.automated"], "behavior": "agent"}),
    ("uptimerobot", "UptimeRobot's check, which publishes no range AgentCake can check",
     lambda: evidence(uas=UPTIMEROBOT, platform="Linux x86_64"),
     {"class": "bot", "row": None, "name": "uptimerobot", "verification": "self_reported", "confidence": "likely",
      "reasons": ["name.ua", "verify.no-range"], "behavior": "off"}),
    ("claude-in-chrome", "Claude in Chrome: an attribute-less closed shadow host, agent behaviour",
     lambda: evidence(mode="local", hits=[hit("env.ext.closed-shadow-host", pages=(1,)),
                                          hit("env.ext.cross-site-landing"), hit("env.ext.viewport-shrink")],
                      pages=[{"t": T0}, {"t": T0 + 40 * S}], behavior_result=behavior("agent", AGENT_RUN)),
     {"class": "agent", "row": "ai", "name": "claude-chrome", "verification": None, "confidence": "possible",
      "reasons": ["env.ext.closed-shadow-host", "env.ext.cross-site-landing", "behavior.agent", "name.from-trace"],
      "behavior": "agent"}),
    ("human", "A human's own Chrome",
     lambda: evidence(behavior_result=behavior("human", HUMAN_RUN)),
     {"class": "human", "row": None, "name": None, "verification": None, "confidence": "possible",
      "reasons": ["behavior.human"], "behavior": "human"}),
    ("weak-only", "A human with only weak signals: landed cross-site, viewport got shorter, a datacenter address",
     lambda: evidence(hits=[hit("env.ext.cross-site-landing"), hit("env.ext.viewport-shrink"),
                            hit("env.cloud.datacenter-ip")], address=first_address("aws"),
                      behavior_result=behavior("human", HUMAN_RUN)),
     {"class": "human", "row": None, "name": None, "verification": None, "confidence": "possible",
      "reasons": ["env.ext.cross-site-landing", "env.ext.viewport-shrink", "env.cloud.datacenter-ip"],
      "behavior": "human"}),
    ("forged-signature", "A Web Bot Auth signature of chatgpt.com that does not verify",
     lambda: evidence(uas=CHROME_LINUX, platform="Linux x86_64", signatures={"collector": forged("chatgpt.com")},
                      behavior_result=behavior("agent", AGENT_RUN)),
     {"class": "agent", "row": "automated", "name": None, "verification": "impersonation", "confidence": "likely",
      "impersonating": "chatgpt", "reasons": ["verify.signature-forged", "env.automated"], "behavior": "agent"}),
    ("assistive-tool", "Keyboard navigation without a pointer, judged an agent by behaviour",
     lambda: evidence(behavior_result=behavior("agent", AGENT_RUN), assistive={"keys": 40, "pointer_moves": 0}),
     {"class": "not_sure", "row": None, "name": None, "verification": None, "confidence": "unsure",
      "reasons": ["behavior.assistive"], "behavior": "agent"}),
    ("lighthouse-local", "Lighthouse on this computer, automation flag set",
     lambda: evidence(mode="local", uas=LIGHTHOUSE, platform="Linux x86_64", hits=[hit("env.auto.webdriver")]),
     {"class": "bot", "row": None, "name": "lighthouse", "verification": "self_reported", "confidence": "likely",
      "reasons": ["name.ua", "verify.local", "env.auto.webdriver"], "behavior": "off"}),
    ("phone", "A few seconds on a phone",
     lambda: evidence(uas=IPHONE, platform="iPhone", touch=True, behavior_result=too_little("touch", None)),
     {"class": "too_little_data", "row": None, "name": None, "verification": None, "confidence": "unsure",
      "reasons": ["behavior.touch"], "behavior": "unsure"}),
]
