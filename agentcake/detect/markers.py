"""Agent products' marks on the page, and when each was there (S3.3, S3.7; GOAL A5: where a person took over).

agentcake/data/agent_markers.json lists the marks; cake.js watches them (static/src/markers.js) and sends a `marker`
record when one appears or goes away, and a `markers` record when its watch starts and at exit (docs/collect-format.md).
This module reads that table, one page view's records and a session's signals:

    load_table(path=None) -> MarkerTable              the table, checked (MarkersError when malformed); read once
    page_marks(records, table=None, raw=(), until=None) -> dict | None
                                                       one page view of cake.js: {"list", "from", "until", "hidden",
                                                       "spans": [...]}, or None when its watch did not run
    recorder_marks(items, table=None) -> dict | None   one page view of the recorder: its raw.js
                                                       `overlay` items as the mark the table's "recorder" names
    turn_spans(signals, table=None) -> [span]          when an agent product said its agent was working: the spans of
                                                       the table's turn_kinds over the session, cut where the page was
                                                       hidden (S3.7's timeline gives the actions inside to the agent)
    describe(span, start_ms, table=None) -> str        a span in the table's words, for a reason, e.g.
                                                       "Claude in Chrome's “working” indicator was on 00:42–01:15"
    words(marker, from_ms, to_ms, field="text", table=None) -> str | None
                                                       the same from times since the visit's start; field "detail"
                                                       gives the mark's technical words (verdict_text keeps the times)

A span is {"marker", "product", "kind", "from", "to"}: times in epoch ms, `to` None for a mark still there when the page
view's records end; product and kind come from the table (None for a mark it does not list: a newer cake.js). A page
view without the watch's start record was recorded by a cake.js without the watch, or left before its load event:
page_marks() gives None (not known), never an empty list (watched, and nothing seen). `from` is when the watch began:
a mark's state before then is not known; `until` is the page view's last record; `hidden` lists the times the page was
hidden ([from, to], `to` None to the end), when no mark is drawn (cake.js does not look then), so a mark's state there
is not known either.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from agentcake import paths
from agentcake.detect.env_rules import load_rules
from agentcake.units import MS_PER_S, S_PER_HOUR, S_PER_MIN

TABLE_FILE = os.path.join(paths.PACKAGE_DIR, "data", "agent_markers.json")
MARK_RECORD, WATCH_RECORD, WATCH_START = "marker", "markers", "start"  # protocol: cake.js's record types (format v1)
SHOWN, GONE = 1, 0  # protocol: a marker record's `on`
VISIBILITY, VISIBLE, HIDDEN = "visibility", 1, 0  # protocol: the raw visibility record and its vs (cake.js, raw.js)
OVERLAY = "overlay"  # protocol: the recorder's raw.js item for its own check of Claude in Chrome's indicator
RECORDER_LIST = "recorder"  # the `list` of a recorder page view: its own check, not a version of the table
EDGES = ("top", "bottom")  # a spot is measured from one of these edges of the viewport
_META_FIELDS = ("product", "kind", "versions", "date", "grade", "evidence", "sources", "collisions", "text")
_SELECTOR_ATTRIBUTES = re.compile(r"\[\s*([\w-]+)")


class MarkersError(ValueError):
    """The mark table is malformed: raised when it is loaded, so a typo never reaches the page script or a reason."""


@dataclass(frozen=True)
class MarkerTable:
    version: str
    page: dict        # what cake.js gets (CFG.markers)
    markers: dict     # mark id -> what it is (product, kind, versions, date, grade, evidence, sources, ..., text)
    spans: dict       # how a span is written: {"closed": ..., "open": ...}
    turn_kinds: tuple  # the kinds whose spans bound the agent's turn
    recorder: dict    # the recorder's record of the indicator -> the mark it stands for


def _check_page_mark(mark, attributes):
    mark_id = mark.get("id")
    has_spots, has_element = "spots" in mark, "ids" in mark or "selector" in mark
    if has_spots == has_element:
        raise MarkersError(f"{mark_id}: give either spots, or ids and a selector")
    for spot in mark.get("spots", ()):
        edges = [edge for edge in EDGES if edge in spot]
        if len(edges) != 1 or not 0 <= spot.get("x", -1) <= 1:
            raise MarkersError(f"{mark_id}: a spot needs x from 0 to 1 and one of {EDGES}")
    unread = sorted(set(_SELECTOR_ATTRIBUTES.findall(mark.get("selector", ""))) - set(attributes))
    if unread:
        raise MarkersError(f"{mark_id}: its selector reads {unread}, which page.attributes does not list")


def _check_meta(mark_id, meta, kinds, grades, sources):
    missing = [field for field in _META_FIELDS if field not in meta]
    if missing:
        raise MarkersError(f"{mark_id}: missing {missing}")
    if meta["kind"] not in kinds or meta["grade"] not in grades:
        raise MarkersError(f"{mark_id}: kind {meta['kind']!r} or grade {meta['grade']!r} is not in the legends")
    strays = [source for source in meta["sources"] if source not in sources]
    if strays:
        raise MarkersError(f"{mark_id}: sources {strays} are not in source_refs")
    if "{span}" not in meta["text"]:
        raise MarkersError(f"{mark_id}: its text has no {{span}}")


def parse_table(data, grades=None):
    """A MarkerTable from the decoded JSON; raises MarkersError on anything malformed. `grades`: the evidence grades
    (env_rules.json's legend)."""
    grades = grades if grades is not None else load_rules().legend["grades"]
    try:
        page, markers, kinds = data["page"], data["markers"], data["legend"]["kinds"]
        ids = [mark["id"] for mark in page["markers"]]
        for mark in page["markers"]:
            _check_page_mark(mark, page["attributes"])
        for mark_id, meta in markers.items():
            _check_meta(mark_id, meta, kinds, grades, data["source_refs"])
        strays = [kind for kind in data["turn_kinds"] if kind not in kinds]
        if strays:
            raise MarkersError(f"turn_kinds {strays} are not in the kinds legend")
        table = MarkerTable(page["version"], page, markers, data["spans"], tuple(data["turn_kinds"]),
                            dict(data["recorder"]))
    except (KeyError, TypeError, AttributeError) as err:
        raise MarkersError(f"mark table is missing {err}") from err
    duplicates = sorted({mark_id for mark_id in ids if ids.count(mark_id) > 1})
    watched = set(ids) | set(table.recorder.values())
    if duplicates or watched != set(markers):
        raise MarkersError(f"duplicate {duplicates}, or watched marks and described marks differ: "
                           f"{sorted(watched ^ set(markers))}")
    return table


@lru_cache(maxsize=None)
def load_table(path=TABLE_FILE):
    """The mark table shipped with Agent Cake (or another file, for tests)."""
    with open(path, encoding="utf-8") as handle:
        return parse_table(json.load(handle))


def _span(table, mark_id, start, end):
    meta = table.markers.get(mark_id) or {}
    return {"marker": mark_id, "product": meta.get("product"), "kind": meta.get("kind"), "from": start, "to": end}


def _time(record):
    value = record.get("t")
    return value if isinstance(value, (int, float)) else None


def _hidden(raw, until):
    """When the page was hidden: from each visibility record that says hidden to the next that says visible (or
    `until`, None when that is not known)."""
    spells, since = [], None
    for record in sorted((r for r in raw if r.get("ty") == VISIBILITY and _time(r) is not None), key=_time):
        if record.get("vs") == HIDDEN and since is None:
            since = _time(record)
        elif record.get("vs") == VISIBLE and since is not None:
            spells.append([since, _time(record)])
            since = None
    if since is not None:
        spells.append([since, until])
    return spells


def page_marks(records, table=None, raw=(), until=None):
    """One page view's marks from its signal records (the `x` stream), or None when the watch did not run there.
    raw: the page view's raw records (their visibility records give `hidden`); until: its last record's time."""
    table = table or load_table()
    starts = [record for record in records
              if record.get("ty") == WATCH_RECORD and record.get("why") == WATCH_START and _time(record) is not None]
    if not starts:
        return None
    start = min(starts, key=_time)
    changes = sorted((record for record in records if record.get("ty") == MARK_RECORD
                      and isinstance(record.get("m"), str) and _time(record) is not None), key=_time)
    spans, shown = [], {}
    for record in changes:  # a repeated state (a copy, or a record out of turn) changes nothing
        mark_id = record["m"]
        if record.get("on") == SHOWN and mark_id not in shown:
            shown[mark_id] = _time(record)
        elif record.get("on") == GONE and mark_id in shown:
            spans.append(_span(table, mark_id, shown.pop(mark_id), _time(record)))
    spans += [_span(table, mark_id, began, None) for mark_id, began in shown.items()]
    return {"list": start.get("list"), "from": _time(start), "until": until, "hidden": _hidden(raw, until),
            "spans": sorted(spans, key=lambda span: span["from"])}


def recorder_marks(items, table=None):
    """One page view of the recorder: its raw.js items, whose `overlay` items (`on` 1 or 0, from its first item on)
    are read as the mark the table's "recorder" names; None when the page has none (the check may not have run)."""
    table = table or load_table()
    overlay = [item for item in items if item.get("ty") == OVERLAY and _time(item) is not None]
    if not overlay:
        return None
    times = [_time(item) for item in items if _time(item) is not None]
    mark_id = table.recorder[OVERLAY]
    records = [{"t": min(times), "ty": WATCH_RECORD, "why": WATCH_START, "list": RECORDER_LIST}]
    records += [{"t": _time(item), "ty": MARK_RECORD, "m": mark_id, "on": SHOWN if item.get("on") else GONE}
                for item in overlay]
    return page_marks(records, table, raw=items, until=max(times))


def _without(start, end, holes):
    """[start, end] minus the holes ([from, to], `to` None to the end), as [[from, to], ...]."""
    pieces = [[start, end]]
    for hole_from, hole_to in holes:
        hole_to = end if hole_to is None else hole_to
        cut = []
        for piece_from, piece_to in pieces:
            if hole_to <= piece_from or hole_from >= piece_to:
                cut.append([piece_from, piece_to])
                continue
            if piece_from < hole_from:
                cut.append([piece_from, hole_from])
            if hole_to < piece_to:
                cut.append([hole_to, piece_to])
        pieces = cut
    return pieces


def turn_spans(signals, table=None):
    """The spans of the table's turn_kinds over a session (env_signals' dict): each page view's, a span still open at
    its end closed at its last record, and cut where that page was hidden. Sorted by their start."""
    table = table or load_table()
    out = []
    for page in signals.get("pages") or []:
        marks = page.get("markers") or {}
        for span in marks.get("spans") or ():
            end = span["to"] if span["to"] is not None else marks.get("until")
            if span["kind"] not in table.turn_kinds or end is None:
                continue
            out += [dict(span, **{"from": begin, "to": finish})
                    for begin, finish in _without(span["from"], end, marks.get("hidden") or ())]
    return sorted(out, key=lambda span: span["from"])


def clock(ms):
    """A moment as the replay's player writes it (web/src/lib/format.ts clock): whole seconds rounded down, m:ss under
    an hour (0:42), else h:mm:ss."""
    seconds = max(0, int(ms // MS_PER_S))
    hours, rest = divmod(seconds, S_PER_HOUR)
    minutes, seconds = divmod(rest, S_PER_MIN)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def describe(span, start_ms, table=None):
    """A span in words (the mark's text, its {span} filled in), times from the visit's start at start_ms."""
    return words(span["marker"], span["from"] - start_ms, None if span["to"] is None else span["to"] - start_ms,
                 table=table)


def words(marker, from_ms, to_ms, field="text", table=None):
    """A mark's text (or its detail, field="detail") with its span filled in, times in ms from the visit's start
    (to_ms None: still there at the end); None for a mark or a field the table does not have."""
    table = table or load_table()
    template = (table.markers.get(marker) or {}).get(field)
    if template is None or from_ms is None:
        return None
    began = clock(from_ms)
    if to_ms is None:
        said = table.spans["open"].format(**{"from": began})
    else:
        said = table.spans["closed"].format(**{"from": began, "to": clock(to_ms)})
    return template.format(span=said)
