"""The held-out site data set of `agentcake eval`: a copy of a website's data folder, read through its list.

    python3 -I -m unittest discover -s tests -p test_eval_site.py -v

A made-up data folder (uploads through collect, as tests/test_evidence.py makes them) stands in for a website's copy.
Its list names one of its two sessions by short hash: only that one is read, with its line's answer, group and site.
Without a data folder nothing is read and the report says what to give. The site's rows are counted on their own:
the tables with and without them differ only in the site's rows and the scoreboard's held-out cells, so no pooled
rate, precision, site count, calibration, held-out threshold or gate measurement reads them.
"""
import gc
import http.client
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentcake import collect, config, datafiles, eval as eval_command, store  # noqa: E402
from agentcake.evaluation import datasets, measures, report, sources, tables  # noqa: E402
from agentcake.evaluation import store as labelled_store  # noqa: E402
from agentcake.responses import Request  # noqa: E402

SETTINGS = datafiles.load("data/eval.json")
KEY = "ck_site_test"
LISTED, UNLISTED = "5a1e9d3c2b4f6a7e8d9c0b1a2f3e4d5c", "6b2f0e4d3c5a7b8f9e0d1c2b3a4f5e6d"
PV = "c3" * 16
T0 = 1_794_600_000_000
S = 1000
LIMIT_S = 3
CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
LINE = {"site": "shop.example", "group": "owner", "class": "human", "checked": "2026-11-16"}


def visit(sid, at_ms):
    """A page view's first batch: its page record, an environment record and a few pointer moves."""
    signals = [{"t": at_ms, "ty": "page", "n": 1, "nav": "navigate", "prerendering": False, "vis": "visible"},
               {"t": at_ms + 5, "ty": "env", "env": {"userAgent": CHROME, "platform": "MacIntel",
                                                     "anyPointer": ["fine"], "maxTouchPoints": 0}}]
    raw = [{"t": at_ms + 10 * k, "ty": "mousemove", "cx": k, "cy": k, "tr": 1, "vs": 1} for k in range(3)]
    return {"v": 1, "k": KEY, "s": sid, "pv": PV, "seq": 0, "t": at_ms, "u": "https://shop.example/", "why": "start",
            "ua": CHROME, "wd": False, "e": [], "r": raw, "x": signals}


def post(body, at_ms):
    message = http.client.HTTPMessage()
    message["User-Agent"], message["Accept-Language"] = CHROME, "en-US"
    with mock.patch.object(collect, "clock_ms", return_value=at_ms):
        answer = collect.from_local(Request("/collect", {}, message, json.dumps(body).encode()))
    if answer.status != 204:
        raise AssertionError(answer.body)


def short(sid):
    return datasets.short_hash(SETTINGS["short_hash"]["goal"], sid, SETTINGS)


class SiteData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        before = os.environ.get("CAKE_HOME")
        cls.home = tempfile.mkdtemp(prefix="cake-site-")
        cls.addClassCleanup(shutil.rmtree, cls.home, ignore_errors=True)
        cls.addClassCleanup(lambda: os.environ.pop("CAKE_HOME", None) if before is None
                            else os.environ.__setitem__("CAKE_HOME", before))
        os.environ["CAKE_HOME"] = cls.home
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        store.db().close()
        post(visit(LISTED, T0), T0)
        post(visit(UNLISTED, T0 + 60 * S), T0 + 60 * S)
        cls.truth = os.path.join(cls.home, "site_list.jsonl")
        with open(cls.truth, "w", encoding="utf-8") as f:
            f.write(json.dumps(dict(LINE, h=short(LISTED))) + "\n")

    def load(self, **options):
        return sources.load(sources.locate(options, SETTINGS), SETTINGS)

    def test_only_the_listed_session_is_read_with_its_lines_answer(self):
        (item,) = self.load(site_home=self.home, truth_site=self.truth)["site"]
        self.assertEqual(item["h"], short(LISTED))
        self.assertEqual((item["truth"]["class"], item["truth"]["group"], item["truth"]["site"]),
                         ("human", "owner", "shop.example"))

    def test_without_a_data_folder_nothing_is_read_and_the_report_says_what_to_give(self):
        data = self.load(truth_site=self.truth)
        self.assertEqual(data["site"], [])
        self.assertIn("--site-home", data["notes"]["site"])

    def test_a_copy_is_judged_as_its_config_says_and_the_readme_says_to_copy_it(self):
        """The evidence's mode comes from the copy's config.json: without it a server's sessions are judged as if
        recorded on a computer, with no address-range or signature checks. So eval/README.md names config.json."""
        modes = {}
        for name, settings in (("without", None), ("server", {"public_listen": "0.0.0.0:8080"})):
            copy = os.path.join(tempfile.mkdtemp(prefix="cake-site-copy-"), "home")
            self.addCleanup(shutil.rmtree, os.path.dirname(copy), True)
            shutil.copytree(self.home, copy)
            os.remove(os.path.join(copy, "config.json"))
            if settings:
                with open(os.path.join(copy, "config.json"), "w", encoding="utf-8") as f:
                    json.dump(settings, f)
            (item,) = self.load(site_home=copy, truth_site=self.truth)["site"]
            modes[name] = item["evidence"]["mode"]
        self.assertEqual(modes, {"without": "local", "server": "server"})
        with open(os.path.join(ROOT, "eval", "README.md"), encoding="utf-8") as f:
            section = f.read().split("## A website's own labelled sessions", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`config.json`", section)

    def test_an_empty_list_reads_nothing_and_leaves_no_connection_open(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            self.assertEqual(labelled_store.labelled([], SETTINGS, self.home), [])
            gc.collect()
        self.assertEqual([str(w.message) for w in caught if issubclass(w.category, ResourceWarning)], [])

    def test_a_folder_without_its_list_reads_nothing(self):
        data = self.load(site_home=self.home, truth_site=os.path.join(self.home, "none.jsonl"))
        self.assertEqual(data["site"], [])
        self.assertIn("--truth-site", data["notes"]["site"])

    def test_the_site_is_counted_on_its_own(self):
        """With and without the site's rows, every table but the site's own rows and held-out cells is the same."""
        data = self.load(site_home=self.home, truth_site=self.truth)
        with_site = tables.build(data, SETTINGS, LIMIT_S, with_logistic=False)
        without = tables.build(dict(data, site=[]), SETTINGS, LIMIT_S, with_logistic=False)
        self.assertEqual([r["id"] for r in with_site["rows"]["site"]], [short(LISTED)])
        self.assertEqual(with_site["scoreboard"]["held_out"]["site"]["humans"][0]["sessions"], 1)
        self.assertEqual(without["scoreboard"]["held_out"], {})
        for key in ("calibration", "heldout", "layers", "humans", "bots", "takeovers", "store_sessions"):
            self.assertEqual(json.dumps(with_site[key], sort_keys=True, default=str),
                             json.dumps(without[key], sort_keys=True, default=str), key)
        board = {k: v for k, v in with_site["scoreboard"].items() if k != "held_out"}
        self.assertEqual(board, {k: v for k, v in without["scoreboard"].items() if k != "held_out"})
        self.assertEqual(measures.collect(with_site, SETTINGS, LIMIT_S), measures.collect(without, SETTINGS, LIMIT_S))

    def test_the_report_prints_the_held_out_cells(self):
        data = self.load(site_home=self.home, truth_site=self.truth)
        results = tables.build(data, SETTINGS, LIMIT_S, with_logistic=False)
        text = report.markdown(results, [], sources.locate({}, SETTINGS), data["notes"], LIMIT_S)
        self.assertIn("| site / owner | human | 1 |", text)


class Options(unittest.TestCase):
    def test_the_command_line_names_the_site_and_its_list(self):
        args = eval_command.parse(["--site-home", "copy", "--truth-site", "list.jsonl"])
        self.assertEqual((args.site_home, args.truth_site), ("copy", "list.jsonl"))


if __name__ == "__main__":
    unittest.main()
