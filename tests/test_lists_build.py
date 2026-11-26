"""Building the lists from their sources, and `agentcake lists update`, without the internet.

    python3 -I -m unittest discover -s tests -v      (from the cake folder)

A small fixed world stands in for GitHub and the operators' servers: fetch() answers from a dict, so every test runs
offline. Addresses come from the documentation ranges (RFC 5737, RFC 3849). Checks: sources merge in order of
precedence; PostHog's file is read without running it; hints and exclusions stay apart; common words from
ai.robots.txt never become names; each address format is read and over-wide bot ranges refused; rolling key expiries
are not bundled as fixed ones; signed directory responses are kept; a changed licence or any failed fetch stops the
build and leaves the lists in use as they were.
"""
import contextlib, copy, datetime, io, json, os, shutil, socket, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from agentcake import cli  # noqa: E402
from agentcake.detect import lists, lists_build, lists_keys  # noqa: E402

NOW = datetime.datetime(2026, 11, 20, 12, 0, tzinfo=datetime.timezone.utc)
LIFETIME = 604800  # seconds: the "now plus seven days" a rolling directory answers with
SIGNER = "signer.example"

POSTHOG = r'''
from dataclasses import dataclass

@dataclass
class BotDefinition:
    name: str
    category: str
    traffic_type: str
    operator: str

BOT_DEFINITIONS: dict[str, BotDefinition] = {
    "Googlebot": BotDefinition("Googlebot", "search_crawler", "Bot", "Google"),
    "Claude/.*Electron": BotDefinition("Claude Desktop", "ai_assistant", "AI Agent", "Anthropic"),
    "UptimeRobot": BotDefinition("UptimeRobot", "monitoring", "Bot", "UptimeRobot"),
    "^Mozilla/5\\.0$": BotDefinition("Bare Mozilla UA", "headless_browser", "Automation", "Unknown"),
    "Amazon CloudFront": BotDefinition("Amazon CloudFront", "http_client", "Bot", "Amazon"),
}
'''
BOTSCENT = {
    "tokens": {"tokens": [{"token": "Googlebot", "name": "googlebot"}, {"token": "ChatGPT-User", "name": "chatgpt-user"},
                          {"token": "curl", "name": "curl", "match": "versioned"}]},
    "names": {"names": {
        "googlebot": {"display": "Googlebot", "vendor": "Google", "kind": "crawler"},
        "chatgpt-user": {"display": "ChatGPT-User", "vendor": "OpenAI", "kind": "fetcher"},
        "curl": {"display": "curl", "vendor": "curl project", "kind": "client"},
        "chatgpt": {"display": "ChatGPT", "vendor": "OpenAI", "kind": "computer-use-agent"},
        "grok-bot": {"display": "Grok Bot", "vendor": "Anysphere", "kind": "computer-use-agent"},
        "claude-chrome": {"display": "Claude for Chrome", "vendor": "Anthropic", "kind": "extension"},
        "cloudflare-browser-run": {"display": "Cloudflare Browser Run", "vendor": "Cloudflare", "kind": "automation"}}},
    "page": {"user_agent_prefixes": {"Kitesurf/": "cloudflare-browser-run"}, "user_agent_tokens": {},
             "platforms": {"Cloudflare Workers": "cloudflare-browser-run"}},
    "signers": {"signers": {SIGNER: "chatgpt"}},
    "keys": {"fetched_at": "2026-11-01T00:00:00Z",
             "directories": {SIGNER: [{"kty": "OKP", "crv": "Ed25519", "x": "rolling-key", "nbf": 1,
                                       "rolling_expiry_s": LIFETIME}]}},
}
ROBOTS = {
    "GPTBot": {"function": "Scrapes data to train OpenAI's products.", "operator": "[OpenAI](https://openai.com)"},
    "Claude-Agent": {"function": "AI Agents", "operator": "Unclear at this time."},
    "ExampleAgent": {"function": "AI Agents", "operator": "[Example Inc](https://example.com)"},
    "Spider": {"function": "AI Data Scrapers", "operator": "Unclear at this time."},
}
SAIL = '''schema = "draft-kelley-webbotauth-sail-00"
modified = 2026-11-01T00:00:00Z
[[prefix_sets]]
name = "browsing"
ipv4_prefixes = ["198.51.100.7"]
ipv6_prefixes = []
[[services]]
name = "Example-Agent"
prefix_sets = ["browsing"]
'''
RANGES = [
    {"id": "example-agent", "label": "Example agent", "kind": "agent", "operator": "Example", "format": "prefixes",
     "urls": ["https://ranges.example/agent.json"], "verifies": ["chatgpt-user"]},
    {"id": "example-sail", "label": "Example SAIL", "kind": "agent", "operator": "Example", "format": "sail",
     "service": "Example-Agent", "urls": ["https://ranges.example/sail"], "verifies": []},
    {"id": "example-relay", "label": "Example relay", "kind": "relay", "operator": "Example",
     "format": "csv-first-column", "urls": ["https://ranges.example/relay.csv"], "verifies": []},
    {"id": "example-cloud", "label": "Example cloud", "kind": "cloud", "operator": "Example", "format": "aws",
     "urls": ["https://ranges.example/cloud.json"], "verifies": []},
]
RANGE_BODIES = {
    "https://ranges.example/agent.json": {"creationTime": "2026-11-12T00:00:00", "prefixes": [
        {"ipv4Prefix": "192.0.2.0/25"}, {"ipv4Prefix": "192.0.2.128/25"}, {"ipv6Prefix": "2001:db8:1::/48"}]},
    "https://ranges.example/sail": SAIL,
    "https://ranges.example/relay.csv": "203.0.113.0/26,XX,XX-YY,Somewhere,\n203.0.113.64/26,XX,XX-YY,Somewhere,\n",
    "https://ranges.example/cloud.json": {"createDate": "2026-11-12-00-00-00",
                                          "prefixes": [{"ip_prefix": "198.51.100.0/24"}],
                                          "ipv6_prefixes": [{"ipv6_prefix": "2001:db8:2::/48"}]},
}
DIRECTORY_HEADERS = {"content-type": "application/http-message-signatures-directory+json",
                     "signature-input": 'sig1=("@authority";req);created=1;tag="http-message-signatures-directory"',
                     "signature": "sig1=:c2lnbmF0dXJl:", "server": "example"}


def recipe():
    with open(lists.SOURCES_FILE, encoding="utf-8") as f:
        sources = json.load(f)
    sources["ip_ranges"]["ranges"] = copy.deepcopy(RANGES)
    sources["signers"]["extra"] = {}
    sources["signers"]["signing"] = {}
    return sources


def world(sources, *, license_text="MIT License\n\"MIT Expat\" license\n", key_exp=None):
    """Every URL the build asks for, answered from the fixtures above."""
    answers, github = {}, sources["github"]
    files = {"botscent": {k: json.dumps(v) for k, v in BOTSCENT.items()},
             "posthog": {"bot_definitions": POSTHOG}, "ai-robots-txt": {"robots": json.dumps(ROBOTS)}}
    for name, spec in sources["repos"].items():
        commit = f"{len(answers):040x}"
        answers[github["commit_api"].format(repo=spec["repo"], ref=spec["ref"])] = json.dumps(
            {"sha": commit, "commit": {"committer": {"date": "2026-11-12T00:00:00Z"}}})
        answers[github["raw"].format(repo=spec["repo"], commit=commit, path=spec["license_file"])] = license_text
        for key, path in spec["files"].items():
            answers[github["raw"].format(repo=spec["repo"], commit=commit, path=path)] = files[name][key]
    for url, body in RANGE_BODIES.items():
        answers[url] = body if isinstance(body, str) else json.dumps(body)
    expiry = key_exp if key_exp is not None else int(NOW.timestamp()) + LIFETIME
    answers[sources["signers"]["directory"].format(host=SIGNER)] = json.dumps(
        {"keys": [{"kty": "OKP", "crv": "Ed25519", "x": "rolling-key", "nbf": 1, "exp": expiry, "use": "sig"},
                  {"kty": "RSA", "n": "not-ed25519"}]})
    return answers


def fetcher(answers):
    def fetch(url, accept=None):
        if url not in answers:
            raise lists_build.BuildError(f"{url}: unreachable")
        headers = DIRECTORY_HEADERS if "well-known" in url else {}
        return lists_build.Response(200, dict(headers), answers[url].encode("utf-8"))
    return fetch


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.sources = recipe()
        self.kinds = lists_build.read_recipe()[1]
        self.files = lists_build.build(self.sources, self.kinds, fetcher(world(self.sources)), None, NOW)
        self.names = {entry["id"]: entry for entry in self.files["names.json"]["names"]}

    def test_a_name_listed_twice_is_one_entry_with_both_sources(self):
        googlebot = self.names["googlebot"]
        self.assertEqual(googlebot["sources"], ["botscent", "posthog"])
        self.assertEqual([p["match"] for p in googlebot["patterns"]], ["token", "word"])

    def test_posthog_regex_gets_the_guard_and_kind_correction(self):
        desktop = self.names["claude-desktop"]
        self.assertEqual(desktop["kind"], "ai-desktop-app")
        self.assertEqual(desktop["patterns"][0]["text"], "(?<![A-Za-z0-9])(?:Claude/.*Electron)")

    def test_posthog_hints_and_exclusions_stay_apart(self):
        about = self.files["names.json"]["sources"]["posthog"]
        self.assertEqual((about["definitions"], about["named"], about["hints"]), (5, 3, 1))
        self.assertEqual(about["excluded"], ["Amazon CloudFront"])
        self.assertEqual(self.files["names.json"]["hints"][0]["id"], "bare-mozilla-ua")
        self.assertNotIn("amazon-cloudfront", self.names)

    def test_ai_robots_txt_adds_names_attaches_known_ones_and_skips_common_words(self):
        about = self.files["names.json"]["sources"]["ai-robots-txt"]
        self.assertEqual(self.names["exampleagent"]["kind"], "cloud-agent")
        self.assertEqual(self.names["exampleagent"]["operator"], "Example Inc")
        self.assertEqual(self.names["gptbot"]["kind"], "ai-crawler")
        self.assertIn("ai-robots-txt", self.names["claude-agent"]["sources"])
        self.assertIn("Spider", about["skipped"])
        self.assertNotIn("spider", self.names)

    def test_our_own_entry_keeps_the_rules_its_browser_matches_by_design(self):
        browser = self.names["antigravity-browser"]
        self.assertEqual((browser["kind"], browser["sources"], browser["by_design"]),
                         ("ai-desktop-app", ["cake"], ["env.auto.chromium-only-brand"]))
        self.assertNotIn("by_design", self.names["claude-agent"])

    def test_an_override_corrects_the_name_a_source_gives(self):
        claude = self.names["claude-chrome"]
        self.assertEqual((claude["name"], claude["kind"], claude["sources"]),
                         ("Claude in Chrome", "ai-browser-extension", ["botscent"]))

    def test_cake_additions_keep_their_evidence(self):
        grok = self.names["grok-bot"]
        self.assertEqual((grok["name"], grok["operator"], grok["evidence"], grok["sources"]),
                         ("Grok Bot", "Anysphere", "unverified", ["cake", "botscent"]))
        self.assertEqual(grok["patterns"], [{"match": "versioned", "text": "GrokAgent", "source": "cake"}])
        self.assertNotIn("grokagent", self.names)
        self.assertNotIn("evidence", self.names["claude-agent"])  # its operator documents it now
        self.assertEqual(self.names["claude-agent"]["sources"][0], "cake")

    def test_every_address_format_is_read_and_collapsed(self):
        ranges = {entry["id"]: entry for entry in self.files["ip_ranges.json"]["ranges"]}
        self.assertEqual(ranges["example-agent"]["v4"], ["192.0.2.0/24"])
        self.assertEqual(ranges["example-agent"]["published"], "2026-11-12T00:00:00")
        self.assertEqual(ranges["example-sail"]["v4"], ["198.51.100.7/32"])
        self.assertEqual(ranges["example-relay"]["v4"], ["203.0.113.0/25"])
        self.assertEqual(ranges["example-cloud"]["v6"], ["2001:db8:2::/48"])

    def test_signer_keys_and_signed_response_are_kept(self):
        keys = self.files["keys.json"]
        self.assertEqual(keys["directories"][SIGNER], [{"kty": "OKP", "crv": "Ed25519", "x": "rolling-key", "nbf": 1,
                                                        "rolling_expiry_s": LIFETIME}])
        response = keys["responses"][SIGNER]
        self.assertEqual(set(response["headers"]), {"content-type", "signature-input", "signature"})
        self.assertIn("rolling-key", response["body"])
        self.assertEqual(self.files["signers.json"]["signers"][SIGNER]["name"], "chatgpt")

    def test_a_signer_noted_as_no_longer_signing_keeps_its_keys_and_the_note(self):
        sources = recipe()
        stopped = {"state": "stopped", "since": "2026-10", "checked": "2026-11-13", "evidence": "unverified",
                   "note": "requests arrive unsigned"}
        sources["signers"]["signing"] = {"$comment": "why", SIGNER: stopped}
        files = lists_build.build(sources, self.kinds, fetcher(world(sources)), None, NOW)
        self.assertEqual(files["signers.json"]["signers"][SIGNER]["signing"], stopped)
        self.assertTrue(files["keys.json"]["directories"][SIGNER])
        self.assertNotIn("signing", self.files["signers.json"]["signers"][SIGNER])

    def test_a_signing_note_for_a_host_that_is_no_signer_stops_the_build(self):
        sources = recipe()
        sources["signers"]["signing"] = {"not-a-signer.example": {"state": "stopped"}}
        with self.assertRaises(lists_build.BuildError):
            lists_build.build(sources, self.kinds, fetcher(world(sources)), None, NOW)

    def test_the_snapshot_reads_back_and_matches(self):
        folder = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, folder)
        lists_build.write_files(self.files, folder)
        snapshot = lists.Lists.from_dir(folder, folder)
        self.assertEqual(snapshot.match_ua("Mozilla/5.0+(compatible; UptimeRobot/2.0)")["kind"], "monitoring")
        self.assertEqual(snapshot.match_ip("192.0.2.9")["verifies"], ["chatgpt-user"])
        self.assertEqual(snapshot.match_platform("Cloudflare Workers")["id"], "cloudflare-browser-run")


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self.sources, self.kinds = recipe(), lists_build.read_recipe()[1]

    def build(self, answers):
        return lists_build.build(self.sources, self.kinds, fetcher(answers), None, NOW)

    def test_posthog_file_is_read_without_running_it(self):
        marker = os.path.join(tempfile.mkdtemp(prefix="cake-lists-"), "ran")
        self.addCleanup(shutil.rmtree, os.path.dirname(marker))
        hostile = POSTHOG.replace('"UptimeRobot": BotDefinition(',
                                  f'"UptimeRobot": open({marker!r}, "w") or BotDefinition(')
        answers = world(self.sources)
        answers.update({url: hostile for url, body in answers.items() if body == POSTHOG})
        with self.assertRaises(lists_build.BuildError):
            self.build(answers)
        self.assertFalse(os.path.exists(marker))

    def test_a_changed_licence_stops_the_build(self):
        with self.assertRaisesRegex(lists_build.BuildError, "no longer says"):
            self.build(world(self.sources, license_text="All rights reserved"))

    def test_a_bot_range_wider_than_the_floor_is_refused(self):
        answers = world(self.sources)
        answers["https://ranges.example/agent.json"] = json.dumps({"prefixes": [{"ipv4Prefix": "10.0.0.0/8"}]})
        with self.assertRaisesRegex(lists_build.BuildError, "wider than"):
            self.build(answers)

    def test_a_file_under_ee_is_refused(self):
        self.sources["repos"]["posthog"]["files"]["bot_definitions"] = "ee/bot_definitions.py"
        with self.assertRaisesRegex(lists_build.BuildError, "another licence"):
            self.build(world(self.sources))


class RollingExpiryTest(unittest.TestCase):
    NOW_S = 2_000_000_000
    TOLERANCE = 600

    def roll(self, fresh, previous, previous_fetched=None):
        return lists_keys.roll_expiry(fresh, previous, previous_fetched, self.NOW_S, self.TOLERANCE)

    def test_a_rolling_key_stays_rolling(self):
        fresh = [{"x": "k", "nbf": 1, "exp": self.NOW_S + LIFETIME}]
        self.assertEqual(self.roll(fresh, [{"x": "k", "nbf": 1, "rolling_expiry_s": LIFETIME}]),
                         [{"x": "k", "nbf": 1, "rolling_expiry_s": LIFETIME}])

    def test_an_expiry_that_moved_with_time_starts_rolling(self):
        earlier = self.NOW_S - 86400
        fresh = [{"x": "k", "exp": self.NOW_S + LIFETIME}]
        self.assertEqual(self.roll(fresh, [{"x": "k", "exp": earlier + LIFETIME}], previous_fetched=earlier),
                         [{"x": "k", "rolling_expiry_s": LIFETIME}])

    def test_a_fixed_expiry_is_kept(self):
        fresh = [{"x": "k", "exp": self.NOW_S + 30 * 86400}]
        self.assertEqual(self.roll(fresh, [{"x": "k", "exp": self.NOW_S + 30 * 86400}], self.NOW_S - 86400), fresh)


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, self.root)
        self.sources = recipe()
        self.patch = mock.patch.object(lists_build, "read_recipe",
                                       return_value=(self.sources, lists_build.read_recipe()[1]))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.later = datetime.datetime.combine(
            datetime.date.fromisoformat(lists.Lists.load().built) + datetime.timedelta(days=1),
            datetime.time(12), datetime.timezone.utc)

    def test_update_writes_a_dated_snapshot_that_is_then_used(self):
        folder = lists_build.update(fetcher(world(self.sources)), self.later, self.root)
        self.assertEqual(os.path.basename(folder), self.later.date().isoformat())
        self.assertLessEqual(set(lists.SNAPSHOT_FILES), set(os.listdir(folder)))  # with the licences: test_lists_licences
        self.assertEqual(lists.Lists.load(user_root=self.root).location, folder)

    def test_a_failed_fetch_changes_nothing(self):
        answers = world(self.sources)
        del answers["https://ranges.example/relay.csv"]
        with self.assertRaisesRegex(lists_build.BuildError, "unreachable"):
            lists_build.update(fetcher(answers), self.later, self.root)
        self.assertEqual(os.listdir(self.root), [])
        self.assertEqual(lists.Lists.load(user_root=self.root).location, "bundled")

    def test_a_second_update_on_the_same_day_replaces_the_first(self):
        lists_build.update(fetcher(world(self.sources)), self.later, self.root)
        folder = lists_build.update(fetcher(world(self.sources)), self.later, self.root)
        self.assertEqual(os.listdir(self.root), [os.path.basename(folder)])


class ListsCommandTest(unittest.TestCase):
    """`agentcake lists` and `agentcake lists update`, run in-process in a scratch CAKE_HOME."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home)
        environment = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        environment.start()
        self.addCleanup(environment.stop)
        lists.reload()
        self.addCleanup(lists.reload)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_update_without_network_fails_and_the_lists_in_use_stay(self):
        def offline(*args, **kwargs):
            raise OSError("network is down")

        with mock.patch.object(socket, "socket", offline), mock.patch.object(socket, "create_connection", offline), \
                mock.patch.object(socket, "getaddrinfo", offline):
            code, _, err = self.run_cli("lists", "update")
        self.assertEqual(code, 1)
        self.assertIn("lists not updated", err)
        self.assertFalse(os.path.exists(lists.user_root()))
        code, out, _ = self.run_cli("lists")
        self.assertEqual((code, json.loads(out)["location"]), (0, "bundled"))

    def test_update_writes_under_cake_home_and_is_used_at_once(self):
        sources = recipe()
        with mock.patch.object(lists_build, "read_recipe", return_value=(sources, lists_build.read_recipe()[1])), \
                mock.patch.object(lists_build, "http_fetch", return_value=fetcher(world(sources))):
            code, out, _ = self.run_cli("lists", "update")
        self.assertEqual(code, 0)
        status = json.loads(out)
        self.assertTrue(status["location"].startswith(lists.user_root()))
        self.assertFalse(status["stale"])


class WriteFilesTest(unittest.TestCase):
    def test_a_file_that_cannot_be_written_leaves_every_file_as_it_was(self):
        folder = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, folder)
        lists_build.write_files({"a.json": {"v": 1}, "b.json": {"v": 1}}, folder)
        with self.assertRaises(TypeError):
            lists_build.write_files({"a.json": {"v": 2}, "b.json": {"v": object()}}, folder)
        for name in ("a.json", "b.json"):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"v": 1})
        self.assertEqual(sorted(os.listdir(folder)), ["a.json", "b.json"])


if __name__ == "__main__":
    unittest.main()
