"""GET /api/session/<id> and …/replay?chunk=<n> (agentcake/api/session.py with reasons.py, actions.py,
replay.py and server_half.py) on the fixed test library.

    python3 -I -m unittest discover -s tests -p test_api_session.py -v      (from the AgentCake folder)

Every session of the library answers the contract, its four layers in order, its timeline and actions inside its
length. Its replay chunks, read one by one, give back the session's whole rrweb stream, each event once and in its
chunk's time. Unknown sessions, self-checks and other sites' uploads are 404, a chunk that is not a number 400, one
past the last 404. The server half lists the srv rows with their comparisons and reuses, and says why page views
have none. A Mixed session's title follows its turns; its summary tells who acted when on the timeline's clock and
which layers point to the verdict, with their own percents, never another word for how sure it is; its hand-off and
length are whole milliseconds, the hand-off where its agent segment starts. A Human session on limited evidence is
titled by why the behavior layer judged nothing: a phone or tablet, uploaded, judged and opened, is never titled as too
few actions however many taps it has; too few actions on a computer still is.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verdict_cases  # noqa: E402
from api_client import Client, contract_problems  # noqa: E402
from test_judging import CHROME, SID, T0, JudgingCase, clicks, visit_batch  # noqa: E402
from agentcake.api import actions as actions_api, answers, reasons as reasons_api, session as session_api  # noqa: E402
from agentcake.detect import verdict, verdict_text  # noqa: E402
from agentcake.wording import product  # noqa: E402

LAYERS = ["name", "verify", "environment", "behavior"]
ACTION_WORDS = ("Open ", "Click", "Type", "Scroll", "Tap")
PHONE = {"userAgent": verdict_cases.IPHONE, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5}


class Words(unittest.TestCase):
    def test_a_human_agent_sessions_title_follows_its_turns(self):
        runs = [(0, 1, "human"), (2, 3, "agent"), (4, 5, "unsure"), (6, 7, "human")]
        title = session_api.title
        self.assertEqual(title("agent", "human_agent", "mixed", "Claude in Chrome", runs),
                         "A human, then Claude in Chrome, then the human again")
        self.assertEqual(title("agent", "human_agent", "mixed", "Comet", [(0, 1, "agent"), (2, 3, "human")]),
                         "Comet, then a human")
        self.assertEqual(title("agent", "human_agent", "mixed", "Comet", runs[:2] * 2),
                         "A human, then Comet, then the human again, then Comet again")

    def test_with_the_judges_hand_offs_a_turn_no_hand_off_began_is_not_told(self):
        runs = [(0, 1, "agent"), (2, 3, "human"), (4, 5, "agent"), (6, 9, "human")]  # the first human only moved
        handoffs = [{"t": 7, "from": "agent", "to": "human", "after": 5}]
        self.assertEqual(session_api.title("agent", "human_agent", "mixed", "Comet", runs, handoffs=handoffs),
                         "Comet, then a human")
        self.assertEqual(session_api.title("agent", "human_agent", "mixed", "Comet", runs),
                         "Comet, then a human, then Comet again, then the human again", "a verdict kept before")

    def test_an_unnamed_agent_takes_turns_in_words(self):
        self.assertEqual(session_api.title("agent", "human_agent", "mixed", None,
                                           [(0, 1, "human"), (2, 3, "agent"), (4, 5, "human"), (6, 7, "agent")]),
                         "A human, then an unnamed agent, then the human again, then the agent again")
        self.assertEqual(session_api.title("agent", "human_agent", "mixed", None, [(0, 1, "agent")]),
                         "An unnamed agent")

    def test_other_titles(self):
        self.assertEqual(session_api.title("human", None, "human", None, []), "A human")
        self.assertEqual(session_api.title("agent", "agent_only", "agent", "Codex browser", []), "Codex browser")
        self.assertEqual(session_api.title("agent", "agent_only", "agent", None, []), "An unnamed agent")
        self.assertEqual(session_api.title("bot", None, "bot", "Googlebot", []), "Googlebot")
        self.assertEqual(session_api.title("human", None, "too_little_data", None, [], "thin"), "Not enough actions to classify")
        self.assertEqual(session_api.title("human", None, "not_sure", None, [], "thin"), "Actor not identified")
        self.assertEqual(session_api.title("human", None, None, None, [], "thin"), "Actor not identified")

    def test_a_human_session_on_limited_evidence_is_titled_by_why_the_behavior_layer_judged_nothing(self):
        """A phone or tablet is never judged by behavior, however many actions it has: its title says so and never
        that there were too few actions; too few actions still says that."""
        title = session_api.title
        self.assertEqual(title("human", None, "too_little_data", None, [], "thin", why="few_actions"),
                         "Not enough actions to classify")
        touch = title("human", None, "too_little_data", None, [], "thin", why="touch")
        self.assertNotEqual(touch, "Not enough actions to classify")
        self.assertEqual(touch, "Phone or tablet visit")

    def test_a_human_agent_summary_tells_who_acted_when_and_which_layers_point_to_it(self):
        epoch = 1_794_608_433_697
        runs = [(epoch + 8_627, epoch + 40_327, "agent"), (epoch + 41_000, epoch + 42_000, "unsure"),
                (epoch + 47_927, epoch + 84_573, "human")]
        layers = [{"layer": "name", "state": "no_hit", "percent": None}, {"layer": "verify", "state": "off", "percent": None},
                  {"layer": "environment", "state": "agent", "percent": 90},
                  {"layer": "behavior", "state": "human_agent", "percent": 99}]
        story = session_api.Story(epoch, runs, "Claude in Chrome", layers)
        self.assertEqual(session_api.verdict_summary("agent", "human_agent", "mixed", [], story),
                         "Claude in Chrome was active from 0:08 to 0:40. A human took over at 0:47. "
                         "Layers that reached the same classification: Environment (90% confidence) and Behavior (99% confidence).")

    def test_a_take_over_is_told_at_the_judges_hand_off_the_new_actors_first_action(self):
        epoch = 1_794_608_433_697
        runs = [(epoch + 8_627, epoch + 40_327, "agent"), (epoch + 47_927, epoch + 84_573, "human")]
        handoffs = [{"t": epoch + 49_100, "from": "agent", "to": "human", "after": epoch + 40_327}]
        story = session_api.Story(epoch, runs, "Claude in Chrome", [], handoffs)
        self.assertEqual(session_api.verdict_summary("agent", "human_agent", "mixed", [], story),
                         "Claude in Chrome was active from 0:08 to 0:40. A human took over at 0:49.")

    def test_active_is_the_actors_first_to_last_action_as_every_action_lists_them(self):
        """One time for the agent on the page: its first action to its last (the times Every action shows), not its
        run's edges, which its input can start sooner (a pointer move before the first click); the hand-off at the new
        actor's first action."""
        epoch = 1_794_608_433_697
        runs = [(epoch + 18_900, epoch + 58_799, "agent"), (epoch + 96_848, epoch + 210_035, "human")]
        handoffs = [{"t": epoch + 97_313, "from": "agent", "to": "human", "after": epoch + 58_799}]
        acts = [actions_api.Action(epoch + 19_432, "click", "#q", "pv", "agent"),
                actions_api.Action(epoch + 57_100, "click", "#add", "pv", "agent"),
                actions_api.Action(epoch + 97_313, "click", "body", "pv", "human")]
        story = session_api.Story(epoch, runs, "Claude in Chrome", [], handoffs, acts)
        self.assertEqual(session_api.verdict_summary("agent", "human_agent", "mixed", [], story),
                         "Claude in Chrome was active from 0:19 to 0:57. A human took over at 1:37.")

    def test_three_layers_are_listed_in_one_sentence(self):
        layers = [{"layer": name, "state": "agent", "percent": percent}
                  for name, percent in (("name", 90), ("environment", 99), ("behavior", 98))]
        story = session_api.Story(0, [(13_000, 63_000, "agent")], None, layers)
        self.assertEqual(session_api.verdict_summary("agent", "agent_only", "agent_automated", [], story),
                         "An unnamed agent was active from 0:13 to 1:03. Layers that reached the same "
                         "classification: Name (90% confidence), Environment (99% confidence) and Behavior (98% confidence).")

    def test_turns_name_who_comes_back_and_an_unnamed_agent(self):
        runs = [(0, 5_000, "human"), (6_000, 9_000, "agent"), (12_500, 20_000, "human"), (21_000, 30_000, "agent")]
        story = session_api.Story(0, runs, None, [])
        self.assertEqual(session_api.verdict_summary("agent", "human_agent", "mixed", [], story),
                         "A human was active from 0:00 to 0:05. An unnamed agent took over at 0:06. "
                         "The human took over again at 0:12. The agent took over again at 0:21.")
        self.assertEqual(session_api.verdict_summary("human", None, "human", [], session_api.Story(
            0, [(1_000, 64_000, "human")], None, [{"layer": "behavior", "state": "human", "percent": 97}])),
                         "A human was active from 0:01 to 1:04. Layers that reached the same classification: Behavior (97% confidence).")

    def test_without_turns_to_tell_the_deciding_reason_stands_and_no_confidence_word(self):
        reasons = [{"id": "name.ua", "layer": "name", "tone": "agent", "text": "The User-Agent declares X."}]
        bot = session_api.Story(0, [], "Googlebot", [{"layer": "name", "state": "bot", "percent": 60},
                                                     {"layer": "environment", "state": "agent", "percent": 99}])
        self.assertEqual(session_api.verdict_summary("bot", None, "bot", reasons, bot),
                         "The User-Agent declares X. Layers that reached the same classification: Name (60% confidence).")
        self.assertEqual(session_api.verdict_summary("agent", "agent_only", "agent_ai", reasons),
                         "The User-Agent declares X.")
        self.assertIn("behavior model", session_api.verdict_summary("human", None, None, []))
        for said in (session_api.verdict_summary("agent", "agent_only", "agent_ai", reasons, bot),
                     session_api.verdict_summary("bot", None, "bot", reasons, bot)):
            self.assertNotIn("Confidence", said)

    def test_a_session_judged_before_its_reasons_were_kept_gets_its_classs_rule(self):
        judged = verdict_text.judging()["classes"]
        name = product()["name"]
        for verdict, turns, rule in (("agent", "human_agent", "mixed"), ("agent", "agent_only", "agent_ai"),
                                     ("human", "thin", "not_sure"), ("bot", None, "bot"), ("human", None, "human")):
            said = session_api.verdict_summary(verdict, turns, None, [])
            self.assertEqual(said, judged[rule]["how"].replace("{name}", name), verdict)
            self.assertNotIn("{", said, "a placeholder never reaches the page")

    def test_reasons_are_worded_as_they_are_shown(self):
        """A reason with facts reads in today's words whatever text it was kept with; one without keeps its text."""
        kept = dict(verdict_text.reason("behavior.too-little-data", "page", 2, n=2, min=3), text="Old words.")
        handoff = {"id": "behavior.handoff", "layer": "behavior", "tone": "none", "text": "The agent took over."}
        today = verdict_text.reason("behavior.too-little-data", "page", 2, n=2, min=3)["text"]
        self.assertEqual(session_api.verdict_summary("human", "thin", "too_little_data", [kept]), today)
        shown = {layer["layer"]: layer["reasons"] for layer in reasons_api.layers("{}", json.dumps([kept, handoff]))}
        self.assertEqual([(r["text"], r["detail"]) for r in shown["behavior"]],
                         [(today, kept["detail"]), ("The agent took over.", None)])


class Layers(unittest.TestCase):
    """Each layer shows one conclusion and only what fits it."""

    def layers(self, layers, reasons, turns=False, verdict="agent"):
        shown = reasons_api.layers(json.dumps(layers), json.dumps(reasons), None, turns, verdict)
        return {layer["layer"]: layer for layer in shown}

    def test_a_layer_less_than_half_sure_reads_unknown_and_says_why_first(self):
        said = self.layers({"behavior": {"state": "human", "leans": "human", "percent": 45}},
                           [verdict_text.reason("behavior.human", "page", "human", human_pct=60)], verdict="human")
        behavior = said["behavior"]
        self.assertEqual((behavior["state"], behavior["percent"]), ("unknown", None))
        self.assertEqual(behavior["reasons"][0]["text"], answers.words()["layer_notes"]["both_ways"])

    def test_a_bots_environment_that_found_an_agent_says_why_it_is_still_a_bot(self):
        said = self.layers({"environment": {"state": "agent", "leans": "agent", "percent": 99}}, [], verdict="bot")
        self.assertEqual([r["text"] for r in said["environment"]["reasons"]],
                         [answers.words()["layer_notes"]["bot_environment"]])

    def test_the_behavior_layer_follows_the_timeline_both_ways(self):
        agent = verdict_text.reason("behavior.agent", "page", ["rules"], basis=["rules"], kinds=["approach"])
        took_turns = self.layers({"behavior": {"state": "agent", "leans": "agent", "percent": 99}}, [agent], turns=True)
        self.assertEqual(took_turns["behavior"]["state"], "human_agent")
        self.assertEqual(took_turns["behavior"]["reasons"][0]["text"], "A human and an agent took turns in this session.")
        whole_way = self.layers({"behavior": {"state": "mixed", "leans": "agent", "percent": 71}}, [agent])
        self.assertEqual((whole_way["behavior"]["state"], whole_way["behavior"]["percent"]), ("agent", 71))
        self.assertNotIn("took turns", whole_way["behavior"]["reasons"][0]["text"])

    def test_a_layer_lists_only_what_fits_its_conclusion(self):
        human = verdict_text.reason("behavior.human", "page", "human", human_pct=60)
        overruled = verdict_text.reason("behavior.overruled")
        agent = verdict_text.reason("behavior.agent", "page", ["rules"], basis=["rules"], kinds=["approach"])
        said = self.layers({"behavior": {"state": "agent", "leans": "agent", "percent": 88}}, [agent, human, overruled])
        self.assertEqual([r["text"] for r in said["behavior"]["reasons"]], [agent["text"]])
        said = self.layers({"behavior": {"state": "human", "leans": "human", "percent": 83}}, [human, overruled])
        self.assertEqual(len(said["behavior"]["reasons"]), 2)

    def test_a_sentence_read_from_two_places_is_said_once_with_both_details(self):
        first = dict(verdict_text.reason("name.ua", "page", "x", half="page", name="X", kind_label="AI agent"))
        second = dict(verdict_text.reason("name.ua", "server", "x", half="server", name="X", kind_label="AI agent"))
        said = self.layers({"name": {"state": "agent", "leans": "agent", "percent": 90}}, [first, second])["name"]
        self.assertEqual(len(said["reasons"]), 1)
        self.assertEqual(said["reasons"][0]["detail"], f"{first['detail']} {second['detail']}")

    def test_a_layers_percent_is_shown_only_for_its_own_conclusion(self):
        said = self.layers({"environment": {"state": "unsure", "leans": "agent", "percent": 60}}, [])["environment"]
        self.assertEqual((said["state"], said["percent"]), ("unknown", None))

    def test_an_impersonated_bots_name_layer_reads_agent_with_the_name_it_gave(self):
        """Googlebot's User-Agent from outside Google's ranges is an Agent: its name layer reads Agent, not Bot, and
        still says which name the visitor gave."""
        judged = verdict.decide(verdict_cases.evidence(uas=verdict_cases.GOOGLEBOT, platform="Linux x86_64"))
        said = self.layers(judged["layers"], judged["reasons"])["name"]
        self.assertEqual((said["state"], said["percent"]), ("agent", 99))
        self.assertEqual([r["text"] for r in said["reasons"]], ["This visitor identifies itself as Googlebot."])


class LimitedEvidenceTitle(JudgingCase):
    """A session uploaded, judged and opened as the page opens it: a Human session on limited evidence is titled by
    why the behavior layer judged nothing."""

    def opened(self, raw, env=None, ua=CHROME):
        body = visit_batch(0, T0, raw, ua=ua)
        if env:
            body["x"].append({"t": T0 + 5, "ty": "env", "env": env})
        self.post(body, T0)
        answer = Client().get(f"/api/session/{SID}")
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "session"), [])
        return answer.body

    def test_a_phone_or_tablet_with_many_taps_is_never_titled_too_few_actions(self):
        body = self.opened(clicks(20, T0), env=PHONE, ua=verdict_cases.IPHONE)
        behavior = next(layer for layer in body["layers"] if layer["layer"] == "behavior")
        self.assertEqual((body["session"]["verdict"], body["session"]["evidence"]), ("human", "thin"))
        self.assertIn("phone or tablet", " ".join(reason["text"] for reason in behavior["reasons"]))
        self.assertNotEqual(body["title"], "Not enough actions to classify")
        self.assertEqual(body["title"], answers.words()["title"]["touch"])

    def test_too_few_actions_on_a_computer_is_still_titled_so(self):
        body = self.opened(clicks(1, T0))
        self.assertEqual((body["session"]["evidence"], body["title"]), ("thin", "Not enough actions to classify"))


class Share(unittest.TestCase):
    def test_the_share_counts_the_actions_every_action_lists_by_who_took_them(self):
        found = [actions_api.Action(0, "open", None, None, "unsure"), actions_api.Action(1, "click", None, None, "agent"),
                 actions_api.Action(2, "click", None, None, "agent"), actions_api.Action(3, "type", None, None, "human")]
        self.assertEqual(actions_api.share(found), {"human": 33, "agent": 67, "unsure": 0})
        self.assertEqual(actions_api.share([]), {"human": 0, "agent": 0, "unsure": 0})


if __name__ == "__main__":
    unittest.main()
