"""How eval/thresholds.json counts the recorder's agent and hand-off recordings (threshold A2, A3-A5), and how the
recordings we ran ourselves are counted beside them without being mixed in.

    python3 -I -m unittest discover -s tests -v

The tests that read recordings are kept with them, outside the published repository.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from agentcake import datafiles  # noqa: E402
from agentcake.evaluation import bots, gate, measures  # noqa: E402

SETTINGS = datafiles.load("data/eval.json")
THRESHOLDS = os.path.join(REPO, "eval", "thresholds.json")
LIMIT_S = 3
SELF_COLLECTED = ["cc-playwright-mcp", "cc-devtools-mcp", "cic-mcp", "fake-patchright-ghost", "fake-camoufox",
                  "fake-pw-humanlike", "fake-pw-builtin", "fake-pptr-ghost-humanize", "fake-pw-humancursor",
                  "fake-selenium-humancursor", "fake-pw-fingerprint", "fake-pptr-setua"]


class GateData(unittest.TestCase):
    """eval/thresholds.json counts the recorded data sets as decided on 2026-11-13: A2 judges Claude in
    Chrome, A3-A5 the real hand-offs beside the splices, every other local AI browser a line of its own that is never
    judged (the local AI browsers hold their own expectations). No threshold value changed."""

    A2_LABELS = ["cic-panel", "cic-mcp"]
    OTHER_LOCAL = ["comet", "atlas", "gemini-chrome", "dia", "codex", "agy", "codex-cu", "neon", "edge-copilot",
                   "chatgpt-ext", "manus-ext", "genspark"]

    def setUp(self):
        self.entries = gate.by_id(gate.load(THRESHOLDS))

    def test_a2_judges_claude_in_chrome_only(self):
        self.assertEqual(SETTINGS["recorded"]["a2_labels"], self.A2_LABELS)
        data = self.entries["A2"]["data"]
        self.assertIn("recorded", data["gated"])
        for label in self.OTHER_LOCAL:
            self.assertIn(f"recorded/{label}", data["reference"], label)
            self.assertNotIn(f"recorded/{label}", data["gated"], label)
        for label in self.A2_LABELS:
            self.assertNotIn(f"recorded/{label}", data["reference"] + data["gated"], label)

    def test_a3_to_a5_judge_the_real_hand_offs_beside_the_splices(self):
        for threshold in ("A3", "A4", "A5"):
            data = self.entries[threshold]["data"]
            self.assertIn("recorded_handoffs", data["gated"], threshold)
            self.assertIn("recording_splices", data["gated"], threshold)
            self.assertNotIn("recorded_handoffs", data["reference"], threshold)

    def test_a5_is_a_median_over_the_sessions_judged_human_plus_agent_and_still_at_most_3_seconds(self):
        a5 = self.entries["A5"]
        self.assertEqual((a5["goal"], a5["op"], a5["value"], a5["unit"]), ("≤ 3 seconds", "<=", 3, "s"))
        self.assertTrue(a5["statistic"].startswith("median over the true hand-offs in the sessions judged Human + "
                                                   "agent"), a5["statistic"])

    def test_a8_prints_the_recordings(self):
        self.assertIn("recorded", self.entries["A8"]["data"]["reference"])

    def test_our_own_runs_are_printed_per_label_and_only_claude_in_chrome_is_judged(self):
        data = self.entries["A2"]["data"]
        for label in SELF_COLLECTED:
            judged, printed = (data["gated"], data["reference"]) if label in self.A2_LABELS else \
                (data["reference"], data["gated"])
            self.assertIn(f"selfcollect/{label}", judged, label)
            self.assertNotIn(f"selfcollect/{label}", printed, label)
            self.assertNotIn(f"recorded/{label}", data["reference"] + data["gated"], label)
        self.assertIn("selfcollect/cic-mcp", data["gated"])


def row(label, judged):
    """A judged session of an agent, with what the measures read of sessions.row()'s rows."""
    return {"truth": {"class": "agent"}, "group": label, "class": judged, "too_little": judged == "too_little_data",
            "layers": {}}


class SelfCollected(unittest.TestCase):
    """The recordings we ran ourselves are a data set of their own: one A2 line per label beside people's
    recordings, which stay as they were, and the scoreboard counts them as agents of their product."""

    @staticmethod
    def a2(rows):
        results = {"rows": rows, "takeovers": {}, "bots": {"t22": bots.t22_table([], SETTINGS)}, "store_sessions": []}
        return {m["source"]: m for m in measures.collect(results, SETTINGS, LIMIT_S) if m["threshold"] == "A2"}

    def test_each_label_gets_its_own_line(self):
        lines = self.a2({"selfcollect": [row("cc-playwright-mcp", "agent"), row("cc-playwright-mcp", "human"),
                                         row("fake-camoufox", "agent"), row("fake-camoufox", "too_little_data")]})
        mcp, camoufox = lines["selfcollect/cc-playwright-mcp"], lines["selfcollect/fake-camoufox"]
        self.assertEqual((mcp["count"], mcp["n"]), (1, 2))
        self.assertEqual((camoufox["count"], camoufox["n"], camoufox["details"]["not_judged"]), (1, 1, 1))

    def test_people_s_recordings_are_counted_as_before(self):
        lines = self.a2({"selfcollect": [row("cc-devtools-mcp", "agent")], "recorded": [row("cic-mcp", "human")]})
        self.assertEqual((lines["recorded"]["count"], lines["recorded"]["n"]), (0, 1))
        self.assertEqual(lines["recorded"]["details"]["by_label"], {"cic-mcp": {"n": 1, "agent_or_mixed": 0}})
        self.assertNotIn("recorded/cc-devtools-mcp", lines)

    def test_a2_judges_our_claude_in_chrome_runs_and_prints_the_rest(self):
        measured = list(self.a2({"selfcollect": [row("cic-mcp", "agent"), row("cic-mcp", "mixed"),
                                                 row("cc-devtools-mcp", "human")]}).values())
        verdict = next(v for v in gate.judge(gate.load(THRESHOLDS), measured) if v["id"] == "A2")
        gated = {m["source"]: m for m in verdict["gated"]}
        self.assertEqual((gated["selfcollect/cic-mcp"]["count"], gated["selfcollect/cic-mcp"]["n"]), (2, 2))
        printed = {m["source"] for m in verdict["reference"]}
        self.assertIn("selfcollect/cc-devtools-mcp", printed)
        self.assertNotIn("selfcollect/cic-mcp", printed)

    def test_the_scoreboard_counts_them_as_agents_of_their_product(self):
        board = SETTINGS["scoreboard"]
        self.assertIn("selfcollect", board["agent_sources"])
        self.assertNotIn("selfcollect", board["human_sources"])
        self.assertEqual(board["recording"]["selfcollect"], "raw")
        self.assertEqual(board["products"]["fake-pw-humanlike"], "playwright-humanlike")
        # calibration reads the real products of our own runs, never the automation we made to look human (11/13)
        self.assertIn("selfcollect", SETTINGS["calibration"]["sources"])
        self.assertEqual(sorted(SETTINGS["calibration"]["left_out"]["selfcollect"]),
                         ["fake-camoufox", "fake-patchright-ghost", "fake-pptr-ghost-humanize", "fake-pptr-setua",
                          "fake-pw-builtin", "fake-pw-fingerprint", "fake-pw-humancursor", "fake-pw-humanlike",
                          "fake-selenium-humancursor"])


if __name__ == "__main__":
    unittest.main()
