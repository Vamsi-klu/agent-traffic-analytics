"""GET /api/setup (S5.1, agentcake/api/onboarding.py): the home page's ways to connect and its example preview.

    python3 -I -m unittest discover -s tests -p test_api_onboarding.py -v      (from the Agent Cake folder)

The answer fits the contract. The sentence for a coding agent comes in English and Chinese, with this
installation's launcher and ~ for the home folder (the same words `agentcake sentence` prints in Chinese); the
commands hold placeholders only; the example sessions are made up and say so, and nothing about them is stored.
`recorded` counts the sessions the lists show, from any source at any time (S5.2: the home page is the dashboard
from the first one on): a self-check, a prefetch or a copy of the site elsewhere is not one.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from agentcake import config, paths, site_setup  # noqa: E402
from agentcake.api import visits  # noqa: E402

T0 = 1_794_500_000_000
A_YEAR_MS = 365 * 24 * 3_600_000


class Setup(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_onboarding", disk_min_free_mb=0)
        answer = Client().get("/api/setup")
        self.assertEqual(answer.status, 200, answer.body)
        self.body = answer.body

    def test_it_answers_the_contract(self):
        self.assertEqual(contract_problems(self.body, "setup"), [])

    def test_the_sentence_in_both_languages_with_this_launcher(self):
        launcher = paths.tilde(paths.launcher())
        for lang in ("en", "zh"):
            self.assertIn(f"`{launcher} setup --print --site`", self.body["sentence"][lang])
            self.assertNotIn(os.path.expanduser("~") + os.sep, self.body["sentence"][lang])
        self.assertEqual(self.body["sentence"]["zh"], paths.tilde(site_setup.sentence_b()))

    def test_there_is_no_demo_shop_to_try(self):
        """D37: a fresh AgentCake connects its owner's website; it has no demo shop and no task for it."""
        self.assertFalse({"demo_url", "demo_task"} & set(self.body))
        self.assertNotIn("/demo", json.dumps(self.body))

    def test_commands_hold_placeholders_never_this_installations_key(self):
        self.assertIn("<your-site-folder>", self.body["terminal"])
        self.assertIn("<your-site-key>", self.body["server"])
        self.assertNotIn("ck_onboarding", json.dumps(self.body))

    def test_the_example_is_made_up_and_says_so(self):
        self.assertTrue(all(row["id"].startswith("example-") for row in self.body["example"]["sessions"]))
        self.assertEqual(Client().get("/api/sessions").body["results"], [], "nothing stored")

    def test_nothing_is_recorded_yet(self):
        self.assertEqual(self.body["recorded"], {"sessions": 0, "agent": 0})

    def test_recorded_counts_the_sessions_the_lists_show_whenever_they_came(self):
        stored = (("human", {"verdict_class": "human", "origin": "demo"}),  # the demo shop of an earlier AgentCake: shown
                  ("agent", {"verdict_class": "agent", "agent_row": "automated", "start_ms": T0 - A_YEAR_MS}),
                  ("selfcheck", {"verdict_class": "human", "is_test": 1}),
                  ("prefetch", {"verdict_class": "excluded"}),
                  ("copy", {"verdict_class": "agent", "agent_row": "ai", "origin": "other"}))
        con = visits.connect()
        try:
            for sid, columns in stored:
                row = {"id": sid, "start_ms": T0, "origin": "site", "is_test": 0, **columns}
                row["end_ms"] = row["start_ms"] + 1000
                con.execute(f"INSERT INTO sessions({', '.join(row)}) VALUES({', '.join('?' * len(row))})",
                            tuple(row.values()))
            con.commit()
        finally:
            con.close()
        answer = Client().get("/api/setup")
        self.assertEqual(contract_problems(answer.body, "setup"), [])
        self.assertEqual(answer.body["recorded"], {"sessions": 2, "agent": 1})


if __name__ == "__main__":
    unittest.main()
