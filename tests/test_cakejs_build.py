"""cake.js is built from agentcake/static/src/ by agentcake/build_js.py (plan step S1.3).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The committed agentcake/static/cake.js must be exactly what build_js.py makes now (it never goes stale); every value
of agentcake/data/cakejs.json reaches the script; our own sources write no number other than 0, 1 and -1 (protocol
constants say so on their line); the bundled third-party parts are the recorded files and carry their licences;
cake.js has no way to send anything except its own fetch to cake.
"""
import copy
import hashlib
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake import build_js  # noqa: E402  (the repository root is put on sys.path first)

PACKAGE = os.path.join(ROOT, "agentcake")
CONFIG_PATH = os.path.join(PACKAGE, "data", "cakejs.json")
LINE_LIMIT_DEFAULT = 400  # tools/limits.json (plan step S1.2) is the authority once it exists
ALLOWED_NUMBERS = {"0", "1"}  # -1 is the unary minus applied to 1


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def our_parts(config):
    """The parts we wrote (the vendored ones say which licence they come under)."""
    return [p for p in config["build"]["parts"] if "licence" not in p]


def embedded_config(script):
    match = re.search(r"^  var CFG = (\{.*\})$", script, re.M)
    return json.loads(match.group(1)) if match else None


def code_without_comments_and_strings(source):
    """JavaScript source with comments, string literals and regular expression literals blanked (lines kept)."""
    out, i, n = [], 0, len(source)
    last_significant = ""
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            j = source.find("\n", i)
            j = n if j < 0 else j
            protocol = "// protocol:" in source[i:j]
            out.append(" protocol-constant" if protocol else "")
            i = j
            continue
        if source.startswith("/*", i):
            j = source.index("*/", i) + 2
            out.append("\n" * source.count("\n", i, j))
            i = j
            continue
        if ch in "'\"`":
            j = i + 1
            while j < n and source[j] != ch:
                j += 2 if source[j] == "\\" else 1
            out.append(ch + ch)
            i = j + 1
            last_significant = ch
            continue
        if ch == "/" and (last_significant in "(,=:[!&|?{};" or last_significant == ""):
            j, in_class = i + 1, False
            while j < n and (source[j] != "/" or in_class):
                if source[j] == "\\":
                    j += 1
                elif source[j] == "[":
                    in_class = True
                elif source[j] == "]":
                    in_class = False
                j += 1
            j += 1
            while j < n and source[j].isalpha():
                j += 1
            out.append("/r/")
            i = j
            last_significant = "/"
            continue
        out.append(ch)
        if not ch.isspace():
            last_significant = ch
        i += 1
    return "".join(out)


def hardcoded_numbers(source):
    """(line number, literal) for every number other than 0 and 1 outside comments, strings and regexes."""
    found = []
    for number, line in enumerate(code_without_comments_and_strings(source).split("\n"), 1):
        if "protocol-constant" in line:
            continue
        for literal in re.findall(r"(?<![\w.$])(\d+(?:\.\d+)?(?:e\d+)?|\.\d+)(?![\w$])", line):
            if literal not in ALLOWED_NUMBERS:
                found.append((number, literal))
    return found


class Build(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.script = build_js.build(self.config)

    def test_committed_script_is_what_the_build_makes_now(self):
        committed = read(os.path.join(PACKAGE, self.config["build"]["out"]))
        self.assertEqual(committed, self.script, "cake.js is stale: run python3 -I agentcake/build_js.py")

    def expected_config(self, config):
        expected = dict(config["script"])
        for name, source in config["build"]["data"].items():
            with open(os.path.join(PACKAGE, source["file"]), encoding="utf-8") as f:
                expected[name] = json.load(f)[source["key"]]
        return expected

    def test_every_value_of_cakejs_json_and_privacy_json_reaches_the_script(self):
        self.assertIn("privacy", self.config["build"]["data"])
        self.assertEqual(embedded_config(self.script), self.expected_config(self.config))

    def test_a_changed_value_changes_the_script(self):
        changed = copy.deepcopy(self.config)
        changed["script"]["batch"]["max_bytes"] += 1
        changed["script"]["rrweb"]["sampling"]["mousemove"] += 1
        self.assertEqual(embedded_config(build_js.build(changed)), self.expected_config(changed))

    def test_the_build_is_reproducible(self):
        self.assertEqual(build_js.build(self.config), self.script)

    def test_every_source_file_is_part_of_the_build(self):
        listed = {os.path.normpath(os.path.join(PACKAGE, p["file"])) for p in self.config["build"]["parts"]}
        src = os.path.join(PACKAGE, "static", "src")
        on_disk = {os.path.join(src, f) for f in os.listdir(src) if f.endswith(".js")}
        self.assertEqual(on_disk - listed, set())

    def test_our_sources_write_no_numbers(self):
        for part in our_parts(self.config):
            with self.subTest(part=part["file"]):
                self.assertEqual(hardcoded_numbers(read(os.path.join(PACKAGE, part["file"]))), [])

    def test_the_number_check_catches_a_magic_number(self):
        self.assertEqual(hardcoded_numbers("var wait = 2000\nvar re = /[0-9]{3}/\n'99'\n// 77\n"), [(1, "2000")])
        self.assertEqual(hardcoded_numbers("var FULL = 2 // protocol: rrweb EventType\n"), [])

    def test_our_sources_stay_under_the_line_limit(self):
        limits_path = os.path.join(ROOT, "tools", "limits.json")
        limit = LINE_LIMIT_DEFAULT
        if os.path.isfile(limits_path):
            limit = json.loads(read(limits_path)).get("max_lines", LINE_LIMIT_DEFAULT)
        for part in our_parts(self.config):
            with self.subTest(part=part["file"]):
                self.assertLessEqual(read(os.path.join(PACKAGE, part["file"])).count("\n"), limit)

    def test_vendored_files_are_the_recorded_ones(self):
        for part in self.config["build"]["parts"]:
            if "sha256" in part:
                with self.subTest(part=part["file"]):
                    with open(os.path.join(PACKAGE, part["file"]), "rb") as f:
                        self.assertEqual(hashlib.sha256(f.read()).hexdigest(), part["sha256"])

    def test_vendored_licences_are_bundled(self):
        for part in self.config["build"]["parts"]:
            if "licence" in part:
                with self.subTest(part=part["file"]):
                    self.assertIn(read(os.path.join(PACKAGE, part["licence"])).strip(), self.script)

    def test_cake_js_sends_only_through_its_own_fetch(self):
        for forbidden in ("XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "importScripts", "openfpcdn"):
            self.assertNotIn(forbidden, self.script)
        self.assertEqual(self.script.count("fetch("), 1)
        self.assertIn("fetch(", read(os.path.join(PACKAGE, "static", "src", "transport.js")))

    def test_runtime_values_are_filled_in_when_served(self):
        served = build_js.with_runtime(self.script, {"site_key": "k-test", "hook_dom": True})
        self.assertIn('{"hook_dom":true,"site_key":"k-test"}', served)
        again = build_js.with_runtime(served, {"site_key": "other"})
        self.assertIn('{"site_key":"other"}', again)
        self.assertNotIn("k-test", again)
        self.assertEqual(len(again) - len('{"site_key":"other"}'), len(self.script) - len("{}"))


if __name__ == "__main__":
    unittest.main()
