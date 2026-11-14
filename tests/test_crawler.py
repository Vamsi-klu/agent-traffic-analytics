"""Crawler-like patterns (agentcake.detect.crawler, plan step S3.4): weak signals, never a class (D17).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Three patterns: a datacenter address, page loads (or the network's earlier visits) at fixed intervals, and many pages
in a row. At least two of them (verdict.json "crawler") make the session look like a crawler; one alone does not.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import NOWHERE, T0, S, first_address, network  # noqa: E402
from agentcake.detect import crawler  # noqa: E402


def every(n, seconds, start=T0):
    return [start + i * seconds * S for i in range(n)]


class Patterns(unittest.TestCase):
    def test_datacenter_alone_is_not_crawler_like(self):
        found = crawler.patterns([T0, T0 + 9 * S], network(first_address("aws")))
        self.assertEqual(found, {"datacenter": True, "fixed_interval": False, "every_s": None, "every_of": None,
                                 "many_pages": False, "pages": 2})
        self.assertFalse(crawler.looks_like_crawler(found))

    def test_datacenter_and_fixed_intervals(self):
        found = crawler.patterns(every(5, 30), network(first_address("aws")))
        self.assertTrue(found["fixed_interval"])
        self.assertTrue(crawler.looks_like_crawler(found))

    def test_many_pages_at_fixed_intervals_from_home(self):
        found = crawler.patterns(every(12, 2), network(NOWHERE))
        self.assertEqual((found["datacenter"], found["fixed_interval"], found["many_pages"]), (False, True, True))
        self.assertTrue(crawler.looks_like_crawler(found))

    def test_a_human_reading_pages_is_not_crawler_like(self):
        times = [T0 + s * S for s in (0, 14, 95, 102, 260, 300, 410)]
        found = crawler.patterns(times, network(NOWHERE))
        self.assertFalse(any(found[k] for k in ("datacenter", "fixed_interval", "many_pages")))

    def test_relay_or_cdn_address_is_not_a_datacenter(self):
        for range_id in ("icloud-private-relay", "cloudflare"):
            with self.subTest(range_id):
                self.assertFalse(crawler.patterns([T0], network(first_address(range_id)))["datacenter"])

    def test_coming_back_at_fixed_intervals_counts_with_this_visit(self):
        three_earlier = every(3, 3600, start=T0 - 3 * 3600 * S)
        found = crawler.patterns([T0], network(first_address("aws")), visits=three_earlier)
        self.assertEqual((found["fixed_interval"], found["every_of"], found["every_s"]), (True, "visits", 3600))
        self.assertTrue(crawler.looks_like_crawler(found))
        self.assertIn("comes back every 60 min", crawler.reason(found)["detail"])

    def test_page_loads_at_fixed_intervals_are_said_as_such(self):
        found = crawler.patterns(every(12, 2), network(first_address("aws")))
        self.assertEqual(found["every_of"], "pages")
        self.assertIn("loads a page every 2 s", crawler.reason(found)["detail"])

    def test_reason_names_the_patterns_found(self):
        found = crawler.patterns(every(12, 2), network(first_address("aws")))
        found_reason = crawler.reason(found)
        self.assertEqual(found_reason["id"], "crawler.like")
        self.assertIn("datacenter", found_reason["detail"])
        self.assertIn("12 pages", found_reason["detail"])
        self.assertIsNone(crawler.reason(crawler.patterns([T0], None)))


if __name__ == "__main__":
    unittest.main()
