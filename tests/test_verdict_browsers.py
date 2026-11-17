"""The name of a browser people also use by hand (a kind marked browser in kinds.json, such as an AI desktop app's own
browser) in the verdict: it says where the page is open, never who acts in it (agentcake/detect/attribute.py).

    python3 -I -m unittest discover -s tests -p test_verdict_browsers.py -v      (from the repository root)

Named by its User-Agent (Antigravity's in-app browser) or by a product rule (the Codex in-app browser), such a browser
leaves the class to automation traces and behaviour, as any browser does; when they find an agent, its name is the
agent's. A rule its list entry says that browser matches by design is left out. A product rule that names no browser
(Muse) still says an agent is here.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import (AGENT_RUN, ANTIGRAVITY, CHROME_LINUX, HUMAN_RUN, behavior, evidence, hit,  # noqa: E402
                           too_little)
from agentcake.detect import verdict  # noqa: E402


def ids(result):
    return [r["id"] for r in result["reasons"]]


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
        self.assertEqual((result["class"], result["name"]), ("mixed", "muse"))


if __name__ == "__main__":
    unittest.main()
