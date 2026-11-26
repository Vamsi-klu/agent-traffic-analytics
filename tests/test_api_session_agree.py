"""GET /api/session/<id>: a Human + agent session's badge, title, timeline and Share of actions say the same
(agentcake/api/session.py with actions.py, on sessions uploaded, judged and opened as the page opens them).

    python3 -I -m unittest discover -s tests -p test_api_session_agree.py -v

An agent that acted takes a turn on the timeline and in the title beside the human, and a share of the actions; one
that took no part (its name, signature or trace says whose browser it is) is in the browser, as the title says, at 0%.
A person scrolling and hovering the browser beside their editor without activating it is a Human, and so is a session
whose agent part, as the model left it, holds no click or input of its own: the page once said Human + agent at 86%
with the title "A human" and the agent at 0% of the actions.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import beside_editor  # noqa: E402  (made up by rule: no recording)
import synthetic_sessions  # noqa: E402  (made up by rule: no recording)
import verdict_cases  # noqa: E402
from test_api_session import OpenedCase  # noqa: E402
from test_judging import T0, clicks  # noqa: E402
from agentcake.api import answers, session as session_api  # noqa: E402
from agentcake.detect import model  # noqa: E402

AGENT_ONLY, HUMAN_AGENT = "agent_only", "human_agent"  # data/api.json's agent_turns


def disagreements(body):
    """What a Human + agent session's page says against its badge (one concept, one value on a page): an agent that
    acted needs a turn on the timeline, in the title beside the human, and a share of the actions; one that took no
    action (its name, signature or trace says whose browser it is) is in the browser, as the title says, at 0%."""
    session, found = body["session"], []
    if (session["verdict"], session["agent_turns"]) != ("agent", "human_agent"):
        return found
    words = answers.words()["title"]
    if session["share"]["agent"] == 0:
        said = words["with_agent"].format(agent=session["agent"]) if session.get("agent") else words["with_unnamed"]
        return [] if body["title"] == said else [f"the agent took no action but the title is {body['title']!r}"]
    agent_word = session.get("agent") or words["unnamed"].split()[-1]
    if not any(segment["who"] == "agent" for segment in body["timeline"]["segments"]):
        found.append("no agent turn on the timeline")
    if words["human"].split()[-1] not in body["title"].lower() or agent_word not in body["title"]:
        found.append(f"the title names one side only: {body['title']!r}")
    if not session["share"]["agent"] > 0:
        found.append(f"the agent has no share of the actions: {session['share']}")
    return found


class HumanAndAgentAgree(OpenedCase):
    """A Human + agent session's badge, title, timeline and Share of actions say the same."""

    def test_a_human_then_an_agent_agree_everywhere(self):
        agent = synthetic_sessions.agent_raw(T0 + 40 * 1000)
        body = self.opened(clicks(8, T0) + [e for e in agent if e["ty"] != "visibility"])
        self.assertEqual((body["session"]["verdict"], body["session"]["agent_turns"]), ("agent", "human_agent"))
        self.assertEqual(disagreements(body), [])

    def test_an_agent_part_with_no_click_or_input_never_shows_as_human_and_agent(self):
        """The page of 11/24 as the model left it: it judged an agent, and on its timeline a human's eight clicks were
        followed by a stretch of pointer movement it gave the agent, with no click, key, typing or scroll in it. Shown
        as Human + agent, the title told only the human and the agent had 0% of the actions; it is a Human."""
        moves = [{"t": T0 + 9_000 + 40 * k, "ty": "mousemove", "cx": 300 + 5 * k, "cy": 200, "tr": 1, "hf": 0}
                 for k in range(60)]
        human = {"who": "human", "start": T0 - 300, "end": T0 + 7_000, "n": 8, "acts": 8, "p": 0.1}
        agent = {"who": "agent", "start": T0 + 9_000, "end": T0 + 11_360, "n": 1, "acts": 0, "p": 0.9}
        judged = verdict_cases.behavior("agent", human, agent)
        judged["timeline"]["handoffs"] = []  # the timeline's own: a run with no action of its own hands nothing over
        with mock.patch.object(model, "judge_session", return_value=judged):
            body = self.opened(clicks(8, T0) + moves)
        self.assertEqual(disagreements(body), [])
        self.assertEqual((body["session"]["verdict"], body["title"]), ("human", answers.words()["title"]["human"]))

    def test_a_human_in_a_named_agents_browser_has_it_in_the_browser_at_no_share(self):
        """A browser that names an agent (its User-Agent) and a human's clicks: Human + agent, the agent with no action
        of its own; the title says it was in the browser, the summary tells the human, and the agent's share is 0%."""
        body = self.opened(clicks(8, T0), ua=verdict_cases.MANUS)
        session = body["session"]
        self.assertEqual((session["verdict"], session["agent_turns"], session["share"]["agent"]),
                         ("agent", "human_agent", 0))
        self.assertEqual(body["title"], answers.words()["title"]["with_agent"].format(agent=session["agent"]))
        self.assertTrue(body["summary"].startswith("A human was active from "), body["summary"])
        self.assertEqual(disagreements(body), [])

    def test_only_a_human_and_agent_session_whose_agent_took_no_part_is_told_as_the_humans_turn(self):
        """The human's turn alone is how the page tells a human with the agent in the browser (its title says so);
        an Agent session whose agent's run holds no action All actions lists still tells that run, as before."""
        human, agent = (T0, T0 + 7_000, "human"), (T0 + 9_000, T0 + 15_000, "agent")
        for group, runs, told in ((AGENT_ONLY, [agent], "Manus was active from 0:09 to 0:15."),
                                  (HUMAN_AGENT, [human, agent], "A human was active from 0:00 to 0:07.")):
            with self.subTest(group=group):
                story = session_api.Story(T0, runs, "Manus", [], [], [])
                self.assertEqual(session_api.verdict_summary("agent", group, None, [], story), told)

    def test_a_person_scrolling_and_hovering_the_browser_beside_their_editor_is_a_human(self):
        """11/24: the badge said Human + agent at 86% while the title said "A human" and the agent had 0% of the
        actions: the browser's own moves after a scroll (WebKit), the window without focus, and an agent part with no
        click or input of its own."""
        body = self.opened(beside_editor.session(T0))
        self.assertEqual((body["session"]["verdict"], body["session"]["agent_turns"], body["title"]),
                         ("human", None, answers.words()["title"]["human"]))
        self.assertEqual(body["session"]["share"]["agent"], 0)
        self.assertEqual(disagreements(body), [])


if __name__ == "__main__":
    unittest.main()
