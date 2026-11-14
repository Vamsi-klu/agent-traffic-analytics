"""The signature on POST /edge: agentcake/edge_signature.py (these tests moved here with
it from test_edge_api.py), what `logs import` signs a batch with and what makes a request one Agent Cake accepts.

    python3 -I -m unittest discover -s tests -p test_edge_signature.py -v      (from the Agent Cake folder)
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import config, edge_signature  # noqa: E402

NOW = 1794500000000
BODY = b'{"v":1,"run":"edgetest","format":"nginx-agentcake","fields":{"missing":[],"empty":[]},"records":[]}'


class Signature(unittest.TestCase):
    secret, body = b"s" * 48, BODY

    def setUp(self):
        self.c = config.DEFAULTS

    def test_a_signed_body_verifies(self):
        header = edge_signature.sign(self.secret, self.body, NOW)
        self.assertTrue(edge_signature.verified(self.secret, header, self.body, NOW, self.c))

    def test_a_changed_body_another_secret_or_a_missing_header_does_not(self):
        header = edge_signature.sign(self.secret, self.body, NOW)
        self.assertFalse(edge_signature.verified(self.secret, header, self.body + b" ", NOW, self.c))
        self.assertFalse(edge_signature.verified(b"t" * 48, header, self.body, NOW, self.c))
        self.assertFalse(edge_signature.verified(self.secret, None, self.body, NOW, self.c))
        self.assertFalse(edge_signature.verified(None, header, self.body, NOW, self.c))

    def test_a_time_outside_the_token_window_does_not(self):
        old = edge_signature.sign(self.secret, self.body, NOW - self.c["token_max_age_ms"] - 1)
        ahead = edge_signature.sign(self.secret, self.body, NOW + self.c["token_max_future_ms"] + 1)
        self.assertFalse(edge_signature.verified(self.secret, old, self.body, NOW, self.c))
        self.assertFalse(edge_signature.verified(self.secret, ahead, self.body, NOW, self.c))
        edge = edge_signature.sign(self.secret, self.body, NOW - self.c["token_max_age_ms"])
        self.assertTrue(edge_signature.verified(self.secret, edge, self.body, NOW, self.c))

    def test_malformed_headers_do_not(self):
        good = edge_signature.sign(self.secret, self.body, NOW)
        prefix, t, mac = good.split(".")
        for bad in ("", good + ".x", f"c1.{t}.{mac}", f"{prefix}.soon.{mac}", f"{prefix}.{t}.{mac}=", f"{prefix}.{t}",
                    f"{prefix}.-{t}.{mac}", f"{prefix}.{t}.{mac[:-1]}"):
            self.assertFalse(edge_signature.verified(self.secret, bad, self.body, NOW, self.c), bad)


if __name__ == "__main__":
    unittest.main()
