"""Reading the operators' address lists: agentcake/detect/lists_ranges.py, offline.

    python3 -I -m unittest discover -s tests -p test_lists_ranges.py -v      (from the AgentCake folder)

AWS publishes one file, ip-ranges.json, in which every prefix names its service: AMAZON (all of them), EC2,
CLOUDFRONT (CloudFront's edge servers), CLOUDFRONT_ORIGIN_FACING (the addresses CloudFront reaches a website from) and
others. The AWS cloud range reads every prefix; Amazon CloudFront's range, a CDN, reads only its two services, so an
address CloudFront sends a visit from is a CDN's (address_check.py, doctor) as Cloudflare's is. The sample below
stands in for AWS's file, on the documentation ranges (RFC 5737, RFC 3849).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentcake.detect import lists, lists_ranges  # noqa: E402

AWS_URL = "https://ranges.example/aws-ip-ranges.json"
EDGE, ORIGIN_FACING, ORIGIN_FACING_V6, EC2 = "192.0.2.0/25", "192.0.2.128/26", "2001:db8:cf::/56", "198.51.100.0/24"
AWS_FILE = {"createDate": "2026-11-12-00-00-00",
            "prefixes": [{"ip_prefix": block, "service": service} for block, service in (
                (EDGE, "AMAZON"), (EDGE, "CLOUDFRONT"), (ORIGIN_FACING, "AMAZON"),
                (ORIGIN_FACING, "CLOUDFRONT_ORIGIN_FACING"), (EC2, "AMAZON"), (EC2, "EC2"))],
            "ipv6_prefixes": [{"ipv6_prefix": ORIGIN_FACING_V6, "service": "CLOUDFRONT_ORIGIN_FACING"}]}
CLOUD = {"id": "aws", "label": "AWS", "kind": "cloud", "operator": "Amazon", "format": "aws", "urls": [AWS_URL],
         "verifies": []}
CDN = {"id": "aws-cloudfront", "label": "Amazon CloudFront", "kind": "cdn", "operator": "Amazon", "format": "aws",
       "services": ["CLOUDFRONT_ORIGIN_FACING", "CLOUDFRONT"], "urls": [AWS_URL], "verifies": []}


def recipe(*specs):
    with open(lists.SOURCES_FILE, encoding="utf-8") as f:
        ip_ranges = json.load(f)["ip_ranges"]
    return dict(ip_ranges, ranges=list(specs))


class Fetches:
    """fetch(url) from AWS_FILE alone, counting the downloads."""

    def __init__(self, body=AWS_FILE):
        self.body, self.count = json.dumps(body).encode("utf-8"), 0

    def __call__(self, url, accept=None):
        if url != AWS_URL:
            raise AssertionError(f"{url} is not in the sample")
        self.count += 1
        return type("Response", (), {"body": self.body})()


class AwsServices(unittest.TestCase):
    def test_without_services_every_prefix_is_read(self):
        (cloud,) = lists_ranges.build_ranges(recipe(CLOUD), Fetches())
        self.assertEqual((cloud["v4"], cloud["v6"]), ([EDGE, ORIGIN_FACING, EC2], [ORIGIN_FACING_V6]))

    def test_with_services_only_their_prefixes_are_read(self):
        (cdn,) = lists_ranges.build_ranges(recipe(CDN), Fetches())
        self.assertEqual((cdn["v4"], cdn["v6"]), ([EDGE, ORIGIN_FACING], [ORIGIN_FACING_V6]))
        self.assertEqual((cdn["kind"], cdn["published"]), ("cdn", AWS_FILE["createDate"]))

    def test_a_service_the_file_no_longer_has_stops_the_build(self):
        renamed = dict(AWS_FILE, prefixes=[p for p in AWS_FILE["prefixes"] if p["service"] != "CLOUDFRONT"])
        with self.assertRaisesRegex(ValueError, "CLOUDFRONT"):
            lists_ranges.build_ranges(recipe(CDN), Fetches(renamed))

    def test_one_file_two_ranges_is_one_download(self):
        fetches = Fetches()
        built = lists_ranges.build_ranges(recipe(CDN, CLOUD), fetches)
        self.assertEqual([entry["id"] for entry in built], ["aws-cloudfront", "aws"])
        self.assertEqual(fetches.count, 1)


class Bundled(unittest.TestCase):
    """sources.json: CloudFront's range is a CDN of its two services, looked up before every cloud."""

    def setUp(self):
        with open(lists.SOURCES_FILE, encoding="utf-8") as f:
            self.ranges = json.load(f)["ip_ranges"]["ranges"]

    def test_cloudfront_is_a_cdn_of_its_origin_facing_and_edge_addresses(self):
        (cloudfront,) = [spec for spec in self.ranges if spec.get("services") and spec["format"] == "aws"]
        self.assertEqual(cloudfront["kind"], "cdn")
        self.assertEqual(set(cloudfront["services"]), {"CLOUDFRONT_ORIGIN_FACING", "CLOUDFRONT"})

    def test_cdns_come_before_clouds(self):
        kinds = [spec["kind"] for spec in self.ranges if spec["kind"] in ("cdn", "cloud")]
        self.assertEqual(kinds, sorted(kinds, key=("cdn", "cloud").index))


if __name__ == "__main__":
    unittest.main()
