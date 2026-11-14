"""S3.1: the name and verification lists, read and matched on this computer without any network.

    python3 -I -m unittest discover -s tests -v      (from the cake folder)

Checks the bundled lists in agentcake/data/lists/: ten self-declared User-Agents get the right name and category
(GOAL A7: AI working for a human is an Agent, a named non-agent program is a Bot, D17), the classes PostHog can name
are named too (GOAL section 8), ordinary browsers are never named, an address is placed in the published range it
belongs to and then forgotten, the age of the lists is reported against the I4 limit, and none of it opens a socket
(D23); the signers are checked in test_lists_signers.py. Addresses used here are read from the bundled ranges at
test time or come from the documentation ranges of RFC 5737, so no real visitor address appears in this file.
"""
import datetime, ipaddress, json, os, shutil, socket, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from agentcake.detect import lists  # noqa: E402

BUNDLED = os.path.join(HERE, "agentcake", "data", "lists")
TEST_NET = "192.0.2.10"  # RFC 5737 documentation range: in nobody's published list

# GOAL A7: (User-Agent, list id, category, kind). Strings are the vendors' documented forms; Claude-Agent's comes
# from a second-hand source and is marked unverified in the list.
A7 = [
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
     "chatgpt-user", "agent", "ai-assistant"),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot",
     "gptbot", "bot", "ai-crawler"),
    ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-Agent/1.0) "
     "Chrome/142.0.0.0 Safari/537.36", "claude-agent", "agent", "cloud-agent"),
    ("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/142.0.7444.59 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
     "googlebot", "bot", "search-crawler"),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) "
     "Chrome/116.0.1938.76 Safari/537.36", "bingbot", "bot", "search-crawler"),
    ("Mozilla/5.0+(compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)", "uptimerobot", "bot", "monitoring"),
    ("Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/135.0.0.0 Mobile Safari/537.36 Chrome-Lighthouse", "lighthouse", "bot", "seo-audit"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 "
     "Safari/537.36 PTST/251105.150512", "ptst", "bot", "seo-audit"),
    ("Mozilla/5.0 (compatible; AhrefsSiteAudit/6.1; +http://ahrefs.com/robot/site-audit)",
     "ahrefssiteaudit", "bot", "seo-audit"),
    ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
     "facebookexternalhit", "bot", "link-preview"),
]

# GOAL section 8: the classes PostHog names, which cake has to name at least as well.
POSTHOG_CLASSES = [
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Claude/1.0.211 "
     "Chrome/138.0.7204.251 Electron/37.2.3 Safari/537.36", "agent", "ai-desktop-app", "Claude"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) ChatGPT/1.2025.300 "
     "Chrome/138.0.7204.251 Electron/37.2.3 Safari/537.36", "agent", "ai-desktop-app", "ChatGPT"),
    ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Google-Agent; "
     "+https://developers.google.com/crawling/docs/crawlers-fetchers/google-agent) Chrome/142.0.7444.59 Safari/537.36",
     "agent", "cloud-agent", "Google-Agent"),
    ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 "
     "Manus-User/1.0", "agent", "cloud-agent", "Manus"),
    ("Mozilla/5.0 (compatible; Twitterbot/1.0)", "bot", "link-preview", "X"),
    ("LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)", "bot", "link-preview",
     "LinkedIn"),
]

HUMANS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 "
    "Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 "
    "Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 "
    "Safari/537.36 Edg/142.0.0.0",
    # Pinterest's in-app browser: a human, even though Pinterest's link preview is a Bot.
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "[Pinterest/iOS]",
    # A point-of-sale tablet: "Toast" must not match the short "oast" probe pattern.
    "Mozilla/5.0 (Linux; Android 12; Toast Flex) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    # VS Code's built-in browser: "Code/1.105" must not read as an AI coding tool.
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Code/1.105.1 "
    "Chrome/138.0.7204.251 Electron/37.6.0 Safari/537.36",
]


def first_address(snapshot, range_id):
    """An address of a bundled range that no earlier range also holds (operators publish some blocks in two lists:
    OpenAI's SearchBot and GPTBot share some), read from the data so the test needs no literal IP."""
    for entry in snapshot.raw_ranges():
        if entry["id"] == range_id:
            for block in entry["v4"] + entry["v6"]:
                address = str(ipaddress.ip_network(block)[0])
                if snapshot.first_range(address) == (entry["label"], entry["kind"]):
                    return address
    raise AssertionError(f"range {range_id} is not bundled or every block is listed earlier too")


class NamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = lists.Lists.load(BUNDLED)

    def test_ten_declared_user_agents_get_name_and_category(self):
        for ua, list_id, category, kind in A7:
            with self.subTest(list_id=list_id):
                found = self.snapshot.match_ua(ua)
                self.assertIsNotNone(found)
                self.assertEqual((found["id"], found["category"], found["kind"]), (list_id, category, kind))
                self.assertTrue(found["name"])
                self.assertTrue(found["sources"])

    def test_cakes_own_additions_are_marked_unverified(self):
        claude = self.snapshot.match_ua(A7[2][0])
        grok = self.snapshot.match_ua("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/139.0.0.0 Safari/537.36 GrokAgent/1.0 (u:0123456789abcdef)")
        self.assertEqual(claude["evidence"], "unverified")
        self.assertEqual((grok["id"], grok["category"], grok["evidence"]), ("grokagent", "agent", "unverified"))

    def test_classes_posthog_names_are_named(self):
        for ua, category, kind, word in POSTHOG_CLASSES:
            with self.subTest(word=word):
                found = self.snapshot.match_ua(ua)
                self.assertEqual((found["category"], found["kind"]), (category, kind))
                self.assertIn(word.lower(), (found["name"] + " " + (found["operator"] or "")).lower())

    def test_every_posthog_definition_is_accounted_for(self):
        posthog = self.snapshot.sources()["posthog"]
        accounted = posthog["named"] + posthog["hints"] + len(posthog["excluded"])
        self.assertEqual(accounted, posthog["definitions"])

    def test_automated_browser_is_an_agent_in_the_automated_row(self):
        found = self.snapshot.match_ua("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "HeadlessChrome/142.0.7444.59 Safari/537.36")
        self.assertEqual((found["category"], found["kind"], found["row"]), ("agent", "automated-browser", "automated"))

    def test_ordinary_browsers_are_not_named(self):
        for ua in HUMANS + ["", None]:
            with self.subTest(ua=ua):
                self.assertIsNone(self.snapshot.match_ua(ua))

    def test_most_specific_token_wins(self):
        image = self.snapshot.match_ua("Googlebot-Image/1.0")
        mobile = self.snapshot.match_ua("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 "
                                        "(KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 "
                                        "(compatible; AdsBot-Google-Mobile; +http://www.google.com/mobile/adsbot.html)")
        self.assertEqual(image["id"], "googlebot-image")
        self.assertEqual(mobile["id"], "adsbot-google-mobile")

    def test_a_named_product_beats_a_generic_automation_token(self):
        found = self.snapshot.match_ua("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko; "
                                       "compatible; Google-Agent) HeadlessChrome/142.0.0.0 Safari/537.36")
        self.assertEqual(found["id"], "google-agent")

    def test_two_declared_link_previews_keep_category_but_no_name(self):
        # Apple's Messages preview declares two link-preview products at once.
        found = self.snapshot.match_ua("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_1) AppleWebKit/601.2.4 (KHTML, "
                                       "like Gecko) Version/9.0.1 Safari/601.2.4 facebookexternalhit/1.1 Facebot "
                                       "Twitterbot/1.0")
        self.assertIsNone(found["name"])
        self.assertEqual((found["category"], found["kind"]), ("bot", "link-preview"))
        self.assertLessEqual({"facebookexternalhit", "twitterbot"}, set(found["conflict"]))

    def test_an_agent_and_a_bot_together_give_no_category(self):
        found = self.snapshot.match_ua("Mozilla/5.0 (compatible; ChatGPT-User/1.0; UptimeRobot/2.0)")
        self.assertIsNone(found["category"])
        self.assertEqual(found["conflict"], ["chatgpt-user", "uptimerobot"])

    def test_names_known_only_from_signers_and_page_rules_are_described(self):
        self.assertEqual(self.snapshot.name("chatgpt")["category"], "agent")
        self.assertEqual(self.snapshot.name("claude-chrome")["row"], "ai")
        self.assertIsNone(self.snapshot.name("no-such-name"))

    def test_claude_in_chrome_goes_by_its_product_name(self):
        # botscent still lists it as Claude for Chrome, its earlier name: the recipe (sources.json) corrects it, and
        # no other data file says the old name (rule titles, reasons)
        self.assertEqual(self.snapshot.name("claude-chrome")["name"], "Claude in Chrome")
        for folder, _, files in os.walk(os.path.dirname(BUNDLED)):
            for name in files:
                path = os.path.join(folder, name)
                if name.endswith(".json") and os.path.abspath(path) != os.path.abspath(lists.SOURCES_FILE):
                    with open(path, encoding="utf-8") as f:
                        self.assertNotIn("Claude for Chrome", f.read(), name)

    def test_platform_declared_by_the_page(self):
        self.assertEqual(self.snapshot.match_platform("Cloudflare Workers")["id"], "cloudflare-browser-run")
        self.assertIsNone(self.snapshot.match_platform("MacIntel"))

    def test_ua_shape_hints_are_kept_apart_from_names(self):
        self.assertIsNone(self.snapshot.match_ua("Mozilla/5.0"))
        self.assertEqual([h["id"] for h in self.snapshot.ua_hints("Mozilla/5.0")], ["bare-mozilla-ua"])
        self.assertEqual(self.snapshot.ua_hints(HUMANS[0]), [])


class AddressesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = lists.Lists.load(BUNDLED)

    def test_published_agent_range_names_the_operator_and_what_it_verifies(self):
        found = self.snapshot.match_ip(first_address(self.snapshot, "openai-chatgpt-user"))
        self.assertEqual((found["range_id"], found["range_kind"], found["operator"]),
                         ("openai-chatgpt-user", "agent", "OpenAI"))
        self.assertIn("chatgpt-user", found["verifies"])

    def test_crawler_ranges_verify_their_bots(self):
        for range_id, list_id in [("google-common-crawlers", "googlebot"), ("bingbot", "bingbot"),
                                  ("anthropic-claude-agent", "claude-agent"), ("google-user-triggered-agents",
                                                                               "google-agent")]:
            with self.subTest(range_id=range_id):
                found = self.snapshot.match_ip(first_address(self.snapshot, range_id))
                self.assertEqual(found["range_id"], range_id)
                self.assertIn(list_id, found["verifies"])

    def test_relay_cdn_and_cloud_are_reported_apart(self):
        relay = self.snapshot.match_ip(first_address(self.snapshot, "icloud-private-relay"))
        cdn = self.snapshot.match_ip(first_address(self.snapshot, "cloudflare"))
        cloud = self.snapshot.match_ip(first_address(self.snapshot, "aws"))
        self.assertEqual((relay["relay"], relay["range"]), ("iCloud Private Relay", None))
        self.assertEqual((cdn["cdn"], cdn["cloud"]), ("Cloudflare", None))
        self.assertEqual((cloud["cloud"], cloud["relay"]), ("AWS", None))

    def test_unlisted_loopback_and_invalid_addresses(self):
        empty = self.snapshot.match_ip(TEST_NET)
        self.assertEqual((empty["range"], empty["cloud"], empty["cdn"], empty["relay"], empty["verifies"]),
                         (None, None, None, None, []))
        self.assertIsNone(self.snapshot.match_ip("127.0.0.1")["range"])
        for bad in ("not an address", "", None, "999.1.1.1"):
            self.assertIsNone(self.snapshot.match_ip(bad))

    def test_ipv4_mapped_ipv6_is_looked_up_as_ipv4(self):
        v4 = first_address(self.snapshot, "openai-gptbot")
        self.assertEqual(self.snapshot.match_ip("::ffff:" + v4), self.snapshot.match_ip(v4))
        self.assertEqual(self.snapshot.match_ip(v4)["range_id"], "openai-gptbot")

    def test_result_keeps_no_address(self):
        address = first_address(self.snapshot, "openai-chatgpt-user")
        self.assertNotIn(address, json.dumps(self.snapshot.match_ip(address)))

    def test_first_range_keeps_the_0_3_3_lookup_order(self):
        # published_range() of 0.3.3: the first range of any kind in the file's order, as (label, kind).
        self.assertEqual(self.snapshot.first_range(first_address(self.snapshot, "cloudflare")), ("Cloudflare", "cdn"))
        self.assertIsNone(self.snapshot.first_range(TEST_NET))


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = lists.Lists.load(BUNDLED)
        self.built = datetime.date.fromisoformat(self.snapshot.built)

    def test_age_against_the_limit(self):
        fresh = self.snapshot.status(max_age_days=30, today=self.built + datetime.timedelta(days=30))
        stale = self.snapshot.status(max_age_days=30, today=self.built + datetime.timedelta(days=31))
        self.assertEqual((fresh["age_days"], fresh["stale"]), (30, False))
        self.assertEqual((stale["age_days"], stale["stale"]), (31, True))
        self.assertEqual(stale["location"], "bundled")

    def test_status_lists_every_source_with_its_snapshot(self):
        sources = self.snapshot.status(max_age_days=30, today=self.built)["sources"]
        for name in ("botscent", "posthog", "ai-robots-txt"):
            self.assertRegex(sources[name]["commit"], "^[0-9a-f]{40}$")


class SnapshotChoiceTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, self.root)
        self.bundled_built = lists.Lists.load(BUNDLED).built

    def copy_bundled(self, built):
        target = os.path.join(self.root, built)
        os.makedirs(target)
        for name in lists.SNAPSHOT_FILES:
            with open(os.path.join(BUNDLED, name), encoding="utf-8") as f:
                data = json.load(f)
            data["built"] = built
            with open(os.path.join(target, name), "w", encoding="utf-8") as f:
                json.dump(data, f)
        return target

    def shifted(self, days):
        return str(datetime.date.fromisoformat(self.bundled_built) + datetime.timedelta(days=days))

    def test_a_newer_update_is_used(self):
        newer = self.copy_bundled(self.shifted(5))
        chosen = lists.Lists.load(BUNDLED, user_root=self.root)
        self.assertEqual((chosen.built, chosen.location), (self.shifted(5), newer))

    def test_an_older_update_loses_to_a_newer_release(self):
        self.copy_bundled(self.shifted(-5))
        self.assertEqual(lists.Lists.load(BUNDLED, user_root=self.root).location, "bundled")

    def test_a_broken_update_is_ignored(self):
        broken = self.copy_bundled(self.shifted(5))
        with open(os.path.join(broken, "names.json"), "w", encoding="utf-8") as f:
            f.write("{ not json")
        self.assertEqual(lists.Lists.load(BUNDLED, user_root=self.root).location, "bundled")

    def test_an_incomplete_update_is_ignored(self):
        partial = self.copy_bundled(self.shifted(5))
        os.remove(os.path.join(partial, "signers.json"))
        self.assertEqual(lists.Lists.load(BUNDLED, user_root=self.root).location, "bundled")


class NoNetworkTest(unittest.TestCase):
    def test_reading_and_matching_open_no_socket(self):
        def refuse(*args, **kwargs):
            raise AssertionError("the lists tried to use the network")

        with mock.patch.object(socket, "socket", refuse), mock.patch.object(socket, "create_connection", refuse), \
                mock.patch.object(socket, "getaddrinfo", refuse):
            snapshot = lists.Lists.load(BUNDLED, user_root=tempfile.gettempdir())
            for ua, *_ in A7:
                snapshot.match_ua(ua)
            snapshot.match_ip(TEST_NET)
            snapshot.signer("chatgpt.com")
            snapshot.status(max_age_days=30, today=datetime.date.fromisoformat(snapshot.built))


if __name__ == "__main__":
    unittest.main()
