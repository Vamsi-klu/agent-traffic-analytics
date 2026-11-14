"""The gate of `agentcake eval`: how measurements become pass, fail or no data, and the exit code.

    python3 -I -m unittest discover -s tests -p test_eval_gate.py -v

The first half feeds gate.judge() made-up measurements. The second runs the whole command (agentcake.cli) on
made-up data: threshold A7's ten User-Agents with their right answers pass, the same list with one wrong answer fails, and
a threshold whose data is not there has no data, which is not a pass; the network is refused throughout.
"""
import copy
import io
import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from agentcake import cli  # noqa: E402
from agentcake.evaluation import gate  # noqa: E402

THRESHOLDS = os.path.join(REPO, "eval", "thresholds.json")
NAMED = os.path.join(REPO, "eval", "named_user_agents.json")


def entry(**changes):
    base = {"id": "X1", "goal": "≥ 90%", "op": ">=", "value": 0.9, "unit": "share", "measure": "m", "statistic": "s",
            "data": {"gated": ["a", "b"], "reference": ["r"]}, "measured_by": gate.MEASURED_HERE}
    return dict(base, **changes)


def measurement(source, value, n, **extra):
    return {"threshold": "X1", "source": source, "value": value, "n": n, "what": "w", **extra}


def judge(thresholds_entry, measurements):
    (verdict,) = gate.judge({"thresholds": [thresholds_entry]}, measurements)
    return verdict


class Judge(unittest.TestCase):
    def test_every_gated_source_with_samples_must_pass(self):
        self.assertEqual(judge(entry(), [measurement("a", 0.95, 20), measurement("b", 0.91, 10)])["status"], "pass")
        self.assertEqual(judge(entry(), [measurement("a", 0.95, 20), measurement("b", 0.5, 10)])["status"], "fail")

    def test_a_source_without_samples_is_skipped_but_one_with_samples_is_needed(self):
        verdict = judge(entry(), [measurement("a", 0.95, 20), measurement("b", None, 0)])
        self.assertEqual((verdict["status"], verdict["missing"]), ("pass", ["b"]))
        self.assertEqual(judge(entry(), [measurement("a", None, 0)])["status"], "no_data")
        self.assertEqual(judge(entry(), [])["status"], "no_data")

    def test_reference_sources_are_never_judged(self):
        verdict = judge(entry(), [measurement("a", 0.95, 20), measurement("r", 0.1, 500)])
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual([m["source"] for m in verdict["reference"]], ["r"])

    def test_a_value_that_could_not_be_made_from_samples_fails(self):
        self.assertEqual(judge(entry(op="<=", value=3, unit="s"), [measurement("a", None, 12)])["status"], "fail")

    def test_upper_limits_and_lower_limits(self):
        self.assertEqual(judge(entry(op="<=", value=0.05), [measurement("a", 0.0, 11)])["status"], "pass")
        self.assertEqual(judge(entry(op="<=", value=0.05), [measurement("a", 1 / 11, 11)])["status"], "fail")
        self.assertEqual(judge(entry(op="<=", value=10, unit="points"), [measurement("a", 10.0, 5)])["status"], "pass")

    def test_a_sample_size_the_goal_asks_for(self):
        self.assertEqual(judge(entry(value=1.0, n=10), [measurement("a", 1.0, 9)])["status"], "fail")
        self.assertEqual(judge(entry(value=1.0, n=10), [measurement("a", 1.0, 10)])["status"], "pass")

    def test_every_group_needs_its_minimum(self):
        few = {"googlebot": {"n": 3, "right": 3}, "uptimerobot": {"n": 2, "right": 2}}
        enough = dict(few, uptimerobot={"n": 3, "right": 3})
        self.assertEqual(judge(entry(value=1.0, min_per_group=3), [measurement("a", 1.0, 5, groups=few)])["status"],
                         "fail")
        self.assertEqual(judge(entry(value=1.0, min_per_group=3), [measurement("a", 1.0, 6, groups=enough)])["status"],
                         "pass")

    def test_a_threshold_measured_elsewhere_is_listed_not_judged(self):
        verdict = judge(entry(measured_by="tests/test_webbotauth.py", data={"gated": [], "reference": []}), [])
        self.assertEqual(verdict["status"], "elsewhere")
        self.assertEqual(gate.exit_code([verdict, judge(entry(), [measurement("a", 1.0, 3)])]), 0)

    def test_exit_code_is_one_on_a_failure_or_on_no_data(self):
        passing = judge(entry(), [measurement("a", 1.0, 3)])
        self.assertEqual(gate.exit_code([passing]), 0)
        self.assertEqual(gate.exit_code([passing, judge(entry(), [])]), 1)
        self.assertEqual(gate.exit_code([passing, judge(entry(), [measurement("a", 0.0, 3)])]), 1)
        self.assertEqual(gate.exit_code([]), 1)

    def test_a_malformed_thresholds_file_is_refused_on_loading(self):
        folder = tempfile.mkdtemp(prefix="cake-eval-")
        for bad in ({"thresholds": []}, {"thresholds": [entry(op="~")]}, {"thresholds": [entry(unit="days")]},
                    {"thresholds": [entry(), entry()]}, {"thresholds": [{"id": "A1"}]},
                    {"thresholds": [entry(value="5%")]}, {"thresholds": [entry(data={"gated": "a"})]}):
            path = os.path.join(folder, "t.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(bad, f)
            with self.subTest(bad=bad), self.assertRaises(gate.ThresholdsError):
                gate.load(path)


def refuse(*args, **kwargs):
    raise AssertionError("agentcake eval tried to use the network")


class Command(unittest.TestCase):
    """The whole command on made-up data, hermetic: every data set named, none of this computer's own."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cake-eval-")
        with open(THRESHOLDS, encoding="utf-8") as f:
            real = gate.by_id(json.load(f))
        a5 = dict(real["A5"], measured_by="elsewhere", data={"gated": [], "reference": []})
        self.only_a7 = self.write("thresholds.json", {"thresholds": [copy.deepcopy(real["A7"]), a5]})
        self.with_a1 = self.write("thresholds_a1.json", {"thresholds": [copy.deepcopy(real["A7"]), a5,
                                                                         copy.deepcopy(real["A1"])]})
        self.sources = self.write("sources.json", {})
        os.environ["CAKE_HOME"] = os.path.join(self.folder, "home")

    def write(self, name, data):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return path

    def run_eval(self, *extra):
        missing = os.path.join(self.folder, "none")
        argv = ["eval", "--gate", "--sources", self.sources, "--lab", missing, "--lab-signals", missing,
                "--uploads", missing, "--truth-goal", missing, "--truth-manual", missing, *extra]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(socket, "socket", refuse), mock.patch.object(socket, "create_connection", refuse), \
                mock.patch.object(socket, "getaddrinfo", refuse), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_the_ten_right_answers_pass_the_gate(self):
        code, out, _ = self.run_eval("--thresholds", self.only_a7, "--named", NAMED)
        self.assertEqual(code, 0, out)
        self.assertIn("| A7 | 10/10 | pass |", out)

    def test_one_wrong_answer_fails_the_gate(self):
        with open(NAMED, encoding="utf-8") as f:
            cases = json.load(f)
        cases["cases"][3]["class"] = "agent"  # Googlebot is a Bot: this answer is wrong on purpose
        code, out, _ = self.run_eval("--thresholds", self.only_a7, "--named", self.write("named.json", cases))
        self.assertEqual(code, 1)
        self.assertIn("**FAIL**", out)

    def test_a_threshold_without_its_data_keeps_the_gate_shut(self):
        code, out, _ = self.run_eval("--thresholds", self.with_a1, "--named", NAMED)
        self.assertEqual(code, 1)
        # the goal column says the threshold in words
        self.assertIn("| A1 | ≤ 5% (with 10–13 samples, that is 0) | no data |", out)

    def test_without_gate_the_report_exits_zero(self):
        missing = os.path.join(self.folder, "none")
        with mock.patch.object(socket, "socket", refuse), redirect_stdout(io.StringIO()):
            code = cli.main(["eval", "--sources", self.sources, "--thresholds", self.with_a1, "--named", NAMED,
                             "--lab", missing, "--lab-signals", missing, "--uploads", missing,
                             "--truth-goal", missing])
        self.assertEqual(code, 0)

    def test_files_are_written_without_local_paths(self):
        out_dir = os.path.join(self.folder, "out")
        code, _, _ = self.run_eval("--thresholds", self.only_a7, "--named", NAMED, "--out", out_dir)
        self.assertEqual(code, 0)
        for name in ("eval.md", "eval.json"):
            with open(os.path.join(out_dir, name), encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn(self.folder, text, name)
            self.assertNotIn(os.path.expanduser("~"), text, name)
        with open(os.path.join(out_dir, "eval.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual([v["status"] for v in data["gate"]], ["pass", "elsewhere"])

    def test_usage_errors_exit_two(self):
        code, _, _ = self.run_eval("--thresholds", os.path.join(self.folder, "no-such-file.json"))
        self.assertEqual(code, 2)
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["eval", "--no-such-option"]), 2)
            self.assertEqual(cli.main(["eval", "--help"]), 0)


if __name__ == "__main__":
    unittest.main()
