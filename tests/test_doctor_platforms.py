"""What sits in front of AgentCake, told apart by the headers it adds: agentcake/doctor_platforms.py.

    python3 -I -m unittest discover -s tests -p test_doctor_platforms.py -v      (from the AgentCake folder)

Header samples from the platforms' own documentation: a header added to the
self-check's answer counts by name, or by name and a part of its value (Via); a header that reached AgentCake counts by
name, as collect keeps only the names of most. A CDN comes before the load balancer behind it, and what to change comes
from the first platform that has a sentence for it, else the general one; so does what to change when the platform
answers the upload itself with a status it has a sentence for (CloudFront's 403). tests/test_doctor_public.py runs the same
through stand-ins of CloudFront, Cloudflare, nginx and a Google load balancer.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from agentcake import doctor_platforms, wording  # noqa: E402

PREFIX, SITE_DOMAIN = "/cake", "example.com"


def text(key, **values):
    return wording.text(key, **values)


class Platforms(unittest.TestCase):
    """The platform in front, told apart by the headers it adds."""

    def names(self, answer=(), arrived=()):
        return [platform["name"] for platform in doctor_platforms.identify(answer, arrived)]

    def test_answer_headers_name_cloudfront_cloudflare_and_vercel(self):
        cases = {"CloudFront": [("Via", "1.1 d111111abcdef8.cloudfront.net (CloudFront)")],
                 "Cloudflare": [("CF-RAY", "8c0ffee0-SJC"), ("Server", "cloudflare")],
                 "Vercel": [("X-Vercel-Id", "sfo1::iad1::doctor")]}
        for name, answer in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.names(answer=answer), [name])
        self.assertEqual(self.names(answer=[("X-Amz-Cf-Id", "doctor")]), ["CloudFront"])

    def test_header_names_at_arrival_count_too(self):
        cases = {"CloudFront": ["x-amz-cf-id"], "Cloudflare": ["cf-ray"], "Vercel": ["x-vercel-id"],
                 "Fly.io": ["fly-client-ip"], "Azure Front Door": ["x-azure-ref"],
                 "DigitalOcean App Platform": ["do-connecting-ip"]}
        for name, arrived in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.names(arrived=arrived), [name])

    def test_a_via_header_names_a_platform_only_by_its_value(self):
        self.assertEqual(self.names(arrived=["via"]), [])
        self.assertEqual(self.names(answer=[("Via", "1.1 vegur")]), ["Heroku"])
        self.assertEqual(self.names(answer=[("Via", "1.1 google")]), ["Google Cloud load balancer"])

    def test_a_cdn_comes_before_the_load_balancer_behind_it(self):
        answer = [("Server", "nginx"), ("Via", "1.1 abc.cloudfront.net (CloudFront)")]
        self.assertEqual(self.names(answer=answer), ["CloudFront", "nginx"])

    def test_nothing_known_names_nothing(self):
        self.assertEqual(self.names(answer=[("Server", "BaseHTTP/0.6 Python/3.14")], arrived=["host", "origin"]), [])

    def test_the_change_comes_from_the_first_platform_that_has_one(self):
        found = doctor_platforms.identify([("Via", "1.1 google"), ("Server", "nginx/1.27.3")], ())
        self.assertEqual(doctor_platforms.headers_fix(found, prefix=PREFIX, host=SITE_DOMAIN),
                         text("doctor_public_fix_nginx", prefix=PREFIX, host=SITE_DOMAIN))
        self.assertEqual(doctor_platforms.headers_fix([], prefix=PREFIX, host=SITE_DOMAIN),
                         text("doctor_public_fix_headers", prefix=PREFIX, host=SITE_DOMAIN))

    def test_a_status_a_platform_answers_itself_names_its_change(self):
        """CloudFront answers 403 to a method its behavior doesn't allow; any other status, or another platform's 403,
        gets the general change: the path rule."""
        values = {"prefix": PREFIX, "host": SITE_DOMAIN}
        cloudfront = doctor_platforms.identify([("X-Amz-Cf-Id", "doctor")])
        forward = text("doctor_public_fix_forward", **values)
        self.assertEqual(doctor_platforms.status_fix(cloudfront, 403, **values),
                         text("doctor_public_fix_cloudfront_methods", **values))
        self.assertEqual(doctor_platforms.status_fix(cloudfront, 404, **values), forward)
        self.assertEqual(doctor_platforms.status_fix(doctor_platforms.identify([("Server", "nginx")]), 403, **values),
                         forward)
        self.assertEqual(doctor_platforms.status_fix([], 403, **values), forward)


if __name__ == "__main__":
    unittest.main()
