"""GET /api/setup (agentcake/api/onboarding.py): the home page's ways to connect and its example preview.

    python3 -I -m unittest discover -s tests -p test_api_onboarding.py -v      (from the AgentCake folder)

The answer fits the contract. The sentence for a coding agent comes in English and Chinese, with this
installation's launcher and ~ for the home folder (the same words `agentcake sentence` prints in Chinese); the
commands hold placeholders only; the example sessions are made up and say so, and nothing about them is stored.
`recorded` counts the sessions the lists show at any time (a self-check, a prefetch or a copy of the site elsewhere is
not one), and of them the website's own: a session an earlier AgentCake's demo shop recorded is listed but doesn't say
the website is connected, so the home page keeps showing how to connect it until the website's first session.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from agentcake import config, paths  # noqa: E402
from agentcake.api import visits  # noqa: E402
from agentcake.wording import product, text  # noqa: E402

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

    def test_the_sentence_in_english_with_this_launcher(self):
        launcher = paths.tilde(paths.launcher())
        self.assertIn(f"`{launcher}`", self.body["sentence"])
        self.assertNotIn(os.path.expanduser("~") + os.sep, self.body["sentence"])
        self.assertEqual(self.body["sentence"], paths.tilde(text("site_sentence", launcher=paths.launcher())))

    def test_there_is_no_demo_shop_to_try(self):
        """A fresh AgentCake connects its owner's website; it has no demo shop and no task for it."""
        self.assertFalse({"demo_url", "demo_task"} & set(self.body))
        self.assertNotIn("/demo", json.dumps(self.body))

    def test_commands_hold_placeholders_never_this_installations_key(self):
        self.assertIn("<your-site-folder>", self.body["terminal"])
        self.assertIn("<your-site-key>", self.body["server"]["settings"])
        self.assertNotIn("ck_onboarding", json.dumps(self.body))

    def test_on_a_server_three_things_the_server_its_dns_record_and_its_settings(self):
        """The subdomain route: Docker Compose starts AgentCake and Caddy, an A record points cake.<the domain> at the
        server, and the settings name that address."""
        server = self.body["server"]
        self.assertEqual(sorted(server), ["dns", "install", "settings"])
        self.assertIn("docker compose up -d", server["install"].splitlines())
        self.assertIn("deploy/Caddyfile", server["install"])
        self.assertEqual([line.split(":")[0] for line in server["dns"].splitlines()], ["Type", "Name", "Value"])
        for setting in ("public_url https://cake.<your-domain>", "trust_lb true"):
            self.assertIn(f"{product()['command']} config set {setting}", server["settings"].splitlines())

    def test_the_example_is_made_up_and_says_so(self):
        self.assertTrue(all(row["id"].startswith("example-") for row in self.body["example"]["sessions"]))
        self.assertEqual(Client().get("/api/sessions").body["results"], [], "nothing stored")

    def test_nothing_is_recorded_yet(self):
        self.assertEqual(self.body["recorded"], {"sessions": 0, "site": 0, "agent": 0})

    def test_recorded_counts_the_sessions_the_lists_show_whenever_they_came(self):
        self.store(("human", {"verdict_class": "human", "origin": "demo"}),  # the demo shop of an earlier AgentCake
                   ("agent", {"verdict_class": "agent", "agent_row": "automated", "start_ms": T0 - A_YEAR_MS}),
                   ("selfcheck", {"verdict_class": "human", "is_test": 1}),
                   ("prefetch", {"verdict_class": "excluded"}),
                   ("copy", {"verdict_class": "agent", "agent_row": "ai", "origin": "other"}))
        answer = Client().get("/api/setup")
        self.assertEqual(contract_problems(answer.body, "setup"), [])
        self.assertEqual(answer.body["recorded"], {"sessions": 2, "site": 1, "agent": 1})

    def test_the_demo_shops_sessions_alone_dont_connect_the_website(self):
        """A visit to an earlier AgentCake's demo shop is listed, but only the website's own visits say it is connected."""
        self.store(("demo", {"verdict_class": "human", "origin": "demo"}))
        self.assertEqual(Client().get("/api/setup").body["recorded"], {"sessions": 1, "site": 0, "agent": 0})

    def store(self, *stored):
        """Writes (id, columns) sessions as collect and judging leave them, from the website unless columns say not."""
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


if __name__ == "__main__":
    unittest.main()
