"""A session of more than one tab, as its page shows it (GET /api/session/<id>).

A session spans its browser's tabs (tabs.py). Each tab session is judged on its own, and the page shows each tab as
PostHog's replay shows each window of a recording. Beside what a session of one tab has (session.py), the answer has:
    tabs         each tab session in the order it opened, as session.seen() reads it on the session's clock: its id (its
                 replay's ?tab=), its tab number, when its recording starts and ends, its own verdict, agent and how
                 sure, its own summary and reasons, its own track (who acted when, its hand-offs) and its replay
    follow       which tab the replay shows at each moment while it follows the visitor: PostHog's segmenter
                 (segmenter.py) over each tab's activity (activity.times: the pages opened and the visitor's input) and
                 the first and last moment its replay holds
    verdict_tab  the tab the verdict rests on: of the tabs whose own verdict is the session's, the surest (one with
                 enough evidence before one on thin evidence, which counts for nothing beside it; then the highest
                 percent; the first of equals); the page's summary, layers and percent are its
    named_tab    the tab an address from before sessions spanned tabs named, when it is one of these: the page opens
                 with it picked
The rest is read over all its tabs: the title tells who acted, in all of them and in time order (session.title); the
timeline holds every tab's runs and hand-offs, with a Human + agent session's hand-offs from one tab to another (where
the actor changes from one tab's run to another tab's: no judge marks those, as each tab is judged on its own); the
pages, the actions and the server half are every tab's in time order, each with its tab's number (the server half's
network is the first tab's that has one); replay is the first tab's, with the session's clock (epoch_ms).

    detail(con, summary, parts, named) -> SessionDetail   summary: the session's row (rows.py); parts: tabs.parts()
"""
import json

from agentcake import activity, streams
from agentcake.api import actions, answers, replay, segmenter, server_half, tabs, visits
from agentcake.api import session as one_tab
from agentcake.api.segmenter import Event
from agentcake.session_replay import STREAM

RAW = "raw"  # the stream cake.js's raw input records are kept in (upload.RECORD_FIELDS)
HUMAN_AGENT, UNSURE = "human_agent", "unsure"
TAB_REPLAY = ("start_ms", "start_url", "chunks", "missing")  # a tab's own part of a replay's info (web: TabReplay)


def detail(con, summary, parts, named):
    epoch, length = tabs.clock(parts)
    shown = [_seen(con, part, epoch, length) for part in parts]
    rests = _verdict_tab(parts, shown, summary["verdict"])
    acting = _acting(parts, summary["verdict"])
    crossed = _crossings(shown, epoch, length, acting) if summary["agent_turns"] == HUMAN_AGENT else {}
    handoffs = [handoff for index, one in enumerate(shown) for handoff in one.handoffs + crossed.get(index, [])]
    pages = _in_time([dict(page, tab=part.tab) for part, one in zip(parts, shown) for page in one.pages])
    body = {"session": dict(summary, duration_ms=length, pages=len(pages),
                            share=actions.share([action for one in shown for action in one.found])),
            "title": _title(con, summary, parts, shown, rests, acting),
            "summary": shown[rests].summary,
            "percent": shown[rests].percent,
            "timeline": {"duration_ms": length,
                         "segments": _in_time([segment for one in shown for segment in one.segments], "start_ms"),
                         "handoffs": _in_time(handoffs)},
            "pages": pages,
            "layers": shown[rests].layers,
            "actions": _actions(parts, shown, epoch),
            "replay": shown[0].replay,
            "server": _server(parts, shown),
            "tabs": [_tab(part, one, epoch, length, crossed.get(index, []))
                     for index, (part, one) in enumerate(zip(parts, shown))],
            "follow": _follow(con, parts, epoch, length),
            "verdict_tab": parts[rests].id}
    if named in {part.id for part in parts}:
        body["named_tab"] = named
    return body


def _seen(con, part, epoch, length):
    own = {"verdict": part.verdict, "agent_turns": part.turns, "evidence": part.evidence,
           "agent": visits.agent_of(part.verdict, part.detail)}
    return one_tab.seen(con, part.id, own, epoch, length, _at(tabs.end_of(part), epoch, length))


def _at(t, epoch, length):
    """A moment (epoch ms) on the session's clock: whole ms inside 0 … length."""
    return int(min(length, max(0, t - epoch)))


def _in_time(items, key="at_ms"):
    """In time order; of one moment, in the order given (the tabs' order)."""
    return sorted(items, key=lambda item: item[key])


def _verdict_tab(parts, shown, verdict):
    """The index of the tab the verdict rests on (see the module docstring)."""
    matching = [index for index, part in enumerate(parts) if part.verdict == verdict] or list(range(len(parts)))
    return max(matching, key=lambda index: (parts[index].evidence != one_tab.THIN, shown[index].percent or 0, -index))


def _acting(parts, verdict):
    """The indexes of the tabs whose runs tell who acted: a Script bot's only in a session of Script bots (a bot decides
    a session only when every tab is one, and one tab's story leaves its bot's runs out: session.seen)."""
    return {index for index, part in enumerate(parts) if part.verdict != one_tab.BOT or verdict == one_tab.BOT}


def _title(con, summary, parts, shown, rests, acting):
    """Who acted, in one line, over the acting tabs' turns in time order (session.title with the session's merged
    class: a session on thin evidence says why its tabs were); an agent acted when it acted in any tab. Within a tab its
    turns are the ones its own judge handed over (session.told, as a session of one tab tells them); from one tab to
    another every change is told. Each turn's agent is its tab's own (session.title's agents): a named agent is one
    agent in every tab, an unnamed one only within its tab."""
    merged = con.execute("SELECT verdict_class FROM visits WHERE id=?", (summary["id"],)).fetchone()[0]
    told = sorted((((turn["start"], turn["end"], turn["who"]), _agent_of(part))
                   for index, (part, one) in enumerate(zip(parts, shown)) if index in acting
                   for turn in one_tab.told(one.runs, one.judged)),
                  key=lambda item: item[0])  # by the turn alone: tabs' turns of one moment keep the tabs' order
    return one_tab.title(summary["verdict"], summary["agent_turns"], merged, summary["agent"],
                         [run for run, _ in told], summary["evidence"], why=shown[rests].why,
                         agent_acted=any(one.agent_acted for one in shown), agents=[agent for _, agent in told])


def _agent_of(part):
    """(name, identity) of a tab's agent: its name, or None and its tab for an agent no name fits."""
    name = visits.agent_of(part.verdict, part.detail)
    return name, name if name else part.tab


def _crossings(shown, epoch, length, acting):
    """{tab index: [Handoff]}: where the actor changes from one acting tab's run to a run of another (unsure runs
    skipped), on the tab the new actor acts in; a change within one tab is that tab's own judge's to mark."""
    merged = sorted((t_start, who, index) for index, one in enumerate(shown) if index in acting
                    for t_start, _, who in one.runs if who != UNSURE)
    found, current = {}, None
    for t_start, who, index in merged:
        if current is not None and who != current[0] and index != current[1]:
            found.setdefault(index, []).append({"at_ms": _at(t_start, epoch, length), "to": who})
        current = (who, index)
    return found


def _actions(parts, shown, epoch):
    """Every action of every tab, in time order, the first max_actions of them."""
    listed = [dict(action, tab=part.tab) for part, one in zip(parts, shown)
              for action in actions.listed(one.found, one.path_of, epoch)]
    return _in_time(listed)[:answers.numbers()["max_actions"]]


def _server(parts, shown):
    """The server half of every tab: its rows in time order, each with its tab's number, and the note over them all."""
    rows = _in_time([dict(row, tab=part.tab) for part, one in zip(parts, shown) for row in one.server["pages"]])
    return {"pages": rows, "network": next((one.server["network"] for one in shown if one.server["network"]), None),
            "note": server_half.note(len(rows), sum(one.page_views for one in shown))}


def _tab(part, one, epoch, length, crossed):
    return {"id": part.id, "tab": part.tab, "start_ms": _at(part.epoch, epoch, length),
            "end_ms": _at(tabs.end_of(part), epoch, length), "verdict": part.verdict, "evidence": part.evidence,
            "agent_turns": part.turns, "agent": visits.agent_of(part.verdict, part.detail),
            "certainty": visits.certainty_of(part.verdict, part.detail), "percent": one.percent,
            "summary": one.summary, "layers": one.layers, "segments": one.segments,
            "handoffs": _in_time(one.handoffs + crossed),
            "replay": {key: one.replay[key] for key in TAB_REPLAY}}


def _follow(con, parts, epoch, length):
    """[FollowStretch]: the segmenter's schedule over the tabs' activity, on the session's clock (see the module
    docstring); a stretch no tab's events cover stays with the tab before it (segmenter.schedule), the first tab when
    none came before."""
    events = []
    for part in parts:
        held = replay.windows(con, part.id)
        if held:  # the first and the last moment its replay holds: its first page, and its recording's end
            (_, first, _), (_, _, last) = held[0], held[-1]
            events += [Event(first, part.id, True), Event(last, part.id, False)]
        events += [Event(t, part.id, True) for t in _activity(con, part.id)]
    stretches = segmenter.schedule(segmenter.segments(events, epoch, epoch + length))
    return [{"tab": tab or parts[0].id, "start_ms": _at(start, epoch, length), "end_ms": _at(end, epoch, length)}
            for tab, start, end in stretches]


def _activity(con, session_id):
    """activity.times() of one tab session: its page starts and its visitor's input (rrweb's for a 0.3.x recording)."""
    raw = [json.loads(text) for _, _, text in streams.read_events(con, session_id, [RAW])]
    rrweb = [] if raw else [json.loads(text) for _, _, text in streams.read_events(con, session_id, [STREAM])]
    return activity.times(raw, rrweb, activity.page_starts(con, session_id))
