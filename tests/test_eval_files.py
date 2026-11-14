"""The sample lists in eval/*.jsonl carry short hashes and counts only (plan S1.5, GOAL privacy rules).

Every line of a sample list may only use the fields listed for that list, and no value may look like an email address,
an IP address, a UUID (PostHog's session, distinct and person ids are UUIDs), a URL or a local path. A new sample list
needs its fields added, which is the moment to check it.

    python3 -I -m unittest discover -s tests -v
"""
import glob
import json
import os
import re
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(REPO, "eval")

ALLOWED_FIELDS = {
    # agentcake eval (S3.9): CAKE_HOME sessions with their answers; stretches are [from_ms, to_ms, who].
    "truth_goal.jsonl": {"h", "case", "group", "class", "row", "name", "verification", "crawler", "stretches",
                         "checked"},
}
NESTED_FIELDS = {}
SHORT_HASH = re.compile(r"^[0-9a-f]{12}$")
LOOKS_PRIVATE = {
    "email address": re.compile(r"[^\s@]+@[^\s@]+\.[a-z]{2,}", re.I),
    "IPv4 address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "IPv6 address": re.compile(r"\b[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){3,}\b", re.I),
    "UUID": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    "URL": re.compile(r"[a-z][a-z0-9+.-]*://", re.I),
    "local path": re.compile(r"(?:^|[\s\"'])(?:/Users/|/home/|~/|[A-Z]:\\)"),
}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def sample_lists():
    return sorted(glob.glob(os.path.join(EVAL, "*.jsonl")))


def readme_fields(section):
    """The field names of a README section's field table: the backticked names in each row's first cell."""
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    return {name for row in rows for name in re.findall(r"`([a-z_]+)`", row.split("|")[1])}


class SampleListChecks:
    """The checks of a set of sample lists: FIELDS {file name: allowed fields}, NESTED {field: allowed inner fields},
    README the document whose sections describe them. The lists checked are those of eval/ that FIELDS names."""
    FIELDS, NESTED, README = ALLOWED_FIELDS, NESTED_FIELDS, os.path.join(EVAL, "README.md")

    def lists(self):
        return [path for path in sample_lists() if os.path.basename(path) in self.FIELDS]

    def test_lines_use_only_allowed_fields(self):
        for path in self.lists():
            allowed = self.FIELDS[os.path.basename(path)]
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    row = json.loads(line)
                    self.assertLessEqual(set(row), allowed, f"{path}:{n}")
                    for key, inner in self.NESTED.items():
                        if key in row:
                            self.assertLessEqual(set(row[key]), inner, f"{path}:{n} {key}")

    def test_hashes_are_short_hashes(self):
        for path in self.lists():
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    row = json.loads(line)
                    self.assertRegex(row["h"], SHORT_HASH, f"{path}:{n}")
                    if "c" in row:
                        self.assertRegex(row["c"], SHORT_HASH, f"{path}:{n}")

    def test_hashes_are_unique_within_a_list(self):
        for path in self.lists():
            with open(path, encoding="utf-8") as f:
                hashes = [json.loads(line)["h"] for line in f]
            self.assertEqual(len(hashes), len(set(hashes)), path)

    def test_the_readme_documents_every_field(self):
        """README has a section per sample list whose table lists exactly the fields allowed here."""
        with open(self.README, encoding="utf-8") as f:
            readme = f.read()
        for name, allowed in self.FIELDS.items():
            self.assertTrue(f"\n## {name}" in readme, f"{self.README}: add a section for {name}")
            section = readme.split(f"\n## {name}", 1)[1].split("\n## ", 1)[0]
            self.assertEqual(readme_fields(section), allowed, name)

    def test_no_value_looks_like_personal_data(self):
        for path in self.lists():
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    for text in strings(json.loads(line)):
                        for what, pattern in LOOKS_PRIVATE.items():
                            self.assertIsNone(pattern.search(text), f"{path}:{n} has a {what}: {text!r}")


class EvalFilesTest(SampleListChecks, unittest.TestCase):
    """The list a user writes for `agentcake eval` (eval/README.md)."""


class PatternTest(unittest.TestCase):
    """The scan itself catches what it is meant to catch."""

    def test_patterns_catch_examples(self):
        examples = {"email address": "someone@example.com", "IPv4 address": "203.0.113.7",
                    "IPv6 address": "2001:db8::1", "UUID": "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b",
                    "URL": "https://example.com/x", "local path": "/Users/someone/data"}
        for what, text in examples.items():
            self.assertIsNotNone(LOOKS_PRIVATE[what].search(text), what)

    def test_patterns_leave_ordinary_values_alone(self):
        for text in ("probably-human", "posthog", "owner", "2026-11-12", "whole session", "a1b2c3d4e5f6"):
            for what, pattern in LOOKS_PRIVATE.items():
                self.assertIsNone(pattern.search(text), f"{what}: {text}")


if __name__ == "__main__":
    unittest.main()
