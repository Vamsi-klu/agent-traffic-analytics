"""agentcake/api/answers.py: who may ask /api, JSON bodies, and the error body every refusal carries.

    python3 -I -m unittest discover -s tests -p test_api_answers.py -v      (from the Agent Cake folder)

Only this computer's own pages may ask: a Host that names another site (a DNS rebinding page) or an Origin that is
not the page's own is refused 403, even for a GET; the local page reached through a tunnel on another port is still
itself. A POST must be JSON (415) holding one object (400). A query value that is not one of the choices, and an
address under /api that no view answers, are refused with the contract's error body.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from agentcake import config  # noqa: E402


class Asking(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_answers", disk_min_free_mb=0)
        self.port = config.load_cfg()["port"]

    def error(self, answer, status):
        self.assertEqual(answer.status, status, answer.body)
        self.assertEqual(contract_problems(answer.body, "error"), [])
        return answer.body["error"]

    def test_the_local_page_may_ask_by_either_name(self):
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            self.assertEqual(Client(host).get("/api/health").status, 200, host)

    def test_a_site_whose_name_points_at_this_computer_is_refused(self):
        self.assertIn("at 127.0.0.1 or localhost", self.error(Client("evil.example:7878").get("/api/health"), 403))
        self.error(Client().get("/api/sessions", headers={"Host": None}), 403)

    def test_another_origin_is_refused_even_for_a_get(self):
        answer = Client().get("/api/health", headers={"Origin": "https://evil.example"})
        self.error(answer, 403)
        same = Client().get("/api/health", headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(same.status, 200)

    def test_the_page_through_a_tunnel_on_another_port_is_still_itself(self):
        tunnel = Client("127.0.0.1:17999")
        self.assertEqual(tunnel.get("/api/health", headers={"Origin": "http://127.0.0.1:17999"}).status, 200)
        self.error(tunnel.get("/api/health", headers={"Origin": f"http://127.0.0.1:{self.port}"}), 403)

    def test_a_post_must_be_one_json_object(self):
        client = Client()
        self.assertIn("application/json", self.error(client.post("/api/settings", b"auto_free=1",
                                                                 content_type="application/x-www-form-urlencoded"), 415))
        self.error(client.post("/api/settings", b"[1, 2]"), 400)
        self.error(client.post("/api/settings", b"{not json"), 400)

    def test_a_value_that_is_not_a_choice_names_the_choices(self):
        said = self.error(Client().get("/api/overview", range="year"), 400)
        self.assertEqual(said, "range must be one of the following values: today, 7d, 30d, all.")

    def test_an_address_no_view_answers_is_a_json_404(self):
        self.assertIn("/api/nothing", self.error(Client().get("/api/nothing"), 404))
        self.error(Client().post("/api/nothing", {}), 404)


if __name__ == "__main__":
    unittest.main()
