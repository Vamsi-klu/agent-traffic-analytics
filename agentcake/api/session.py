"""GET /api/session/<id>: one session as its page shows it; GET …/replay?chunk=<n>[&tab=<id>]: replay.py.

Opening a session judges its tabs first when a verdict is stale or an older judge's (judging.on_open), as opening a
replay always did. The id is a session's or one of its tab sessions' (tabs.resolve: the address of a tab session from
before sessions spanned tabs opens the session it is in now); a session none of whose tabs counts (visits.py: a
self-check, another site's upload, a prefetch) is a 404, as is an id of none. A session of several tabs adds what
session_tabs.py says; a session of one tab is this SessionDetail, as it always was:
    session    the session as the lists show it (visits.page)
    title      who acted, in one line (api.en.json "title"): "A human, then Claude in Chrome, then the human again"
               from a Human + agent session's runs (unsure runs skipped), "A human, with Claude in Chrome in the
               browser" for one whose agent took no part (no action of its own, no hand-off to it), else "A human",
               the agent's name ("An unnamed agent" when no name fits), or for a Human session on thin evidence why it
               is thin (too few actions, a phone or tablet whatever its number of actions, or evidence that can't
               tell)
    percent    how sure cake is of the verdict, 1 to 99 (detect/confidence.py, calibrated: Human that a human acted,
               a Human session on thin evidence too, Agent that an agent did, Bot by how its name was checked); None
               for a session judged before verdicts kept it, and for a phone or tablet shown as a Human, on thin
               evidence or not (the behaviour model does not run there, so no layer measured how sure: the owner's
               rule of 2026-11-22; an Agent or a Bot on one keeps its percent). It is the page's one word on how sure
               the verdict is: the summary says no other (one conclusion, one measure, as a bot score is one number)
    summary    what happened, who and why, in the page's words (summary()): who acted when, turn by turn (the
               timeline's runs, on its clock: a hand-off at the moment the timeline marks it), else the reason that
               decided the verdict (the first in its tone: data/api.json "summary"); then the layers that point to the
               verdict, each with its own percent as the layer shows it. A session without reasons (judged before 0.4.0) gets its class's
               rule from judging.en.json
    timeline   who acted when over the whole recording, in ms from the session's first recorded event (epoch_ms, so
               the replay's events line up; tabs.clock): the stored segments, and for a Human + agent session
               the hand-offs the judge marked (detect/handoff.py: the new actor's first action), which judging.py
               keeps with the verdict, so the marks, the title, the summary and the reasons name the same moments; a
               verdict kept before that has them from the stored runs, as detect/timeline.py marked them; its length
               reaches the last action, the last replay event or the last segment, whichever is later: the player's
               length, which the session's own duration_ms (the lists') is too
    pages      pages.py: the pages in the order they opened (entry page first, exit page last), on the timeline's clock;
               the session's own pages is how many there are, and its share each actor's share of the actions Every
               action lists (actions.share: the same actions Pages visited counts), so the page counts actions once
    layers     reasons.py, each reason's moments on the timeline's clock;  actions: actions.py;  replay: replay.py;
               server: server_half.py
"""
import json
from collections import namedtuple
from http import HTTPStatus
from urllib.parse import unquote

from agentcake import judging, timezone
from agentcake.api import actions, answers, pages, periods, reasons, replay, server_half, tabs, visits
from agentcake.config import load_cfg
from agentcake.detect import markers, verdict_text
from agentcake.detect import timeline as behavior_timeline

PREFIX = "/api/session/"
REPLAY_SUFFIX = "/replay"
HUMAN_AGENT, UNSURE, HUMAN, BOT, THIN = "human_agent", "unsure", "human", "bot", "thin"
AGENT = "agent"
TOO_LITTLE, TOUCH = "too_little_data", "touch"  # verdict.py's class, and behavior.run()'s reason for a phone or tablet


@answers.view
def view(request):
    rest = request.path[len(PREFIX):]
    if rest.endswith(REPLAY_SUFFIX):
        return replay.chunk(request, unquote(rest[:-len(REPLAY_SUFFIX)]))
    return detail(unquote(rest))


def detail(address_id):
    """The session an address names (tabs.resolve: a session's id, or one of its tab sessions' ids from before a
    session spanned tabs), each of its tabs judged first when its verdict is stale."""
    found = _named(address_id)
    if found is None:
        return answers.error(HTTPStatus.NOT_FOUND, "no_session")
    visit_id, named, listed = found
    for part in listed:
        judging.on_open(part.id)
    con = visits.connect()
    try:
        with visits.snapshot(con):
            rows, _ = visits.page(con, visits.Scope().where("v.id = ?", visit_id), 1, periods.now_ms(),
                                  timezone.chosen(load_cfg()))
            listed = tabs.parts(con, [visit_id]).get(visit_id) if rows else None  # again: judging may have changed it
            if not listed:
                return answers.error(HTTPStatus.NOT_FOUND, "no_session")
            if len(listed) > 1:
                from agentcake.api import session_tabs  # it reads this module's seen() and title()
                body = session_tabs.detail(con, rows[0], listed, named)
            else:
                body = _detail(con, listed[0], rows[0])
    finally:
        con.close()
    return answers.ok(body)


def _named(address_id):
    """(the session's id, the tab session the address named or None, its tabs) of an address, or None."""
    con = visits.connect()
    try:
        found = tabs.resolve(con, address_id)
        return None if found is None else (*found, tabs.parts(con, [found[0]]).get(found[0], []))
    finally:
        con.close()


def _detail(con, part, summary):
    """A session of one tab, as its page always showed it."""
    epoch, length = tabs.clock([part])
    one = seen(con, part.id, summary, epoch, length, length)
    return {"session": dict(summary, duration_ms=length, pages=len(one.pages), share=actions.share(one.found)),
            "title": one.title, "summary": one.summary, "percent": one.percent,
            "timeline": {"duration_ms": length, "segments": one.segments, "handoffs": one.handoffs},
            "pages": one.pages, "layers": one.layers, "actions": actions.listed(one.found, one.path_of, epoch),
            "replay": one.replay, "server": one.server}


# What the page shows of one tab session, on a session's clock (see seen()); judged: its judge's own hand-offs (epoch
# ms; None for a verdict kept before the judge kept them), as told() reads them.
Seen = namedtuple("Seen", "title summary percent runs segments handoffs pages layers found path_of replay server why "
                          "page_views agent_acted judged")


def seen(con, session_id, own, epoch, length, end):
    """What the page shows of one tab session on the clock of the session it is in (epoch, length): own is its own
    {"verdict", "agent_turns", "evidence", "agent"} (a session of one tab: the session's), end where its last page
    ends on that clock (its own end in a session of several tabs)."""
    (verdict_class, reasons_json, layers_json, detail_json, net, freed, dropped) = con.execute(
        "SELECT verdict_class, reasons, layers, verdict_detail, net, replay_freed_ms, events_dropped FROM sessions "
        "WHERE id=?", (session_id,)).fetchone()
    runs = con.execute("SELECT t_start, t_end, actor FROM segments WHERE session_id=? ORDER BY t_start",
                       (session_id,)).fetchall()
    verdict, turns, evidence = own["verdict"], own["agent_turns"], own["evidence"]
    kept = reasons.stored(reasons_json)
    detail = json.loads(detail_json) if detail_json else {}
    judged = detail.get("handoffs")  # the judge's own hand-offs, kept with its verdict; None: a verdict kept before
    handoffs = judged if judged is not None else behavior_timeline.handoffs(
        [{"who": who, "start": t_start, "end": t_end} for t_start, t_end, who in runs])
    whole = None if turns == HUMAN_AGENT else verdict  # a Human + agent session's input outside every segment is unsure
    views = pages.views(con, session_id)
    found = actions.recorded(con, session_id, runs, whole, views)
    agent_acted = _agent_took_part(found, judged)
    visit = pages.Visit(views, found, epoch)
    layers = reasons.layers(layers_json, reasons_json, epoch, turns == HUMAN_AGENT, verdict)
    story = Story(epoch, runs if verdict != BOT else [], own["agent"], layers, judged, found)
    why = _behavior_why(layers_json)
    page_views = visits.page_count({view: history for view, history in views.items() if view is not None})
    return Seen(
        title=title(verdict, turns, verdict_class, own["agent"], runs, evidence, judged, why=why,
                    agent_acted=agent_acted),
        summary=verdict_summary(verdict, turns or evidence, detail.get("judging"), kept, story),
        percent=None if (verdict == HUMAN and why == TOUCH) else detail.get("percent"),
        runs=runs, segments=visits.relative(runs, epoch, length),
        handoffs=[{"at_ms": int(min(length, max(0, handoff["t"] - epoch))), "to": handoff["to"]}
                  for handoff in handoffs] if turns == HUMAN_AGENT else [],
        pages=visit.listed(end), layers=layers, found=found, path_of=visit.path_of,
        replay=replay.info(con, session_id, epoch, freed, dropped, load_cfg()),
        server=server_half.table(con, session_id, net, epoch, page_views), why=why, page_views=page_views,
        agent_acted=agent_acted, judged=judged)


def title(verdict, turns, verdict_class, agent, runs, evidence=None, handoffs=None, why=None, agent_acted=True,
          agents=None):
    """Who acted, in one line; turns: an Agent session's split (visits.TURNS), agent: its name or None (Unnamed),
    evidence: thin for a Human session cake could not tell, whose title says why; handoffs: the judge's own, when it
    kept them (told()); why: why the behavior layer judged nothing (_behavior_why()), which tells a phone or tablet,
    whatever its number of actions, from too few actions; agent_acted: whether the agent took part as the page tells
    it (_agent_took_part()). A Human + agent session whose agent took no part (a name, a signature or a trace says
    whose browser it is, and a human acted in it) has the agent in the browser. agents: who each run's agent is,
    parallel to runs, (name or None, identity), when the runs come from tabs whose agents may differ (a session of
    several tabs): each agent's turn is told by its own name, an unnamed agent's as an unnamed agent, never by another
    agent's, and an Agent session that more than one agent acted in is told turn by turn too; without it every agent
    run is the agent's."""
    words = answers.words()["title"]
    told_turns = told(runs, handoffs, agents)
    several = len({turn["agent"] for turn in told_turns if turn["who"] == AGENT}) > 1
    if turns == HUMAN_AGENT or (turns and several):
        if turns == HUMAN_AGENT and not agent_acted:
            return words["with_agent"].format(agent=agent) if agent else words["with_unnamed"]
        if told_turns:
            return _turns([(turn["who"], turn["agent"]) for turn in told_turns], agent, words)
    if evidence:
        if verdict_class != TOO_LITTLE:
            return words["unsure"]
        return words[TOUCH] if why == TOUCH else words[TOO_LITTLE]
    if verdict == HUMAN:
        return words["human"]
    if agent:
        return words["agent"].format(agent=agent)
    return words["unnamed"] if turns else words["unsure"]


def _behavior_why(layers_json):
    """Why the verdict's behavior layer judged nothing (verdict.py's layers: "touch", "few_actions", ...), None when it
    judged or the verdict kept no layers."""
    kept = json.loads(layers_json) if layers_json else {}
    return (kept.get("behavior") or {}).get("why")


def _turns(order, agent, words):
    """The title of turns in order, each (actor, its agent: (name, identity) or None for the session's own agent):
    an agent is told by its own name, and "again" only when that very agent acted before."""
    said, seen = None, set()
    for who, of in order:
        name, identity = of if of is not None else (agent, who)
        if who == HUMAN:
            part = words["human"] if said is None else words["human_again" if HUMAN in seen else "human_later"]
            identity = HUMAN
        elif name:
            part = words["agent_again" if identity in seen else "agent"].format(agent=name)
        else:
            part = words["unnamed_again" if identity in seen else ("unnamed" if said is None else "unnamed_later")]
        seen.add(identity)
        said = part if said is None else words["then"].format(before=said, after=part)
    return said


def told(runs, handoffs=None, agents=None):
    """The turns the title and the summary tell, [{"who", "start", "end", "agent"}], from the stored runs (t_start,
    t_end, actor): unsure runs skipped, one actor's runs in a row joined (an agent's only with the same agent's: agents,
    parallel to runs, says whose each run is, as title() takes it; None: one agent's). With the judge's own hand-offs
    (handoffs, which it keeps with its verdict), a turn is told only where a hand-off began it, from that hand-off's
    moment, the one the timeline marks and the reasons name (the new actor's first action, detect/handoff.py); a turn
    no hand-off began (its actor only moved the pointer) is left out. Without them (a verdict kept before) every turn is
    told from its run's start, as the timeline then marks it."""
    turns = []
    for index, (t_start, t_end, who) in enumerate(runs):
        if who == UNSURE:
            continue
        of = agents[index] if agents and who == AGENT else None
        if turns and turns[-1]["who"] == who and turns[-1]["agent"] == of:
            turns[-1]["end"] = t_end
        else:
            turns.append({"who": who, "start": t_start, "end": t_end, "agent": of})
    if handoffs is None or not turns:
        return turns
    out = [turns[0]]
    for turn in turns[1:]:
        if turn["who"] == out[-1]["who"] and turn["agent"] == out[-1]["agent"]:
            out[-1]["end"] = turn["end"]
            continue
        began = next((h["t"] for h in handoffs
                      if h["to"] == turn["who"] and out[-1]["start"] < h["t"] <= turn["end"]), None)
        if began is not None:
            out.append({"who": turn["who"], "start": began, "end": turn["end"], "agent": turn["agent"]})
    return out


# What the summary tells beside the verdict: the recording's start (epoch ms), the stored runs (t_start, t_end, actor),
# the agent's name (None: unnamed), the layers as the page shows them (reasons.layers), the judge's own hand-offs
# (None: a verdict kept before it kept them) and the actions All actions lists (actions.recorded; None: not given).
Story = namedtuple("Story", "epoch runs agent layers handoffs acts", defaults=(None, None))


def verdict_summary(verdict, group, judging_class, kept, story=None):
    """What happened, who and why (see the module docstring); group: an Agent session's split, or thin for a Human
    session on thin evidence, which picks the reason and the rule before the verdict does. Without a story (or runs
    to tell), the deciding reason stands for who acted."""
    said = _turns_told(verdict, story, group) if story and group != THIN else None
    if said is None:
        chosen = _deciding(verdict, kept)
        if chosen is None:
            rules = answers.numbers()["summary"]
            return verdict_text.class_rule(judging_class or rules["classes"][group or verdict])
        said = verdict_text.words(chosen, story.epoch if story else None)[0]
    why = _pointing(verdict, story.layers) if story else None
    return f"{said} {why}" if why else said


def _deciding(verdict, kept):
    """The reason that decided the verdict: the first in the verdict's tone, else the first of the fallback layer
    (data/api.json "summary"); None without one."""
    rules = answers.numbers()["summary"]
    tone = rules["tones"].get(verdict)
    return (next((r for r in kept if tone and r.get("tone") == tone), None)
            or next((r for r in kept if r.get("layer") == rules["fallback_layer"]), None))


def _turns_told(verdict, story, group=None):
    """Who acted when, turn by turn, on the timeline's clock: the first turn from its actor's first action to its last
    (_acted(): the times All actions lists), then each hand-off at the moment the timeline marks and the reasons name,
    the new actor's first action (told()): one time for each on the page; for a Human + agent session (group) whose
    agent took no part, the human's turns as one, as its title says. None when no human or agent run is there to
    tell."""
    turns = told(story.runs, story.handoffs)
    if group == HUMAN_AGENT and story.acts is not None and not _agent_took_part(story.acts, story.handoffs):
        humans = [turn for turn in turns if turn["who"] == HUMAN]
        turns = [dict(humans[0], end=humans[-1]["end"])] if humans else []
    if not turns or (verdict == HUMAN and any(turn["who"] != HUMAN for turn in turns)):
        return None
    turns = [_acted(turns, story.acts)] + turns[1:]
    words, seen = answers.words()["summary"], set()
    at = lambda t: markers.clock(max(0, t - story.epoch))  # noqa: E731  (a moment as the player writes it)
    said = []
    for turn in turns:
        who = _who(turn["who"], story.agent, turn["who"] in seen, words["who"])
        if not said:
            said.append(words["acted"].format(who=who, start=at(turn["start"]), end=at(turn["end"])))
        else:
            said.append(words["took_over_again" if turn["who"] in seen else "took_over"].format(who=who,
                                                                                               at=at(turn["start"])))
        seen.add(turn["who"])
    return " ".join(said)


def _acted(turns, acts):
    """The first turn from its actor's first action to its last before the next hand-off (acts: actions.recorded's, in
    time order): the times All actions gives that actor, every action when a whole-session verdict gave it them all,
    inside its runs or not. Without an action there, the run's own times. A later turn is told only by its start, the
    hand-off's moment, which told() gives."""
    first = turns[0]
    until = turns[1]["start"] if len(turns) > 1 else float("inf")
    times = [act.t for act in acts or () if act.who == first["who"] and act.t < until]
    return dict(first, start=times[0], end=times[-1]) if times else first


def _agent_took_part(acts, handoffs):
    """Whether the agent took part as the page tells it: one of the actions All actions lists (actions.recorded's,
    pages opened aside) is its, or the judge marked a hand-off to it (handoffs: the judge's own, None for a verdict
    kept before)."""
    return (any(act.who == AGENT and act.kind != actions.OPEN for act in acts)
            or any(handoff["to"] == AGENT for handoff in handoffs or ()))


def _who(actor, agent, again, words):
    if actor == HUMAN:
        return words["human_again" if again else "human"]
    if agent:
        return words["agent"].format(agent=agent)
    return words["unnamed_again" if again else "unnamed"]


def _pointing(verdict, layers):
    """The layers whose conclusion is the verdict's, each with the percent the layer shows (how sure it is of that
    conclusion); None when none does."""
    agreeing = answers.numbers()["summary"]["supports"].get(verdict) or ()
    words, names = answers.words()["summary"], verdict_text.judging()["layers"]
    leaning = [layer for layer in layers if layer.get("state") in agreeing and layer.get("percent") is not None]
    found = [words["supports" if n == 0 else "supports_too"].format(layer=names[layer["layer"]], percent=layer["percent"])
             for n, layer in enumerate(leaning)]
    if not found:
        return None
    listed = found[0] if len(found) == 1 else words["list"].format(items=", ".join(found[:-1]), last=found[-1])
    return words["pointing"].format(layers=listed)
