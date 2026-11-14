"""Where `agentcake eval` finds each data set, and loading what is there (plan step S3.9).

    locate(options, settings) -> {key: path or None}
    load(where, settings) -> {"lab", "lab_signals", "uploads", "recordings", "recorded", "selfcollect", "posthog",
                              "store", "named", "public_humans", "notes"}

A location comes from, in this order: the command line; the sources file (--sources, default eval/sources.json
of a checkout, which git ignores; eval/sources.example.json lists the keys, and S1.5's "out_dir" names the PostHog
dataset); for the files a checkout carries, data/eval.json "files" next to the package. Relative paths are read
from the current folder, like any command's. Data that only lives on one computer (the recorder's folder, the
PostHog dataset, a CAKE_HOME, the folder of the recorder copy our own runs used) is never guessed: without a
location it is skipped and the report says so. The
CAKE_HOME of truth_goal.jsonl's sessions defaults to the current one (CAKE_HOME, else ~/.cake).
"""
import json
import os

from agentcake import paths
from agentcake.evaluation import datasets, store

KEYS = ("thresholds", "named_user_agents", "truth_manual", "truth_goal", "truth_recordings", "lab_sessions",
        "lab_signals", "cakejs_uploads", "recordings", "posthog", "cake_home", "motion_attestation", "public_humans",
        "selfcollect", "truth_selfcollect")
CHECKOUT = os.path.dirname(paths.PACKAGE_DIR)
SOURCES_FILE = "sources"
ALIASES = {"out_dir": "posthog"}  # the research tools' key for the same folder
# agentcake/eval.py's options for the files a checkout carries, named when one is not found
FLAGS = {"lab_sessions": "--lab", "lab_signals": "--lab-signals", "cakejs_uploads": "--uploads",
         "named_user_agents": "--named"}


def locate(options, settings):
    """{key: path or None}: options (a dict of command-line values) win over the sources file and the checkout."""
    files = settings["files"]
    sources_path = options.get(SOURCES_FILE) or _checkout_file(files.get(SOURCES_FILE))
    from_file = _read_sources(sources_path)
    where = {}
    for key in KEYS:
        value = options.get(key) or from_file.get(key) or _checkout_file(files.get(key))
        where[key] = os.path.abspath(os.path.expanduser(value)) if value else None
    if where["cake_home"] is None and where["truth_goal"]:
        where["cake_home"] = paths.home()
    where[SOURCES_FILE] = os.path.abspath(sources_path) if sources_path else None
    return where


def load(where, settings):
    """Every data set that is there; notes says, for each one that is not, what to give."""
    data, notes = {}, {}
    data["lab"] = _load(where, "lab_sessions", notes, lambda p: datasets.lab_sessions(p, settings))
    signals = _load(where, "lab_signals", notes, lambda p: datasets.lab_signals(p, settings))
    data["lab_signals"] = signals or []
    data["uploads"] = _load(where, "cakejs_uploads", notes, datasets.cakejs_uploads) or {}
    data["named"] = _load(where, "named_user_agents", notes, datasets.named_user_agents) or []
    data["recordings"], data["recorded"] = [], []
    if where["recordings"] and os.path.isdir(where["recordings"]):
        data["recordings"] = datasets.recordings(where["recordings"], where["truth_manual"], settings)
        if not data["recordings"]:
            notes["recordings"] = "no clean recording yet: the clean recordings' list (--truth-manual) names none that the folder has"
        data["recorded"] = datasets.recorded(where["recordings"], where["truth_recordings"], settings)
        if not data["recorded"]:
            notes["recorded"] = ("no agent or hand-off recording yet: the recordings' list (--truth-recordings) names none that "
                                 "the folder has")
    else:
        notes["recordings"] = "not given (--recordings: the S1.5 recorder's data folder)"
        notes["recorded"] = notes["recordings"]
    data["selfcollect"] = _self_collected(where, settings, notes)
    data["posthog"] = None
    if where["posthog"] and os.path.isdir(where["posthog"]):
        data["posthog"] = datasets.posthog(where["posthog"], settings)
    else:
        notes["posthog"] = "not given (--posthog: S1.5's local PostHog dataset, the out_dir of eval/sources.json)"
    data["public_humans"] = _public_humans(where, notes)
    truth = datasets.jsonl(where["truth_goal"])
    data["store"] = store.labelled(truth, settings, where["cake_home"]) if truth else []
    if not truth:
        notes["store"] = "no session listed yet (eval/truth_goal.jsonl: GOAL T3, T5, T6, T8, T22 runs)"
    elif not data["store"]:
        notes["store"] = "none of the listed sessions is in the CAKE_HOME given (--cake-home)"
    data["notes"] = notes
    return data


def _self_collected(where, settings, notes):
    """The recordings we ran ourselves (S9.4: Claude Code with an MCP server, automation dressed up as a human), from
    the recorder copy they were made on: a data set of their own, never added to people's recordings."""
    folder = where["selfcollect"]
    if not (folder and os.path.isdir(folder)):
        notes["selfcollect"] = "not given (--selfcollect: the data folder of the recorder copy our own runs used)"
        return []
    found = datasets.recorded(folder, where["truth_selfcollect"], settings)
    if not found:
        notes["selfcollect"] = "no recording yet: the list of our own runs (--truth-selfcollect) names none that the folder has"
    return found


def _public_humans(where, notes):
    """motion-attestation's captures (a checkout's fixture) and the local PSAI and CaptchaSolve30k file, if given."""
    found = []
    if where["motion_attestation"] and os.path.isfile(where["motion_attestation"]):
        found += datasets.motion_attestation(where["motion_attestation"])
    else:
        notes["motion_attestation"] = "not found: a checkout's tests/fixtures/motion_attestation/humans.json"
    if where["public_humans"] and os.path.isfile(where["public_humans"]):
        found += datasets.public_humans(where["public_humans"])
    else:
        notes["public_humans"] = ("not given (public_humans in the sources file: the file "
                                  "the maintainers' converter writes)")
    return found


def _load(where, key, notes, reader):
    path = where[key]
    if not path or not os.path.exists(path):
        notes[key] = f"not found: give {FLAGS[key]}"  # the report never names a local path
        return None
    return reader(path)


def _checkout_file(relative):
    if not relative:
        return None
    path = os.path.join(CHECKOUT, relative)
    return path if os.path.exists(path) else None


def _read_sources(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {ALIASES.get(key, key): value for key, value in raw.items()
            if isinstance(value, str) and not key.startswith("_")}
