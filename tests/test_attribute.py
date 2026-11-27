"""Which agent or bot a session is (agentcake.detect.attribute), through the whole verdict.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Name priority: a verified signature or published range > a page product rule > a self-reported name > an
extension's own trace > an automation tool's trace > a category only. The lab's 4 Claude in
Chrome runs are "likely Claude in Chrome" (the attribute-less div); its 22 Playwright runs are Agent · Automated
browser and named only where a trace names the tool; a signed request is named after its signer; the 10 User-Agents of
threshold A7 get the right name and category; case T22's listed bots are Bots and its cloud script an Agent that looks like
a crawler (A9). The names the interface's samples show are names a session can get, and the interface has a word only
for the certainties naming gives.
"""
import glob, json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_lists import A7  # noqa: E402  (the 10 User-Agents of threshold A7, as the list tests use them)
from verdict_cases import (AGENT_RUN, AUTOMATION_HITS, CHROME_LINUX, GOOGLEBOT, HEADLESS, HUMAN_RUN, MANUS,  # noqa: E402
                           T0, UPTIMEROBOT, S, behavior, crawl_pages, evidence, first_address, hit, too_little,
                           verified)
from agentcake import datafiles  # noqa: E402
from agentcake.detect import env_rules, verdict, verdict_text  # noqa: E402

# The samples: the home page's example (GET /api/setup), the answers the screenshot and dev servers give (the recorded
# replays aside: they are the shop's own pages) and the component overview's agent tags.
SAMPLE_FILES = [os.path.join(ROOT, "agentcake", "data", "example.json")] + sorted(
    path for path in glob.glob(os.path.join(ROOT, "web", "src", "data", "fixtures", "**", "*.json"), recursive=True)
    if os.sep + "replay" + os.sep not in path)
COMPONENTS_PAGE = os.path.join(ROOT, "web", "src", "pages", "components.tsx")
AGENT_TAG = re.compile(r'<AgentTag name="([^"]+)"(?: certainty="([^"]+)")?')
NO_NAME = re.compile(r"no name|without a name|isn't named|gets no name", re.IGNORECASE)  # a reason saying none is shown



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

    def test_grok_bot_signals_name_the_same_product(self):
        ua = CHROME_LINUX + " GrokAgent/1.0"
        grok = hit("env.product.grok-bot")
        for hits, signatures, method in (
            ([], {}, "declared"),
            ([grok], {}, "product-rule"),
            ([grok], {"collector": verified("cursorusercontent.com")}, "signature"),
        ):
            with self.subTest(method=method):
                result = verdict.decide(evidence(uas=ua, hits=hits, signatures=signatures,
                                                 behavior_result=too_little()))
                self.assertEqual((result["class"], result["name"], result["name_method"]),
                                 ("agent", "grok-bot", method))
                self.assertNotIn("name.outranked", ids(result))
                self.assertNotIn("name.disagree", ids(result))

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

    def test_no_reason_says_there_is_no_name_when_another_method_names_the_visit(self):
        # names that conflict, disagree or were impersonated count for nothing, but a method of another priority
        # may still name the visit: then no reason on its page may say that the visit has no name
        conflict = CHROME_LINUX + " Manus-User/1.0 ChatGPT-User/1.0"  # two product names at once
        cases = {"user-agent names in conflict, a verified signature":
                 evidence(uas=conflict, signatures={"collector": verified("chatgpt.com")},
                          behavior_result=behavior("agent", AGENT_RUN)),
                 "product rules that disagree, a verified signature":
                 evidence(uas=CHROME_LINUX, hits=[hit("env.product.muse"), hit("env.product.instinct")],
                          signatures={"collector": verified("chatgpt.com")}, behavior_result=behavior("agent", AGENT_RUN)),
                 "an impersonated crawler's name, a product rule":
                 evidence(uas=GOOGLEBOT, hits=[hit("env.product.muse")], behavior_result=behavior("agent", AGENT_RUN))}
        for label, case in cases.items():
            with self.subTest(label):
                result = verdict.decide(case)
                said = [verdict_text.words(r)[0] for r in result["reasons"]]
                self.assertIsNotNone(result["name"])
                self.assertEqual([text for text in said if NO_NAME.search(text)], [])

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
        self.assertIn("returns every 5 minutes", crawler["detail"])


def names_cake_gives():
    """{"agent" | "bot": {display name: whether a check can verify it}}: the list entries a naming source points to,
    as attribute.py's levels read them (a signer, a published range's verifies, an environment rule's names or
    suggests, a User-Agent pattern or navigator.platform), less the tools that never name themselves (verdict.json)."""
    names, kinds = datafiles.load("data/lists/names.json"), datafiles.load("data/lists/kinds.json")["kinds"]
    signers = datafiles.load("data/lists/signers.json")["signers"].values()
    verifiable = {signer["name"] for signer in signers} | {
        list_id for spec in datafiles.load("data/lists/ip_ranges.json")["ranges"] for list_id in spec.get("verifies", [])}
    pointed = verifiable | {rule.names or rule.suggests for rule in env_rules.load_rules().rules} | set(
        names["platforms"].values()) | {entry["id"] for entry in names["names"] if entry["patterns"]}
    never = datafiles.load("data/verdict.json")["attribution"]["not_tools"]
    found = {"agent": {}, "bot": {}}
    for entry in names["names"]:
        if entry["id"] in pointed and entry["id"] not in never:
            named = found[kinds[entry["kind"]]["category"]]
            named[entry["name"]] = named.get(entry["name"], False) or entry["id"] in verifiable
    return found


def sample_names(value):
    """(name, certainty, "agent" | "bot") of every name a sample answer shows: a session's (its verdict and agent),
    the session list's agent filter (agent_names) and the agent counts (agents_seen, agents; null there is Unnamed)."""
    if isinstance(value, list):
        return [found for item in value for found in sample_names(item)]
    if not isinstance(value, dict):
        return []
    found = [(value["agent"], value.get("certainty"), value["verdict"])] if (
        value.get("verdict") in ("agent", "bot") and value.get("agent")) else []
    found += [(name, None, "agent") for name in value.get("agent_names") or []]
    found += [(row["name"], None, "agent") for key in ("agents_seen", "agents") for row in value.get(key) or []
              if isinstance(row, dict) and row.get("name")]
    return found + [inner for item in value.values() for inner in sample_names(item)]


class SampleNames(unittest.TestCase):
    """The interface's samples show only names a session can get, each with a certainty naming gives it: Verified
    only where a signature or a published range can check that name."""

    @classmethod
    def setUpClass(cls):
        cls.names = names_cake_gives()
        words = datafiles.load("data/api.json")["certainty"]
        cls.certainties = {words[given] for given in
                           datafiles.load("data/verdict.json")["attribution"]["certainty"].values()}

    def check(self, where, name, certainty, category):
        with self.subTest(where, name=name, certainty=certainty):
            self.assertTrue(name in self.names[category], f"no naming source gives {category} sessions this name")
            self.assertIn(certainty, self.certainties | {None})
            if certainty == "verified":
                self.assertTrue(self.names[category][name], "neither a signer nor a published range verifies it")

    def test_sample_sessions_and_agent_counts_show_names_cake_gives(self):
        for path in SAMPLE_FILES:
            with open(path, encoding="utf-8") as f:
                found = sample_names(json.load(f))
            for name, certainty, category in found:
                self.check(os.path.relpath(path, ROOT), name, certainty, category)

    def test_the_component_overview_tags_names_cake_gives(self):
        with open(COMPONENTS_PAGE, encoding="utf-8") as f:
            tags = AGENT_TAG.findall(f.read())
        self.assertTrue(tags)
        for name, certainty in tags:
            self.check("components.tsx", name, certainty or None, "agent")

    def test_the_interface_words_only_the_certainties_naming_gives(self):
        """A name is verified or likely (verdict.json attribution): none comes from behaviour alone."""
        given = set(datafiles.load("data/verdict.json")["attribution"]["certainty"].values())
        self.assertEqual(set(datafiles.load("data/api.json")["certainty"]), given)


if __name__ == "__main__":
    unittest.main()
