"""agentcake/addresses.py: an address that cannot be read is no address, never an error (log matching too).

    python3 -I -m unittest discover -s tests -p test_addresses.py -v      (from the repository root)
"""
import os
import sqlite3
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import addresses, log_match  # noqa: E402


class Addresses(unittest.TestCase):
    def test_a_readable_address_gives_its_parts_and_path(self):
        self.assertEqual(addresses.split("https://shop.example/cart?x=1").netloc, "shop.example")
        self.assertEqual(addresses.path("https://shop.example/cart?x=1"), "/cart")
        self.assertEqual(addresses.path("https://shop.example"), "")

    def test_no_address_and_an_unreadable_one_give_none(self):
        for url in (None, "", "https://[", "http://[/cart"):
            with self.subTest(url):
                self.assertIsNone(addresses.split(url))
                self.assertIsNone(addresses.path(url))

    def test_a_page_view_whose_address_cannot_be_read_has_no_path_to_match(self):
        """Anyone can send collect an address urlsplit refuses (an unclosed IPv6 bracket): that page view is matched
        by time only, like one without an address, and the other page views of the session keep their paths."""
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE batches (session_id TEXT, pv TEXT, seq INTEGER, url TEXT)")
        con.executemany("INSERT INTO batches VALUES (?, ?, ?, ?)", [("s1", "a", 0, "https://["),
                                                                     ("s1", "b", 0, "https://shop.example/cart")])
        self.assertEqual(log_match._first_urls(con, "s1"), {"a": None, "b": "/cart"})


if __name__ == "__main__":
    unittest.main()
