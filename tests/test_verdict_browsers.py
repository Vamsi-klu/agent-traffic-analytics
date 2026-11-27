"""The name of a browser people also use by hand (a kind marked browser in kinds.json, such as an AI desktop app's own
browser) in the verdict: it says where the page is open, never who acts in it (agentcake/detect/attribute.py).

    python3 -I -m unittest discover -s tests -p test_verdict_browsers.py -v      (from the repository root)

Named by its User-Agent (Antigravity's in-app browser) or by a product rule (the Codex in-app browser), such a browser
leaves the class to automation traces and behaviour, as any browser does; when they find an agent, its name is the
agent's. A rule its list entry says that browser matches by design is left out. A product rule that names no browser
(Muse) still says an agent is here.

Muse and Grok Bot drive their own cloud browser (verdict.json "mixed" "handoff_only"), where a human can only take over
the agent's live view: their human-looking actions are the agent's, and such a session is Human + agent only when its
timeline shows the agent acting and a hand-off.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import (AGENT_RUN, ANTIGRAVITY, CHROME_LINUX, HUMAN_RUN, behavior, evidence,  # noqa: E402
                           first_address, hit, run, too_little, verified)
from agentcake.api import visits  # noqa: E402
from agentcake.detect import verdict  # noqa: E402

# Grok Bot's cloud computer: a plain Chrome 139 on Linux, named only by its page rule
UA_G = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
CLOUD_AGENTS = ("muse", "grok-bot")  # list ids verdict.json "mixed" "handoff_only" names
HUMANLIKE = "behavior.humanlike-cloud-agent"
TAKEOVER = (AGENT_RUN, run("human", 61, 120, 15, 0.08))  # the agent acts, then a human takes over its live view


def ids(result):
    return [r["id"] for r in result["reasons"]]


def in_cloud_browser(list_id, behavior_result, **more):
    """A session in the cloud browser of Muse or Grok Bot, named by its page rule, with this behaviour."""
    if list_id == "grok-bot":
        return evidence(uas=UA_G, platform="Linux x86_64", hits=[hit("env.product.grok-bot"),
                                                                 hit("env.cloud.linux-swiftshader")],
                        address=first_address("aws"), behavior_result=behavior_result, **more)
    return evidence(uas=CHROME_LINUX, platform="Linux x86_64", hits=[hit("env.product.muse")],
                    behavior_result=behavior_result, **more)


class DeclaredBrowser(unittest.TestCase):
    def test_a_human_in_an_ai_apps_browser_is_a_human(self):
        result = verdict.decide(evidence(uas=ANTIGRAVITY, behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((result["class"], result["name"], result["layers"]["name"]["state"]),
                         ("human", None, "no_hit"))
        said = {r["id"]: r for r in result["reasons"]}
        self.assertEqual(said["name.ua-browser"]["tone"], "none")
        self.assertNotIn("verify.no-range", said)

    def test_an_agent_in_an_ai_apps_browser_gets_the_browsers_name(self):
        result = verdict.decide(evidence(uas=ANTIGRAVITY, behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["row"], result["name"], result["name_certainty"]),
                         ("agent", "ai", "antigravity-browser", "likely"))
        self.assertEqual(result["confidence"], "possible")  # behaviour's own level: the browser's name adds nothing

    def test_too_little_behaviour_in_an_ai_apps_browser_is_too_little_data(self):
        result = verdict.decide(evidence(uas=ANTIGRAVITY, behavior_result=too_little()))
        self.assertEqual((result["class"], result["name"]), ("too_little_data", None))

    def test_a_trace_the_browser_shows_by_design_says_nothing(self):
        traces = [hit("env.auto.chromium-only-brand"), hit("env.auto.cdp-runtime-leak")]
        in_antigravity = verdict.decide(evidence(uas=ANTIGRAVITY, hits=traces,
                                                 behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual(in_antigravity["class"], "human")
        self.assertNotIn("env.auto.chromium-only-brand", ids(in_antigravity))
        self.assertIn("env.soft-alone", ids(in_antigravity))
        elsewhere = verdict.decide(evidence(hits=traces, behavior_result=behavior("human", HUMAN_RUN)))
        self.assertIn(elsewhere["class"], ("agent", "mixed"))  # two soft rules still confirm each other


class BrowserProductRule(unittest.TestCase):
    def test_a_browsers_product_rule_names_but_does_not_decide(self):
        human = verdict.decide(evidence(hits=[hit("env.product.codex-browser")],
                                        behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((human["class"], human["name"], human["layers"]["environment"]["state"]),
                         ("human", None, "no_hit"))
        driven = verdict.decide(evidence(hits=[hit("env.product.codex-browser"), hit("env.auto.playwright-globals")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((driven["class"], driven["row"], driven["name"], driven["name_method"]),
                         ("agent", "ai", "codex-browser", "product-rule"))
        rule = next(r for r in driven["reasons"] if r["id"] == "env.product.codex-browser")
        self.assertEqual(rule["tone"], "none")

    def test_another_products_rule_names_the_agent_before_the_browsers_own(self):
        """The class rests on the other product (strong_name leaves browsers out), so the name does too: a browser's
        rule names the agent only when nothing else does, and it does not disagree with the agent it hosts."""
        result = verdict.decide(evidence(hits=[hit("env.product.codex-browser"), hit("env.product.chatgpt-chrome")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["name"], result["name_method"]),
                         ("agent", "chatgpt-chrome", "product-rule"))
        self.assertNotIn("name.disagree", ids(result))

    def test_a_product_rule_that_names_no_browser_still_says_an_agent_is_here(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, hits=[hit("env.product.muse")],
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((result["class"], result["name"]), ("agent", "muse"))


class CloudBrowserNeedsHandoff(unittest.TestCase):
    """Muse and Grok Bot: Human + agent needs the agent's part and a hand-off on the timeline, else it is an Agent."""

    def judged(self, list_id, *runs, said="human", **more):
        return verdict.decide(in_cloud_browser(list_id, behavior(said, *runs), **more))

    def test_human_looking_actions_alone_are_the_agents_and_say_why(self):
        for list_id in CLOUD_AGENTS:
            with self.subTest(list_id):
                result = self.judged(list_id, HUMAN_RUN)
                self.assertEqual((result["class"], result["name"], result["confidence"], result["handoffs"]),
                                 ("agent", list_id, "likely", []))
                said = next(r for r in result["reasons"] if r["id"] == HUMANLIKE)
                self.assertEqual((said["value"], said["layer"], said["grade"], said["tone"]),
                                 (list_id, "behavior", "inferred", "none"))  # tone none: shown beside a human layer
                self.assertIn(result["display_name"], said["text"])
                self.assertEqual({segment["who"] for segment in result["segments"]}, {"agent"})

    def test_a_verified_signature_beside_the_rule_leaves_it_the_agents(self):
        result = self.judged("muse", HUMAN_RUN, signatures={"collector": verified("muse.ai")})
        self.assertEqual((result["class"], result["name"], result["verification"], result["confidence"]),
                         ("agent", "muse", "verified", "certain"))
        self.assertIn(HUMANLIKE, ids(result))

    def test_the_verified_signature_alone_names_it_the_same_way(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, platform="Linux x86_64",
                                         signatures={"collector": verified("muse.ai")},
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((result["class"], result["name"], result["verification"], result["confidence"]),
                         ("agent", "muse", "verified", "certain"))
        self.assertIn(HUMANLIKE, ids(result))

    def test_a_human_run_just_long_enough_where_behaviour_could_not_tell_is_the_agents(self):
        for list_id in CLOUD_AGENTS:
            with self.subTest(list_id):
                result = self.judged(list_id, run("human", 0, 3, 3, 0.3), said="unsure")  # 3 actions over 3 s
                self.assertEqual(result["class"], "agent")
                self.assertIn(HUMANLIKE, ids(result))

    def test_a_human_taking_over_after_the_agent_acted_is_human_plus_agent(self):
        for list_id in CLOUD_AGENTS:
            with self.subTest(list_id):
                result = self.judged(list_id, *TAKEOVER, said="agent")
                self.assertEqual((result["class"], result["name"]), ("mixed", list_id))
                self.assertEqual(result["handoffs"][0]["to"], "human")
                self.assertNotIn(HUMANLIKE, ids(result))

    def test_the_agent_acting_alone_is_the_agents_with_nothing_to_explain(self):
        for list_id in CLOUD_AGENTS:
            with self.subTest(list_id):
                result = self.judged(list_id, AGENT_RUN, said="agent")
                self.assertEqual((result["class"], result["name"]), ("agent", list_id))
                self.assertNotIn(HUMANLIKE, ids(result))

    def test_the_pages_show_human_looking_actions_as_agent_only_and_a_takeover_as_human_plus_agent(self):
        for list_id in CLOUD_AGENTS:
            with self.subTest(list_id):
                for runs, said, shown in (((HUMAN_RUN,), "human", ("agent", "agent_only")),
                                          (TAKEOVER, "agent", ("agent", "human_agent"))):
                    cls = self.judged(list_id, *runs, said=said)["class"]
                    self.assertEqual((visits.verdict_of(cls, None), visits.turns_of(cls, None)), shown)

    def test_the_behaviour_layer_says_what_behaviour_saw_never_human_plus_agent_alone(self):
        for list_id in CLOUD_AGENTS:
            with self.subTest(list_id):
                for runs, said, want in (((HUMAN_RUN,), "human", ("agent", "human")),
                                         ((run("human", 0, 3, 3, 0.3),), "unsure", ("agent", "unsure")),
                                         (TAKEOVER, "agent", ("mixed", "mixed"))):
                    result = self.judged(list_id, *runs, said=said)
                    self.assertEqual((result["class"], result["layers"]["behavior"]["state"]), want)


if __name__ == "__main__":
    unittest.main()
