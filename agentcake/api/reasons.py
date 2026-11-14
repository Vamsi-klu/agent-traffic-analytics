"""The four layers of "Why this verdict" (S5.1; S5.4 draws them): each layer's state and reasons, from the verdict.

The verdict (judging.py) keeps each layer's state, which way it leans and how sure (verdict.py's layers: {"state",
"why"?, "leans", "percent"}; detect/confidence.py; None in a verdict kept before S3.7) and its reasons layer by layer
(verdict_text.reason). The page has the four layers name, verify, environment and behavior; a reason of a layer
it does not have (weak signals, crawler-like patterns) shows in the layer data/api.json "reasons" names for it, and a
prefetch's exclusion reasons never show (such a session is no visit). Each reason keeps its tone and its text and gets
the kind of evidence the page draws an icon for (data/api.json "reasons", in the order its comment gives). A layer the
verdict does not name (a session judged before S3.4) is off. A reason is worded as it is shown (verdict_text.words: today's
text, and its detail, the technical evidence the page shows under it, or None), not as it was when judged.

    layers(layers_json, reasons_json, origin=None, turns=False, verdict=None) -> [LayerReasons], in the order name,
                       verify, environment, behavior; origin: the replay's start, from which the reasons say their
                       moments. A layer's state is its conclusion and its percent how sure it is of that conclusion
                       (none when the layer leans the other way); a layer less than half sure of its conclusion reads
                       Unknown, with a first line that says its evidence points both ways; in a session with hand-offs
                       the behavior layer is Human + agent and words the model's line as data/api.json "turns_words"
                       says
    stored(reasons_json) -> the verdict's reasons, as it kept them
"""
import functools
import json

from agentcake.api.answers import numbers, words
from agentcake.detect import env_rules, verdict_text

ENVIRONMENT, PAGE_HALF, BEHAVIOR = "environment", "page", "behavior"
OFF, UNKNOWN_STATE, NO_HIT, HUMAN_AGENT = "off", "unsure", "no_hit", "human_agent"
HUMAN, AGENT, BOT, NO_TONE = "human", "agent", "bot", "none"
AGREES = {HUMAN_AGENT: ("agent",)}  # a Human + agent layer's percent is how sure it is that an agent took part
UNKNOWN = "unknown"  # data/api.json layer_states: a layer that can't tell
HALF = 50  # protocol: a percent under half says the layer's own conclusion is less likely than not


def _table():
    return numbers()["reasons"]


@functools.lru_cache(maxsize=None)
def _env_rule_kinds():
    return {rule.id: rule.kind for rule in env_rules.load_rules().rules}


def stored(reasons_json):
    return json.loads(reasons_json) if reasons_json else []


def layers(layers_json, reasons_json, origin=None, turns=False, verdict=None):
    """The four layers as the page shows them; origin: the replay's start (the reasons' moments), turns: whether the
    session's timeline has hand-offs (its behavior layer then reads Human + agent), verdict: the session's (a Bot's
    environment layer that found an agent says why the verdict is still Bot)."""
    table, states = _table(), numbers()["layer_states"]
    kept = json.loads(layers_json) if layers_json else {}
    shown = {layer: [] for layer in table["layers"]}
    for reason in stored(reasons_json):
        layer = interface_layer(reason)
        if layer:
            worded = dict(reason, id=table["turns_words"].get(reason.get("id"), reason.get("id"))) if turns else reason
            text, detail = verdict_text.words(worded, origin)
            shown[layer].append((reason.get("id") in table["layer_by_id"], reason.get("id"),
                                 {"kind": kind(reason, layer), "tone": reason["tone"], "text": text, "detail": detail}))
    out = []
    for layer in table["layers"]:
        own = kept.get(layer) or {}  # its state, and since S3.7 which way it leans and how sure (confidence.py)
        state = _shown_state(layer, states.get(own["state"], UNKNOWN_STATE) if own.get("state") else OFF, turns,
                             verdict)
        sure = own.get("leans") is not None and own.get("leans") in AGREES.get(state, (state,))
        # a layer's own evidence first, then what data/api.json brings into it (a name after the trace it was read
        # from), only what agrees with the layer's conclusion, and a sentence said twice once
        found = _merged([said for _, reason_id, said in sorted(shown[layer], key=lambda entry: entry[0])
                         if _agrees(table, state, reason_id, said["tone"])])
        percent = own.get("percent") if sure else None
        if percent is not None and percent < HALF:  # its own conclusion is less likely than not: it can't tell
            state, percent, found = UNKNOWN, None, [_note(table, layer, "both_ways")] + found
        if verdict == BOT and layer == table["bot_note_layer"] and state == AGENT:
            found = found + [_note(table, layer, "bot_environment")]
        # a percent is how sure the layer is of its own conclusion: one that leans the other way is not shown
        out.append({"layer": layer, "state": state, "reasons": found, "percent": percent,
                    "leans": own.get("leans") if percent is not None else None})
    return out


def _shown_state(layer, state, turns, verdict):
    """The behavior layer follows the session's timeline both ways: Human + agent when it has hand-offs, the verdict's
    own side when it has none; any other layer as it is."""
    if layer != BEHAVIOR or state in (OFF, NO_HIT):
        return state
    if turns:
        return HUMAN_AGENT
    return verdict if state == HUMAN_AGENT and verdict in (AGENT, HUMAN) else state


def _agrees(table, state, reason_id, tone):
    """Whether a reason fits the conclusion its layer shows: a reason for one side only beside that side's conclusion
    (data/api.json "tone_states"), one data/api.json "only_when" names only beside the states it lists."""
    allowed = table["only_when"].get(reason_id) or table["tone_states"].get(tone)
    return state == UNKNOWN or not allowed or state in allowed


def _merged(found):
    """A layer's reasons with one sentence said twice (the same evidence read from two halves) said once, its details
    joined."""
    out, by_text = [], {}
    for said in found:
        first = by_text.get(said["text"])
        if first is None:
            by_text[said["text"]] = said = dict(said)
            out.append(said)
        elif said["detail"] and said["detail"] != first["detail"]:
            first["detail"] = " ".join(filter(None, (first["detail"], said["detail"])))
    return out


def _note(table, layer, key):
    """A line the page adds to a layer (api.en.json "layer_notes"): a fact for neither side, in the layer's icon."""
    return {"kind": table["by_layer"][layer], "tone": NO_TONE, "text": words()["layer_notes"][key], "detail": None}


def interface_layer(reason):
    """The page's layer for a reason (the layer its evidence belongs to: data/api.json "reasons"), or None for one
    it does not show."""
    table, layer = _table(), reason.get("layer")
    if reason.get("id") in table["layer_by_id"]:
        return table["layer_by_id"][reason["id"]]
    return layer if layer in table["layers"] else table["other_layers"].get(layer)


def kind(reason, layer):
    table, reason_id = _table(), reason.get("id")
    if reason_id in table["kind_by_id"]:
        return table["kind_by_id"][reason_id]
    if layer == ENVIRONMENT:
        rule_kind = _env_rule_kinds().get(reason_id)
        if rule_kind and reason.get("source") == PAGE_HALF:
            return table["env_rule_kinds"][rule_kind]
        if reason.get("source") in table["by_source"]:
            return table["by_source"][reason["source"]]
    return table["by_layer"][layer]
