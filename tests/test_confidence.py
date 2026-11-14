"""agentcake/detect/confidence.py: the percents a verdict shows (plan step S3.7, decision D36).

    python3 -I -m unittest discover -s tests -v

A verdict's layers each lean one way with a chance, or nowhere; the session's percent is the chance its class is
right, the layers' log-likelihood ratios added. The table here is made by hand so that each number can be followed.
"""
import math
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import confidence  # noqa: E402

TABLE = {"clamp": [0.01, 0.99],
         "behaviour": {"score_limit": 12, "blocks": [[-2.0, 0.05], [0.0, 0.5], [2.0, 0.9], [12.0, 0.98]]},
         "layers": {"verified": 0.999, "impersonation": 0.99, "self_reported": 0.9, "env_hard": 0.999,
                    "env_counted": 0.9, "env_soft_alone": 0.75}}
OFF = {"state": "off"}


def segments(*probabilities, who="agent"):
    return [{"p": p, "who": who} for p in probabilities]


def behaviour(*probabilities, verdict="agent"):
    return {"verdict": verdict, "segments": segments(*probabilities)}


def result(cls, layers=None, reasons=(), verification=None):
    base = {"name": OFF, "verify": OFF, "environment": {"state": "no_hit"}, "behavior": {"state": "human"}}
    return {"class": cls, "layers": {**base, **(layers or {})}, "reasons": list(reasons), "verification": verification}


def annotate(res, behaviour_result=None):
    return confidence.annotate(res, {"behavior": behaviour_result}, TABLE)


class BehaviourTest(unittest.TestCase):
    def test_the_score_is_the_mean_log_odds_of_the_segments_held_inside_the_limit(self):
        self.assertAlmostEqual(confidence.score(segments(0.5, 0.5), 12), 0.0)
        self.assertAlmostEqual(confidence.score(segments(0.9, 0.1), 12), 0.0)
        self.assertEqual(confidence.score(segments(1.0), 12), 12)

    def test_the_map_gives_the_chance_of_the_block_the_score_falls_in(self):
        self.assertEqual(confidence.behaviour_chance(behaviour(0.02, 0.03), "human", TABLE), 0.05)
        self.assertEqual(confidence.behaviour_chance(behaviour(0.8, 0.7), "agent", TABLE), 0.9)
        self.assertEqual(confidence.behaviour_chance(behaviour(1.0), "agent", TABLE), 0.98)

    def test_too_little_data_or_no_model_is_no_chance(self):
        self.assertIsNone(confidence.behaviour_chance({"verdict": "too_little_data", "segments": []}, "agent", TABLE))
        self.assertIsNone(confidence.behaviour_chance(None, "agent", TABLE))

    def test_in_a_human_and_agent_session_the_agents_runs_are_scored(self):
        mixed = {"verdict": "unsure", "segments": segments(0.99, 0.99) + segments(0.01, 0.01, 0.01, who="human")}
        self.assertEqual(confidence.behaviour_chance(mixed, "mixed", TABLE), 0.98)
        self.assertEqual(confidence.behaviour_chance(mixed, "not_sure", TABLE), 0.5)


class LayersTest(unittest.TestCase):
    def test_a_layer_that_found_nothing_or_did_not_run_leans_nowhere(self):
        out = annotate(result("human"), behaviour(0.02, 0.03, verdict="human"))
        for name in ("name", "verify", "environment"):
            self.assertEqual((out["layers"][name]["leans"], out["layers"][name]["percent"]), (None, None), name)
        self.assertEqual(out["layers"]["environment"]["state"], "no_hit")  # the state stays as it was

    def test_behaviour_leans_to_the_side_of_its_chance(self):
        out = annotate(result("human"), behaviour(0.02, 0.03, verdict="human"))
        self.assertEqual((out["layers"]["behavior"]["leans"], out["layers"]["behavior"]["percent"]), ("human", 95))

    def test_behaviour_leans_to_its_own_conclusion_and_says_how_sure_it_is(self):
        human_said = annotate(result("human"), behaviour(0.8, 0.7, verdict="human"))  # the map reads 90% agent
        self.assertEqual((human_said["layers"]["behavior"]["leans"], human_said["layers"]["behavior"]["percent"]),
                         ("human", 10))
        agent_said = annotate(result("agent", {"behavior": {"state": "agent"}}), behaviour(0.02, 0.03))
        self.assertEqual((agent_said["layers"]["behavior"]["leans"], agent_said["layers"]["behavior"]["percent"]),
                         ("agent", 5))
        unsure = annotate(result("not_sure", {"behavior": {"state": "unsure"}}), behaviour(0.8, 0.7, verdict="unsure"))
        self.assertEqual(unsure["layers"]["behavior"]["leans"], "agent")  # no side of its own: its chance's
        self.assertEqual(human_said["percent"], 10)  # the session's percent: the same log-odds either way

    def test_a_hard_trace_and_soft_traces_alone(self):
        hard = annotate(result("agent", {"environment": {"state": "agent"}},
                               [{"strength": "hard", "tone": "agent"}]))
        soft = annotate(result("not_sure", {"environment": {"state": "unsure"}}))
        self.assertEqual((hard["layers"]["environment"]["leans"], hard["layers"]["environment"]["percent"]),
                         ("agent", 99))
        self.assertEqual((soft["layers"]["environment"]["leans"], soft["layers"]["environment"]["percent"]),
                         ("agent", 75))

    def test_a_name_counts_by_how_it_was_checked(self):
        said = annotate(result("agent", {"name": {"state": "agent"}}, verification="self_reported"))
        self.assertEqual((said["layers"]["name"]["leans"], said["layers"]["name"]["percent"]), ("agent", 90))
        bot = annotate(result("bot", {"name": {"state": "bot"}, "verify": {"state": "bot"}}, verification="verified"))
        self.assertEqual((bot["layers"]["name"]["leans"], bot["layers"]["verify"]["percent"]), ("bot", 99))


class SessionTest(unittest.TestCase):
    def test_a_humans_percent_is_the_chance_of_a_human(self):
        self.assertEqual(annotate(result("human"), behaviour(0.02, 0.03, verdict="human"))["percent"], 95)

    def test_layers_add_their_log_likelihood_ratios(self):
        out = annotate(result("agent", {"name": {"state": "agent"}}, verification="self_reported"),
                       behaviour(0.8, 0.7))
        both = 1 / (1 + math.exp(-(math.log(0.9 / 0.1) + math.log(0.9 / 0.1))))
        self.assertEqual(out["percent"], round(100 * both))

    def test_a_hard_trace_outweighs_human_looking_behaviour(self):
        out = annotate(result("agent", {"environment": {"state": "agent"}}, [{"strength": "hard", "tone": "agent"}]),
                       behaviour(0.02, 0.03, verdict="human"))
        self.assertGreaterEqual(out["percent"], 98)

    def test_thin_evidence_is_shown_as_a_human_with_the_chance_of_a_human(self):
        self.assertEqual(annotate(result("too_little_data"), {"verdict": "too_little_data", "segments": []})["percent"],
                         50)
        unsure = annotate(result("not_sure", {"environment": {"state": "unsure"}}))  # soft traces alone: 75% agent
        self.assertEqual(unsure["percent"], 25)

    def test_an_agents_percent_reads_its_own_part(self):
        parts = [{"p": 0.99, "who": "agent", "act_t": 1}, {"p": 0.01, "who": "human", "act_t": 2},
                 {"p": 0.01, "who": "human", "act_t": 3}]
        found = {"verdict": "agent", "segments": parts}
        self.assertEqual(confidence.agent_part(found, "agent"), parts[:1])
        self.assertEqual(confidence.agent_part(found, "mixed"), parts[:1])
        self.assertEqual(confidence.agent_part(found, "human"), parts)
        checked = {**found, "timeline": {"checks": [{"check": "typing_cadence", "from": 2, "to": 2}]}}
        self.assertEqual(confidence.agent_part(checked, "agent"), parts[:2])  # a check's stretch is the agent's part

    def test_typing_that_ends_at_bot_adds_its_declared_strength_to_the_behaviour(self):
        table = {**TABLE, "layers": {**TABLE["layers"], "typing_cadence": 0.95}}
        typed = {**behaviour(0.3, 0.4, verdict="agent"), "raw_input": True,  # segments that say nothing: 0.5
                 "evidence": {"typing_cadence": {"class": "bot", "score": 0.2, "samples": 30}}}
        out = confidence.annotate(result("agent", {"behavior": {"state": "agent"}}), {"behavior": typed}, table)
        self.assertEqual((out["layers"]["behavior"]["leans"], out["percent"]), ("agent", 95))
        rrweb = confidence.annotate(result("agent", {"behavior": {"state": "agent"}}),
                                    {"behavior": {**typed, "raw_input": False}}, table)
        self.assertEqual(rrweb["percent"], 50)  # no keys without raw input: the typing is not read

    def test_a_bot_counts_by_its_check_and_an_excluded_session_has_none(self):
        self.assertEqual(annotate(result("bot", {"name": {"state": "bot"}}, verification="self_reported"))["percent"],
                         90)
        self.assertIsNone(annotate(result("excluded"))["percent"])

    def test_percents_stay_inside_the_clamp(self):
        out = annotate(result("agent", {"environment": {"state": "agent"}, "name": {"state": "agent"}},
                              [{"strength": "hard", "tone": "agent"}], verification="verified"), behaviour(1.0))
        self.assertEqual(out["percent"], 99)


if __name__ == "__main__":
    unittest.main()
