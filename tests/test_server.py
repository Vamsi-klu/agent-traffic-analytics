"""The local listener of a real `agentcake serve` (server.py): what other sites' pages can and cannot do.

    python3 -I -m unittest discover -s tests -p test_server.py -v      (from the Agent Cake folder)

Another site may post visits to collect (a dev server on another port is another origin), so collect and its
preflight carry CORS headers; nothing else does, so no other page can read the local pages' data, and a preflight
for /api is refused. /api answers a request that names this computer, never one whose Host names another site (DNS
rebinding). / is the compiled pages' index.html.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cake_server import SITE_KEY, CakeServer, http  # noqa: E402

ALLOW_ORIGIN = "Access-Control-Allow-Origin"
VISIT = (b'{"v":1,"k":"' + SITE_KEY.encode() + b'","s":"localvisit","pv":"pv","seq":0,"t":1794500000000,'
         b'"u":"http://localhost:3000/","e":[],"r":[],"x":[]}')


class LocalListener(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def test_the_root_is_the_compiled_pages(self):
        status, headers, body = http(self.server.local + "/")
        self.assertEqual((status, headers["Content-Type"]), (200, "text/html; charset=utf-8"))
        self.assertIn(b"<!doctype html>", body)

    def test_only_collect_answers_other_origins(self):
        status, headers, _ = http(self.server.local + "/collect", VISIT,
                                  {"Content-Type": "text/plain", "Origin": "http://localhost:3000"}, "POST")
        self.assertEqual((status, headers.get(ALLOW_ORIGIN)), (204, "*"))
        status, headers, _ = http(self.server.local + "/collect", method="OPTIONS")
        self.assertEqual((status, headers.get(ALLOW_ORIGIN)), (204, "*"))
        for path in ("/api/sessions", "/api/health", "/"):
            self.assertNotIn(ALLOW_ORIGIN, http(self.server.local + path)[1], path)
        status, headers, _ = http(self.server.local + "/api/settings", method="OPTIONS")
        self.assertEqual((status, headers.get(ALLOW_ORIGIN)), (404, None))

    def test_api_refuses_a_host_that_names_another_site(self):
        self.assertEqual(http(self.server.local + "/api/sessions")[0], 200)
        self.assertEqual(http(self.server.local + "/api/sessions", headers={"Host": "rebind.example"})[0], 403)


if __name__ == "__main__":
    unittest.main()
