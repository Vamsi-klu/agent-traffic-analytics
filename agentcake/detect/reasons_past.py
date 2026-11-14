"""The facts of a reason kept before verdicts kept facts, read back from its sentence (D34: the words are display).

Such a session kept each reason's finished text only. agentcake/data/reasons_past.json lists every wording each reason,
and each phrase a fact names, had until then (tools/reasons_past.py collects them from git). facts() matches the kept
text against its reason's wordings, newest first, and turns the phrases back into what verdict_text keeps (a half's
words into its id, a mark's sentence into the mark and its times, a Web Bot Auth sentence into its result, ...). It
reads, never writes: nothing in the database changes, and a sentence no wording matches keeps its text.

    facts(kept) -> dict | None
"""
import functools
import re
import string

from agentcake import datafiles
from agentcake.units import MS_PER_S, S_PER_HOUR, S_PER_MIN

PAST_FILE = "data/reasons_past.json"
FAILED = object()
CLOCK_UNITS = (S_PER_HOUR, S_PER_MIN, 1)  # seconds in each part of markers.clock()'s h:mm:ss (m:ss or mm:ss under an hour)


def _past():
    return datafiles.load(PAST_FILE)


@functools.lru_cache(maxsize=None)
def _pattern(template):
    """A template as a regular expression: each {fact} a group (a fact said twice must be the same both times)."""
    parts, seen = [], set()
    for literal, name, _, _ in string.Formatter().parse(template):
        parts.append(re.escape(literal))
        if name is None:
            continue
        parts.append(f"(?P={name})" if name in seen else f"(?P<{name}>.+?)")
        seen.add(name)
    return re.compile("".join(parts), re.DOTALL)


def _match(templates, text):
    """(key, facts) of the first template that makes text, trying [(key, template), ...] in order; None if none does."""
    for key, template in templates:
        found = _pattern(template).fullmatch(text or "")
        if found:
            return key, found.groupdict()
    return None


def _each(table):
    return [(key, template) for key, templates in table.items() for template in templates]


def facts(kept):
    """The facts verdict_text keeps for a reason kept with its text only, or None when no wording of its id makes it."""
    past = _past()
    for template in past["reasons"].get(kept.get("id"), ()):
        found = _match([(None, template)], kept.get("text"))
        if found is None:
            continue
        decoded = _decode(found[1], past)
        if decoded is not FAILED:
            return decoded
    return None


def _decode(found, past):
    out = {}
    for name, value in found.items():
        decoded = DECODERS.get(name, _as_is)(value, past)
        if decoded is FAILED:
            return FAILED
        out.update(decoded if name in MERGED else {name: decoded})
    return out


def _as_is(value, past):
    return value


def _half(value, past):
    by_words = {template: key for key, template in _each(past["halves"])}
    if value in by_words:
        return by_words[value]
    parts = re.split(r", | and ", value)
    found = [by_words.get(part) for part in parts]
    return found if len(parts) > 1 and None not in found else FAILED


def _method(value, past):
    by_words = {template: key for key, template in _each(past["methods"])}
    return by_words.get(value, FAILED)


def _basis(value, past):
    names, out = [], {}
    for part in value.split("; "):
        found = _match(_each(past["behavior_basis"]), part)
        if found is None:
            return FAILED
        names.append(found[0])
        out.update(found[1])
    return {"basis": names, **out}


def _signals(value, past):
    keys, out = [], {}
    for part in value.split(", "):
        found = _match(_each(past["crawler_signals"]), part)
        if found is None:
            return FAILED
        keys.append(found[0])
        if "pages" in found[1]:
            out["pages"] = found[1]["pages"]
        if "every" in found[1]:
            seconds = _seconds(found[1]["every"], past)
            if seconds is FAILED:
                return FAILED
            out["every_s"] = seconds
    return {"signals": keys, **out}


def _seconds(value, past):
    found = _match(_each(past["durations"]), value)
    if found is None or not found[1].get("n", "").isdigit():
        return FAILED
    return int(found[1]["n"]) * (S_PER_MIN if found[0] == "minutes" else 1)


def _marker(value, past):
    """An indicator's sentence ("… was on 00:42–01:15") as the mark and its times from the visit's start."""
    found = _match(_each(past["markers"]), value)
    if found is None:
        return FAILED
    span = _match(_each(past["spans"]), found[1].get("span", ""))
    if span is None:
        return FAILED
    began, ended = _ms(span[1].get("from")), _ms(span[1].get("to")) if span[0] == "closed" else None
    if began is FAILED or ended is FAILED:
        return FAILED
    return {"marker": found[0], "from_ms": began, "to_ms": ended}


def _ms(clock):
    """markers.clock()'s words (m:ss, mm:ss or h:mm:ss) as ms."""
    parts = (clock or "").split(":")
    if not 1 < len(parts) <= len(CLOCK_UNITS) or not all(part.isdigit() for part in parts):
        return FAILED
    return sum(int(part) * unit for part, unit in zip(reversed(parts), reversed(CLOCK_UNITS))) * MS_PER_S


def _signature(value, past):
    """A Web Bot Auth sentence as its result: the code and the facts it was filled with."""
    found = _match(_each(past["webbotauth"]), value)
    if found is None:
        return FAILED
    return {"signature": {"code": found[0], **found[1]}}


DECODERS = {"half": _half, "method": _method, "other_method": _method, "basis": _basis, "signals": _signals,
            "words": _marker, "detail": _signature}
MERGED = {"basis", "signals", "words", "detail"}  # each gives several facts, or one under a new name
