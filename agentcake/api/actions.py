"""'All actions' of a session (the session page lists it): the pages opened and what the visitor did, never what was typed.

An action is a page opened (cake.js's page record, kept per page view; the rrweb Meta event of a cake 0.3.x recording)
or one of the visitor's own actions in the raw stream, as data/actions.json defines them for the whole of AgentCake
(detect/visitor_actions.py: a click, a key or typed input, a wheel, a scroll the visitor's own input caused; a page
that scrolls itself makes none). Keys and typing on the same target and page, each closer than action_merge_ms to the
one before, are one action, typing when they typed ("Type in #email"), else keys ("Press a key on #search": cake.js
never records which key); a wheel and the scrolling it causes on one page are one scroll. A recording without raw
input (cake 0.3.x) gives the input rrweb kept (detect/rrweb_events.py), by the same definition. Each action says what in words (api.en.json: "Click #add", "Type in #email"; cake.js keeps
a field's length, never its text, and no selector of a private field), who acted (the stored segment it falls in;
outside every segment, `whole`: the verdict of a Human or an Agent only session, else unsure) and on which page (pages.py: the
page of its page view open then, so a single-page app's new address shows). The list holds at most data/api.json
max_actions, the earliest; the pages section counts them all.

    recorded(con, session_id, runs, whole, views) -> [Action]   every action, in time order, with who took it; a
                                                                  cake 0.3.x recording adds its pages' addresses to
                                                                  views (pages.views)
    listed(found, path_of, epoch) -> [contract Action]            "All actions": the first max_actions; path_of(action)
                                                                  is the address of the page it was taken on
    who_at(runs, whole) -> who(t)                                 who acted at a moment
    share(found) -> {human, agent, unsure}                        each actor's share of the actions, whole percents
    taken(con, session_id, verdict, turns, runs) -> [Action]      every action of one tab session, as its page
                                                                  finds them (a session's share counts all its
                                                                  tabs' together: rows.py)
"""
import json
from collections import namedtuple

from agentcake import streams
from agentcake.api import visits
from agentcake.api.answers import numbers, words
from agentcake.api import pages
from agentcake.api.pages import Address
from agentcake.detect import rrweb_events, visitor_actions

RAW, SIGNALS, REPLAY = "raw", "env", "rrweb"
PAGE_RECORD = "page"  # protocol: the record cake.js sends when a page view begins (cake_main.js)
OPEN = "open"
TYPE, KEY, SCROLL = "type", "key", "scroll"  # data/actions.json's kinds that join their neighbours
KEYBOARD = (TYPE, KEY)  # keys and typing on one target are one action: typing when it typed
WHOLE_VERDICTS = ("human", "agent")  # a Human's or an Agent's input outside every segment is still theirs
UNSURE, HUMAN_AGENT = "unsure", "human_agent"
TARGET = "s"  # protocol: the raw record's selector of its target (cake.js raw.js)
# One action: when (epoch ms on the events' clock), its kind (OPEN or data/actions.json's), its target's selector,
# its page view (cake.js's pv; a 0.3.x Meta event's href; None when it has none) and who took it.
Action = namedtuple("Action", "t kind target view who")


def share(found):
    """Each actor's share of the session's actions (the ones All actions lists, without the pages opened), whole
    percents that add up to 100; all 0 for a session with no action."""
    taken = [action.who for action in found if action.kind != OPEN]
    return dict(zip(visits.WHO, visits.whole_percents([taken.count(who) for who in visits.WHO])))


def taken(con, session_id, verdict, turns, runs):
    """recorded() of one tab session, found as its page finds them (the session list's share is the page's): verdict
    and turns, its own verdict and agent_turns; runs, its stored segments (t_start, t_end, actor)."""
    whole = None if turns == HUMAN_AGENT else verdict  # a Human + agent session's input outside every run is unsure
    return recorded(con, session_id, runs, whole, pages.views(con, session_id))


def recorded(con, session_id, runs, whole, views):
    """Every action of the session, oldest first, input merged as the module docstring says, with who took it."""
    found = _raw_actions(con, session_id) + _page_opens(con, session_id) or _replay_actions(con, session_id, views)
    merged = []
    for t, kind, target, view in sorted(found, key=lambda action: action[0]):
        last = merged[-1] if merged else None
        if (last and last["view"] == view and t - last["until"] <= numbers()["action_merge_ms"]
                and _joins(last, kind, target)):
            last["until"] = t
            last["kind"] = TYPE if TYPE in (kind, last["kind"]) else last["kind"]
            continue
        merged.append({"t": t, "until": t, "kind": kind, "target": target, "view": view})
    who = who_at(runs, whole)
    return [Action(action["t"], action["kind"], action["target"], action["view"], who(action["t"])) for action in merged]


def listed(found, path_of, epoch):
    """The first max_actions of found as "All actions" lists them: when (ms from epoch), who, what, which page."""
    return [{"at_ms": max(0, round(action.t - epoch)), "who": action.who, "what": _what(action, path_of),
             "page": path_of(action)} for action in found[:numbers()["max_actions"]]]


def who_at(runs, whole):
    """who(t): the actor of the stored segment a moment falls in; outside every segment, whole: the verdict of a Human or
    an Agent only session (None for a Human + agent session), else unsure."""
    fallback = whole if whole in WHOLE_VERDICTS else UNSURE

    def who(t):
        for t_start, t_end, actor in runs:
            if t_start <= t <= t_end:
                return actor
        return fallback
    return who


def _joins(last, kind, target):
    """Whether input of this kind on this target belongs to the action before it (both on one page, close enough):
    keys and typing on the same target, or scrolling (a wheel names the element under the pointer, the scroll it
    causes none)."""
    if kind in KEYBOARD and last["kind"] in KEYBOARD:
        return last["target"] == target
    return kind == SCROLL and last["kind"] == SCROLL


def _raw_actions(con, session_id):
    definition = visitor_actions.load()
    wanted = set(definition["kinds"]) | set(definition["caused_by"])  # the actions and the input a scroll needs
    records, views = [], {}
    for _, _, text, page in streams.read_events(con, session_id, [RAW], with_page=True):
        if not any(name in text for name in wanted):
            continue
        record = json.loads(text)
        if record.get("ty") in wanted and record.get("t") is not None:
            records.append(record)
            views[id(record)] = page
    return [(record["t"], kind, record.get(TARGET), views[id(record)])
            for record, kind in visitor_actions.found(records, definition)]


def _page_opens(con, session_id):
    out = []
    for _, _, text, page in streams.read_events(con, session_id, [SIGNALS], with_page=True):
        if PAGE_RECORD in text:
            record = json.loads(text)
            if record.get("ty") == PAGE_RECORD and record.get("t") is not None:
                out.append((record["t"], OPEN, None, page))
    return out


def _replay_actions(con, session_id, views):
    """The input and pages of a recording with neither raw input nor page records (cake 0.3.x), from its rrweb
    events; adds each page's address to views, its href standing for its page view."""
    events = []
    for _, _, text in streams.read_events(con, session_id, [REPLAY]):
        events.append(json.loads(text))
    out = [(event["timestamp"], OPEN, None, event["data"].get("href")) for event in events
           if event.get("type") == rrweb_events.META and isinstance(event.get("data"), dict)]
    for href in {href for _, _, _, href in out if href}:
        views.setdefault(href, [Address(None, visits.page_path(href))])
    out += [(event["t"], kind, None, None)
            for event, kind in visitor_actions.found(rrweb_events.events_from_rrweb(events))]
    return out


def _what(action, path_of):
    said = words()["actions"]
    if action.kind == OPEN:
        return said["open"].format(page=path_of(action))
    if action.target and action.kind in said and "{target}" in said[action.kind]:
        return said[action.kind].format(target=action.target)
    return said.get(action.kind + "_plain", said[action.kind])
