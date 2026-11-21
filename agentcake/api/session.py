"""GET /api/session/<id>: one session as its page shows it; GET …/replay?chunk=<n>: replay.py.

Opening a session judges it first when its verdict is stale or an older judge's (judging.on_open), as opening a
replay always did. A session that does not exist or does not count (visits.py: a self-check, another site's upload, a
prefetch) is a 404. SessionDetail:
    session    the session as the lists show it (visits.page)
    title      who acted, in one line (api.en.json "title"): "A human, then Claude in Chrome, then the human again"
               from a Human + agent session's runs (unsure runs skipped), else "A human", the agent's name ("An
               unnamed agent" when no name fits), or for a Human session on thin evidence why it is thin (too few
               actions, a phone or tablet whatever its number of actions, or evidence that can't tell)
    percent    how sure cake is of the verdict, 1 to 99 (detect/confidence.py, calibrated: Human that a human acted,
               a Human session on thin evidence too, Agent that an agent did, Bot by how its name was checked); None
               for a session judged before verdicts kept it. It is the page's one word on how sure the verdict is: the
               summary says no other (one conclusion, one measure, as a bot score is one number)
    summary    what happened, who and why, in the page's words (summary()): who acted when, turn by turn (the
               timeline's runs, on its clock: a hand-off at the moment the timeline marks it), else the reason that
               decided the verdict (the first in its tone: data/api.json "summary"); then the layers that point to the
               verdict, each with its own percent as the layer shows it. A session without reasons (judged before 0.4.0) gets its class's
               rule from judging.en.json
    timeline   who acted when over the whole recording, in ms from the session's first recorded event (epoch_ms, so
               the replay's events line up; visits.recording): the stored segments, and for a Human + agent session
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
from agentcake.api import actions, answers, pages, periods, reasons, replay, server_half, visits
from agentcake.config import load_cfg
from agentcake.detect import markers, verdict_text
from agentcake.detect import timeline as behavior_timeline

PREFIX = "/api/session/"
REPLAY_SUFFIX = "/replay"
HUMAN_AGENT, UNSURE, HUMAN, BOT, THIN = "human_agent", "unsure", "human", "bot", "thin"
TOO_LITTLE, TOUCH = "too_little_data", "touch"  # verdict.py's class, and detect/model.py's reason for a phone or tablet


@answers.view
def view(request):
    rest = request.path[len(PREFIX):]
    if rest.endswith(REPLAY_SUFFIX):
        return replay.chunk(request, unquote(rest[:-len(REPLAY_SUFFIX)]))
    return detail(unquote(rest))


def detail(session_id):
    judging.on_open(session_id)
    con = visits.connect()
    try:
        found, _ = visits.page(con, visits.Scope().where("s.id = ?", session_id), 1, periods.now_ms(),
                               timezone.chosen(load_cfg()))
        if not found:
            return answers.error(HTTPStatus.NOT_FOUND, "no_session")
        body = _detail(con, session_id, found[0])
    finally:
        con.close()
    return answers.ok(body)


def _detail(con, session_id, summary):
    (verdict_class, reasons_json, layers_json, detail_json, net, freed, dropped) = con.execute(
        "SELECT verdict_class, reasons, layers, verdict_detail, net, replay_freed_ms, events_dropped FROM sessions "
        "WHERE id=?", (session_id,)).fetchone()
    epoch, length = visits.recording(con, session_id)
    runs = con.execute("SELECT t_start, t_end, actor FROM segments WHERE session_id=? ORDER BY t_start",
                       (session_id,)).fetchall()
    verdict, turns, evidence = summary["verdict"], summary["agent_turns"], summary["evidence"]
    kept = reasons.stored(reasons_json)
    detail = json.loads(detail_json) if detail_json else {}
    judged = detail.get("handoffs")  # the judge's own hand-offs, kept with its verdict; None: a verdict kept before
    handoffs = judged if judged is not None else behavior_timeline.handoffs(
        [{"who": who, "start": t_start, "end": t_end} for t_start, t_end, who in runs])
    whole = None if turns == HUMAN_AGENT else verdict  # a Human + agent session's input outside every segment is unsure
    views = pages.views(con, session_id)
    found = actions.recorded(con, session_id, runs, whole, views)
    visit = pages.Visit(views, found, epoch)
    listed = visit.listed(length)
    layers = reasons.layers(layers_json, reasons_json, epoch, turns == HUMAN_AGENT, verdict)
    story = Story(epoch, runs if verdict != BOT else [], summary["agent"], layers, judged, found)
    return {"session": dict(summary, duration_ms=length, pages=len(listed), share=actions.share(found)),
            "title": title(verdict, turns, verdict_class, summary["agent"], runs, evidence, judged,
                           why=_behavior_why(layers_json)),
            "summary": verdict_summary(verdict, turns or evidence, detail.get("judging"), kept, story),
            "percent": detail.get("percent"),
            "timeline": {"duration_ms": length, "segments": visits.relative(runs, epoch, length),
                         "handoffs": [{"at_ms": int(min(length, max(0, handoff["t"] - epoch))), "to": handoff["to"]}
                                      for handoff in handoffs] if turns == HUMAN_AGENT else []},
            "pages": listed,
            "layers": layers,
            "actions": actions.listed(found, visit.path_of, epoch),
            "replay": replay.info(con, session_id, epoch, freed, dropped, load_cfg()),
            "server": server_half.table(con, session_id, net, epoch, summary["pages"])}


def title(verdict, turns, verdict_class, agent, runs, evidence=None, handoffs=None, why=None):
    """Who acted, in one line; turns: an Agent session's split (visits.TURNS), agent: its name or None (Unnamed),
    evidence: thin for a Human session cake could not tell, whose title says why; handoffs: the judge's own, when it
    kept them (told()); why: why the behavior layer judged nothing (_behavior_why()), which tells a phone or tablet,
    whatever its number of actions, from too few actions."""
    words = answers.words()["title"]
    if turns == HUMAN_AGENT:
        order = [turn["who"] for turn in told(runs, handoffs)]
        if order:
            return _turns(order, agent, words)
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
    said, seen = None, set()
    for who in order:
        if who == HUMAN:
            part = words["human"] if said is None else words["human_again" if HUMAN in seen else "human_later"]
        elif agent:
            part = words["agent_again" if who in seen else "agent"].format(agent=agent)
        else:
            part = words["unnamed_again" if who in seen else ("unnamed" if said is None else "unnamed_later")]
        seen.add(who)
        said = part if said is None else words["then"].format(before=said, after=part)
    return said


def told(runs, handoffs=None):
    """The turns the title and the summary tell, [{"who", "start", "end"}], from the stored runs (t_start, t_end,
    actor): unsure runs skipped, one actor's runs in a row joined. With the judge's own hand-offs (handoffs, which it
    keeps with its verdict), a turn is told only where a hand-off began it, from that hand-off's moment, the one the
    timeline marks and the reasons name (the new actor's first action, detect/handoff.py); a turn no hand-off began
    (its actor only moved the pointer) is left out. Without them (a verdict kept before) every turn is told from its
    run's start, as the timeline then marks it."""
    turns = []
    for t_start, t_end, who in runs:
        if who == UNSURE:
            continue
        if turns and turns[-1]["who"] == who:
            turns[-1]["end"] = t_end
        else:
            turns.append({"who": who, "start": t_start, "end": t_end})
    if handoffs is None or not turns:
        return turns
    out = [turns[0]]
    for turn in turns[1:]:
        if turn["who"] == out[-1]["who"]:
            out[-1]["end"] = turn["end"]
            continue
        began = next((h["t"] for h in handoffs
                      if h["to"] == turn["who"] and out[-1]["start"] < h["t"] <= turn["end"]), None)
        if began is not None:
            out.append({"who": turn["who"], "start": began, "end": turn["end"]})
    return out


# What the summary tells beside the verdict: the recording's start (epoch ms), the stored runs (t_start, t_end, actor),
# the agent's name (None: unnamed), the layers as the page shows them (reasons.layers), the judge's own hand-offs
# (None: a verdict kept before it kept them) and the actions Every action lists (actions.recorded; None: not given).
Story = namedtuple("Story", "epoch runs agent layers handoffs acts", defaults=(None, None))


def verdict_summary(verdict, group, judging_class, kept, story=None):
    """What happened, who and why (see the module docstring); group: an Agent session's split, or thin for a Human
    session on thin evidence, which picks the reason and the rule before the verdict does. Without a story (or runs
    to tell), the deciding reason stands for who acted."""
    said = _turns_told(verdict, story) if story and group != THIN else None
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


def _turns_told(verdict, story):
    """Who acted when, turn by turn, on the timeline's clock: the first turn from its actor's first action to its last
    (_acted(): the times Every action lists), then each hand-off at the moment the timeline marks and the reasons name,
    the new actor's first action (told()): one time for each on the page. None when no human or agent run is there to
    tell."""
    turns = told(story.runs, story.handoffs)
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
    time order): the times Every action gives that actor, every action when a whole-session verdict gave it them all,
    inside its runs or not. Without an action there, the run's own times. A later turn is told only by its start, the
    hand-off's moment, which told() gives."""
    first = turns[0]
    until = turns[1]["start"] if len(turns) > 1 else float("inf")
    times = [act.t for act in acts or () if act.who == first["who"] and act.t < until]
    return dict(first, start=times[0], end=times[-1]) if times else first


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
