"""One session's evidence for the verdict step (agentcake.detect.verdict), built from what each data set recorded.

    from_signals(signals, raw=None, rrweb=None, mode="local", network=None) -> evidence
        env_signals' dict (from_lab or from_cake) and the session's events: every layer that data can feed, and the
        indicator spans (markers.turn_spans) the behaviour timeline gives to the agent
    behaviour_only(events, raw_input, touch=False, session_start=None) -> evidence
        a recording with events only (PostHog's): no environment, no names; behaviour as the model judges it
    named_only(user_agent) -> evidence    nothing but a User-Agent, on this computer (GOAL A7)
    keep(evidence, halves=None, layers=None) -> evidence
        the evidence some halves (page, collector, server) or some judging layers would have had alone
    with_behaviour(evidence, raw, rrweb) -> evidence     the behaviour layer's result added (store.py's sessions)

Each builder runs the behaviour layer once (behavior.run, as verdict.judge does) and stores its result, so keep() can
take evidence away without judging the events again. keep() leaves out what a half did not read: the page half is
cake.js (its environment signals, its User-Agent, the behaviour of its events); the collector half is the collect
endpoint (its requests' headers and signatures, the network facts and the earlier visits of that network); the
server half is the site's server (the page request's headers, signature and Sec-Purpose). Nothing here judges:
verdict.decide() does, on what these return.
"""
import dataclasses

from agentcake.detect import behavior, env_rules, markers, model, verdict, verdict_identity, weak

PAGE, COLLECTOR, SERVER = "page", "collector", "server"


def from_signals(signals, raw=None, rrweb=None, mode="local", network=None, visits=(), signatures=None,
                 touch=False, page_times=None):
    """page_times: when each of the signals' page views began (ms), in their order; default: page_starts(raw)."""
    claims = verdict_identity.claims_from_signals(signals)
    times = list(page_times if page_times is not None else page_starts(raw or []))
    pages = [dict(_page(page), **({"t": times[i]} if i < len(times) else {}))
             for i, page in enumerate(signals.get("pages") or [])]
    evidence = {"mode": mode, "pages": pages,
                "user_agents": claims["user_agents"], "platform": claims["platform"],
                "signatures": signatures or {}, "network": network, "rdns": None,
                "env": env_rules.evaluate(signals), "marks": markers.turn_spans(signals), "touch": touch,
                "visits": list(visits),
                "weak": weak.facts(signals, (), raw or [])}  # no collect-request facts: a lab or recorder session
    return with_behaviour(evidence, raw, rrweb)


def behaviour_only(events, raw_input, touch=False, session_start=None):
    """A session that recorded nothing but its events: the behaviour layer alone (env None: not recorded).

    The model is called as S3.7's tables call it (model.judge_session on the events as they are), which gives
    too little data for a phone, a tablet or too few action segments exactly as behavior.run() does.
    """
    result = model.judge_session(events, raw_input=raw_input, touch=touch, session_start=session_start)
    return {"mode": "local", "pages": [], "user_agents": {}, "platform": None, "signatures": {}, "network": None,
            "rdns": None, "env": None, "touch": touch, "visits": [], "behavior": result,
            "assistive": behavior.assistive_signs(events) if raw_input else None}


def named_only(user_agent):
    """GOAL A7: a local session whose only evidence is its User-Agent (on every half that reads one)."""
    return {"mode": "local", "pages": [], "user_agents": {PAGE: [user_agent], COLLECTOR: [user_agent],
                                                          SERVER: [user_agent]},
            "platform": None, "signatures": {}, "network": None, "rdns": None, "env": None, "touch": False,
            "visits": [], "behavior": None, "assistive": None}


def keep(evidence, halves=None, layers=None):
    """The evidence with only the given halves, or only the given judging layers (None keeps everything)."""
    out = dict(evidence)
    if halves is not None:
        halves = set(halves)
        out["user_agents"] = {h: v for h, v in (evidence.get("user_agents") or {}).items() if h in halves}
        out["signatures"] = {h: v for h, v in (evidence.get("signatures") or {}).items() if h in halves}
        if PAGE not in halves:
            out.update(platform=None, behavior=None, assistive=None)
        if COLLECTOR not in halves:
            out.update(network=None, rdns=None, visits=[])
        if SERVER not in halves:
            out["pages"] = [{k: v for k, v in page.items() if k != "sp"} for page in evidence.get("pages") or []]
        out["env"] = _env_from(evidence.get("env"), lambda hit: hit.half in halves)
    if layers is not None:
        layers = set(layers)
        if "name" not in layers:
            out.update(user_agents={}, platform=None)
        if "verify" not in layers:
            out.update(signatures={}, network=None, rdns=None)
        if "environment" not in layers:
            out["env"] = _env_from(evidence.get("env"), lambda hit: False)
        if "behavior" not in layers:
            out.update(behavior=None, assistive=None)
    return out


def with_behaviour(evidence, raw, rrweb):
    """The evidence with the behaviour layer's result, as verdict.judge runs it (not for a known Bot), kept on the
    evidence so the tables can judge it again with parts taken away."""
    needed, _ = verdict.needs_behavior(evidence)
    result = behavior.run(raw=raw, rrweb=rrweb, touch=evidence["touch"], turns=evidence.get("marks") or ()) \
        if needed and (raw or rrweb) else None
    assistive = behavior.assistive_signs(raw) if raw else None
    return dict(evidence, behavior=result, assistive=assistive)


def _env_from(env, wanted):
    """An EnvResult with only the wanted hits (None stays None: not recorded)."""
    if env is None:
        return None
    return dataclasses.replace(env, hits=tuple(hit for hit in env.hits if wanted(hit)))


def page_starts(raw):
    """When each page view began, read from raw events tagged with their page: the first event of each run of
    events on one page (a page opened twice is two runs). The crawler check reads only these times."""
    starts, current = [], object()
    for event in raw:
        if event.get("pg") != current:
            current = event.get("pg")
            starts.append(event["t"])
    return starts


def _page(page):
    """verdict's page entry: the server half's Sec-Purpose of the page request, when the signals have it."""
    headers = (page.get("nav") or {}).get("headers") or {}
    purpose = headers.get("sec-purpose")
    return {"sp": purpose} if purpose else {}
