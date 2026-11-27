"""Each data set's sessions judged by AgentCake's four layers, one row per session with its answer.

    lab(sessions, signals_by_run) -> rows            our lab's sessions: every layer (local mode)
    lab_signals(sessions) -> rows                    the lab's signal recordings: environment and names, no events
    cakejs(uploads) -> rows                          real cake.js uploads of automated browsers, as collect got them
    recordings(items) -> rows                        clean human recordings: every layer the recorder fed
    recorded(items, source) -> rows                  the recorder's agents and hand-offs, each with its own answer
                                                     (source: recorded, or selfcollect for our own runs)
    posthog(units, settings) -> rows                 PostHog replays: behaviour only (reference)
    public_humans(items) -> rows                     real people from public data sets: behaviour only (scoreboard)
    store(labelled) -> rows                          CAKE_HOME sessions listed in truth_goal.jsonl
    site(labelled) -> rows                           a website's own sessions, labelled afterwards (held out)
    named(cases) -> rows                             threshold A7's User-Agents, nothing else known

A row: {"id", "source", "group", "truth": {"class", "row", ...}, "class", "row", "name", "kind", "verification",
"reasons" (ids), "behaviour" (the model's own verdict), "too_little" (the behaviour layer saw too little data:
a phone, a tablet, or fewer action segments than the minimum), "layers" (each layer's state), "site" (where it was
recorded, when the data set says; the scoreboard counts per site), "holdout" (what a session is held out with, when
the data set says: the person in the PostHog training set, the site owner's accounts as one; the product in the
recorder's agents), "evidence"}. The
evidence stays on the row for the tables that take parts of it away (layers.py); report.py never prints it.
"""
from agentcake.detect import env_signals, verdict
from agentcake.evaluation import evidence as evidence_builder

TOO_LITTLE = "too_little_data"
RECORDED, SELFCOLLECT = "recorded", "selfcollect"  # people's agent recordings; the ones we ran ourselves
SITE = "site"  # a website's own sessions, labelled afterwards: held out


def row(row_id, source, group, truth, evidence, site=None, holdout=None):
    """A session's row (see the module docstring)."""
    result = verdict.decide(evidence)
    behaviour = evidence.get("behavior") or {}
    return {"id": row_id, "source": source, "group": group, "truth": truth, "class": result["class"],
            "row": result["row"], "name": result["name"], "kind": result["kind"],
            "verification": result["verification"], "confidence": result["confidence"],
            "percent": result.get("percent"),  # an earlier model, judged for comparison, has none
            "reasons": [r["id"] for r in result["reasons"]], "behaviour": behaviour.get("verdict"),
            "n_actions": behaviour.get("n_actions"), "too_little": behaviour.get("verdict") == TOO_LITTLE,
            "layers": {layer: state["state"] for layer, state in result["layers"].items()}, "site": site,
            "holdout": holdout,
            "evidence": evidence}


def lab(sessions, signals_by_run):
    """Every lab session that has its signals: environment, names and behaviour of its raw events."""
    out = []
    for run, session in sessions.items():
        signals = signals_by_run.get(run)
        if signals is None:
            continue
        built = evidence_builder.from_signals(signals, raw=session["raw"])
        out.append(row(run, "lab", session["group"], {"class": session["class"], "row": session["row"]}, built))
    return out


def lab_signals(sessions):
    """The lab's signal recordings (2026-11-09 and 11-11): no events, so no behaviour layer."""
    return [row(s["id"], "lab_signals", s["group"], {"class": s["class"], "row": s["row"]},
                evidence_builder.from_signals(s["signals"])) for s in sessions]


def cakejs(uploads, truth):
    """{name: uploads} of cake.js recorded with each upload's request headers; truth: the answer for all of them."""
    out = []
    for name, items in uploads.items():
        seen, batches = set(), []
        for item in items:
            batch = item["batch"]
            key = (batch["s"], batch["pv"], batch["seq"])
            if key not in seen:  # a batch sent twice is stored once
                seen.add(key)
                batches.append(batch)
        signals = env_signals.from_cake(batches, [{"headers": item["headers"]} for item in items])
        raw = sorted(({**r, "pg": b["pv"]} for b in batches for r in b.get("r") or []), key=lambda e: e["t"])
        out.append(row(name, "cakejs_uploads", truth["group"], truth,
                       evidence_builder.from_signals(signals, raw=raw or None)))
    return out


def recordings(items, truth):
    """Clean human recordings: the recorder's lab collectors give every page-side layer, its server the page
    requests and collect requests."""
    return [row(item["h"], "recordings", truth["group"], truth, _recording_evidence(item), item.get("site"))
            for item in items]


def recorded(items, source=RECORDED):
    """The recorder's labelled recordings, grouped by who operated them. Each uses the same layers as a clean
    recording and holds its label as the calibration fold. Source distinguishes the recordings people made
    (recorded) from the ones we ran ourselves (selfcollect)."""
    out = []
    for item in items:
        truth = {"class": item["truth"], "label": item["label"], "mode": item["mode"]}
        if item.get("variant"):
            truth["variant"] = item["variant"]
        out.append(row(item["h"], source, item["label"], truth, _recording_evidence(item), item.get("site"),
                       holdout=item["label"]))
    return out


def _recording_evidence(item):
    return evidence_builder.from_signals(env_signals.from_lab(item["payloads"], item["requests"]),
                                         raw=item["raw"] or None, rrweb=item["rrweb"] or None)


def posthog(units, groups_of, truth_of):
    """PostHog units judged on behaviour alone; groups_of(unit) names the group, truth_of(unit, group) its answer."""
    out = []
    for unit in units:
        group = groups_of(unit)
        built = evidence_builder.behaviour_only(unit["events"], raw_input=False, touch=unit["touch"],
                                                session_start=unit["start"])
        out.append(row(unit["h"], "posthog", group, truth_of(unit, group), built, holdout=unit.get("holdout")))
    return out


def public_humans(items):
    """Real people from public data sets (datasets.motion_attestation, datasets.public_humans): their events only,
    judged as cake.js's raw events are (a phone or a tablet is too little data)."""
    return [row(item["h"], "public_humans", item["set"], {"class": "human"},
                evidence_builder.behaviour_only(item["events"], raw_input=True, touch=item["touch"]), item["site"])
            for item in items]


def store(labelled):
    return [row(item["h"], "store", item["truth"].get("group") or item["truth"].get("case"), item["truth"],
                item["evidence"]) for item in labelled]


def site(labelled):
    """A copy of a website's data folder read through its list (sources.py): each session with its line's answer,
    group and site, judged as AgentCake judged it there."""
    return [row(item["h"], SITE, item["truth"].get("group"), item["truth"], item["evidence"], item["truth"].get("site"))
            for item in labelled]


def named(cases):
    out = []
    for case in cases:
        r = row(case["name"], "named", case["kind"], {"class": case["class"], "name": case["name"],
                                                        "kind": case["kind"]},
                evidence_builder.named_only(case["user_agent"]))
        out.append(r)
    return out


def right(r):
    """Whether a row's verdict is its answer: the class, and the row, name, kind and verification it gives."""
    truth = r["truth"]
    if r["class"] != truth.get("class"):
        return False
    return all(r[key] == truth[key] for key in ("row", "name", "kind", "verification") if truth.get(key))
