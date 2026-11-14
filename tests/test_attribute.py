"""Which agent or bot a session is (agentcake.detect.attribute), through the whole verdict.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Name priority: a verified signature or published range > a page product rule > a self-reported name > an
extension's own trace > an automation tool's trace > a category only. The lab's 4 Claude in
Chrome runs are "likely Claude in Chrome" (the attribute-less div); its 22 Playwright runs are Agent · Automated
browser and named only where a trace names the tool; a signed request is named after its signer; the 10 User-Agents of
threshold A7 get the right name and category; case T22's listed bots are Bots and its cloud script an Agent that looks like
a crawler (A9).
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_lists import A7  # noqa: E402  (the 10 User-Agents of threshold A7, as the list tests use them)
from verdict_cases import (AGENT_RUN, AUTOMATION_HITS, CHROME_LINUX, GOOGLEBOT, HEADLESS, HUMAN_RUN, MANUS,  # noqa: E402
                           T0, UPTIMEROBOT, S, behavior, crawl_pages, evidence, first_address, hit, too_little,
                           verified)
from agentcake.detect import verdict  # noqa: E402



def ids(result):
    return [r["id"] for r in result["reasons"]]


def naming(result):
    return result["name"], result["name_certainty"], result["category"]


class Priority(unittest.TestCase):
    def test_verified_signature_outranks_a_product_rule_and_says_so(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, hits=[hit("env.product.muse")],
                                         signatures={"collector": verified("chatgpt.com")},
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(naming(result), ("chatgpt", "certain", None))
        self.assertEqual(result["name_method"], "signature")
        self.assertIn("name.outranked", ids(result))

    def test_product_rule_outranks_a_declared_name(self):
        result = verdict.decide(evidence(uas=MANUS, hits=[hit("env.product.muse")], behavior_result=too_little()))
        self.assertEqual(naming(result), ("muse", "likely", None))
        self.assertIn("name.outranked", ids(result))

    def test_product_rule_sets_the_row_of_its_product(self):
        # Cloudflare Browser Run is an automated browser in the lists (kinds.json), though product rules point to AI
        # in a real browser otherwise (verdict.json env_rows); here only the page rule knows it (no name declared)
        result = verdict.decide(evidence(mode="local", hits=[hit("env.product.cloudflare-browser-run")],
                                         behavior_result=too_little()))
        self.assertEqual((result["class"], result["row"], naming(result)),
                         ("agent", "automated", ("cloudflare-browser-run", "likely", None)))

    def test_declared_name_is_likely(self):
        result = verdict.decide(evidence(uas=MANUS, behavior_result=too_little()))
        self.assertEqual((naming(result), result["name_method"]), (("manus", "likely", None), "declared"))

    def test_extension_trace_names_its_product_as_likely(self):
        result = verdict.decide(evidence(mode="local", hits=[hit("env.ext.closed-shadow-host")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(naming(result), ("claude-chrome", "likely", None))
        self.assertEqual(result["judging"], "agent_ai")
        self.assertIn("name.from-trace", ids(result))

    def test_unconfirmed_extension_trace_names_no_one(self):
        result = verdict.decide(evidence(mode="local", hits=[hit("env.ext.closed-shadow-host")],
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((result["class"], result["name"]), ("human", None))

    def test_extension_without_a_product_trace_is_a_category(self):
        result = verdict.decide(evidence(mode="local", hits=[hit("env.ext.hidden-trusted-pointerdown")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["row"], naming(result)), ("ai", (None, None, "extension")))

    def test_cloud_host_is_a_cloud_browser_that_says_nothing(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, hits=[hit("env.cloud.linux-swiftshader")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(naming(result), (None, None, "cloud_browser"))

    def test_behaviour_alone_is_possibly_a_local_agent(self):
        result = verdict.decide(evidence(behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(naming(result), (None, None, "local_agent"))

    def test_agent_range_without_a_name_is_its_operators_infrastructure(self):
        result = verdict.decide(evidence(address=first_address("openai-chatgpt-user"),
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(naming(result), (None, None, "infrastructure"))
        self.assertEqual(result["operator"], "OpenAI")

    def test_no_name_for_humans_and_unsure_sessions(self):
        for result_of_behavior in (behavior("human", HUMAN_RUN), too_little()):
            with self.subTest(result_of_behavior["verdict"]):
                result = verdict.decide(evidence(behavior_result=result_of_behavior))
                self.assertEqual(naming(result), (None, None, None))


class AutomatedBrowsers(unittest.TestCase):
    def test_tool_named_by_its_own_globals(self):
        for rule, tool in (("env.auto.playwright-globals", "playwright"), ("env.auto.puppeteer-globals", "puppeteer"),
                           ("env.auto.selenium-globals", "selenium")):
            with self.subTest(tool):
                result = verdict.decide(evidence(mode="local", hits=[hit("env.auto.webdriver"), hit(rule)],
                                                 behavior_result=behavior("agent", AGENT_RUN)))
                self.assertEqual((result["row"], naming(result)), ("automated", (tool, "likely", None)))
                self.assertEqual(result["judging"], "agent_automated")
                self.assertIn("env.automated", ids(result))  # the automated-browser sentence, named tool or not
                self.assertIn("name.tool", ids(result))

    def test_tool_named_by_its_user_agent_token(self):
        ua = CHROME_LINUX + " Puppeteer/24.0"
        result = verdict.decide(evidence(mode="local", uas=ua, hits=[hit("env.auto.webdriver")],
                                         behavior_result=too_little()))
        self.assertEqual(naming(result), ("puppeteer", "likely", None))

    def test_headless_chrome_is_no_tool_name(self):
        result = verdict.decide(evidence(mode="local", uas=HEADLESS, hits=[hit(r) for r in AUTOMATION_HITS],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(naming(result), (None, None, "automated"))

    def test_tools_that_disagree_name_none(self):
        result = verdict.decide(evidence(mode="local", hits=[hit("env.auto.webdriver"),
                                                             hit("env.auto.playwright-globals"),
                                                             hit("env.auto.puppeteer-globals")],
                                         behavior_result=too_little()))
        self.assertEqual(naming(result), (None, None, "automated"))
        self.assertIn("name.disagree", ids(result))


class GoalA7(unittest.TestCase):
    """The 10 User-Agents of threshold A7, judged on this computer (self-reported only)."""

    def test_ten_user_agents_named_and_classed(self):
        for ua, list_id, category, kind in A7:
            with self.subTest(list_id):
                result = verdict.decide(evidence(mode="local", uas=ua, behavior_result=too_little()))
                self.assertEqual((result["name"], result["kind"]), (list_id, kind))
                self.assertEqual(result["class"], "bot" if category == "bot" else "agent")
                self.assertEqual(result["verification"], "self_reported")


class GoalT22(unittest.TestCase):
    """Case T22, with addresses as a load balancer would give them (the first address of a published range)."""

    def test_googlebot_three_ways(self):
        verified_bot = verdict.decide(evidence(uas=GOOGLEBOT, address=first_address("google-common-crawlers")))
        home = verdict.decide(evidence(uas=GOOGLEBOT, behavior_result=behavior("agent", AGENT_RUN)))
        unknown = verdict.decide(evidence(uas=GOOGLEBOT, address=None))
        self.assertEqual((verified_bot["class"], verified_bot["name"], verified_bot["verification"]),
                         ("bot", "googlebot", "verified"))
        self.assertEqual((home["class"], home["row"], home["name"], home["impersonating"]),
                         ("agent", "automated", None, "googlebot"))
        self.assertEqual((unknown["class"], unknown["name"], unknown["verification"]),
                         ("bot", "googlebot", "self_reported"))

    def test_uptimerobot_three_times(self):
        for address in (first_address("aws"), None, "198.51.100.20"):
            with self.subTest(address=address):
                result = verdict.decide(evidence(uas=UPTIMEROBOT, address=address))
                self.assertEqual((result["class"], result["name"], result["verification"]),
                                 ("bot", "uptimerobot", "self_reported"))

    def test_cloud_script_every_five_minutes_is_an_agent_that_looks_like_a_crawler(self):
        every_s, rounds = 300, 3
        for round_number in range(rounds):
            start = T0 + round_number * every_s * S
            pages = [{"t": start + i * 2 * S} for i in range(15)]
            visits = [T0 + k * every_s * S for k in range(round_number)]
            with self.subTest(round=round_number + 1):
                result = verdict.decide(evidence(uas=HEADLESS, hits=[hit(r) for r in AUTOMATION_HITS],
                                                 address=first_address("aws"), pages=pages, visits=visits,
                                                 behavior_result=too_little(n_actions=0)))
                self.assertEqual((result["class"], result["row"], result["category"]), ("agent", "automated",
                                                                                        "automated"))
                crawler = next(r for r in result["reasons"] if r["id"] == "crawler.like")
                self.assertIn("datacenter", crawler["detail"])
                self.assertIn("15 pages", crawler["detail"])

    def test_coming_back_every_five_minutes_is_said(self):
        visits = [T0 - k * 300 * S for k in range(1, 4)]
        result = verdict.decide(evidence(uas=HEADLESS, hits=[hit(r) for r in AUTOMATION_HITS], visits=visits,
                                         address=first_address("aws"), pages=crawl_pages(3, 20),
                                         behavior_result=too_little(n_actions=0)))
        crawler = next(r for r in result["reasons"] if r["id"] == "crawler.like")
        self.assertIn("comes back every 5 min", crawler["detail"])


if __name__ == "__main__":
    unittest.main()
