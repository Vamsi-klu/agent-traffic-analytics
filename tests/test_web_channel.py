"""The channel a session came through, by PostHog's default channel rules: agentcake/web_channel.py with
data/channels.json (PostHog's channel definitions, MIT).

    python3 -I -m unittest discover -s tests -p test_web_channel.py -v

Each case follows a branch of PostHog's rules (posthog/hogql/database/schema/channel_type.py, documented at
posthog.com/docs/data/channel-type): cross-network campaigns, paid visits (a paid medium, gclid, gad_source) by source,
shopping campaign, medium, referring domain, then gad_source=1, a video campaign, a Facebook click; Direct; organic
visits by the same lookups, then video, push, a Facebook click, no referrer, a referrer. A referring domain is looked
up as it is and as each shorter domain of two labels or more.
"""
import unittest
from collections import namedtuple

from agentcake import web_channel

Entry = namedtuple("Entry", "referring_domain utm_source utm_medium utm_campaign gad_source has_gclid has_fbclid")


def entry(domain="", source=None, medium=None, campaign=None, gad=None, gclid=False, fbclid=False):
    return Entry(domain, source, medium, campaign, gad, gclid, fbclid)


CASES = [
    (entry(campaign="Cross-Network-Spring"), "Cross Network"),
    (entry(source="google", medium="cpc"), "Paid Search"),
    (entry(source="facebook", medium="paid_social"), "Paid Social"),
    (entry(medium="cpc", campaign="summer-shopping"), "Paid Shopping"),
    (entry(medium="display"), "Display"),
    (entry(domain="www.youtube.com", gclid=True), "Paid Video"),
    (entry(gad="1"), "Paid Search"),
    (entry(medium="ppc", campaign="video-launch"), "Paid Video"),
    (entry(medium="cpc", fbclid=True), "Paid Social"),
    (entry(gclid=True), "Paid Unknown"),
    (entry(), "Direct"),
    (entry(source="(direct)"), "Direct"),
    (entry(domain="www.google.com"), "Organic Search"),
    (entry(domain="www.google.co.uk"), "Organic Search"),
    (entry(domain="news.ycombinator.com"), "Organic Social"),
    (entry(domain="chatgpt.com"), "AI"),
    (entry(source="newsletter", medium="email"), "Email"),
    (entry(source="Instagram"), "Organic Social"),
    (entry(domain="", campaign="black-friday-shop"), "Direct"),
    (entry(domain="blog.example.net", campaign="black-friday-shop"), "Organic Shopping"),
    (entry(domain="blog.example.net", campaign="product-video"), "Organic Video"),
    (entry(source="app", medium="web-push"), "Push"),
    (entry(fbclid=True), "Organic Social"),
    (entry(domain="blog.example.net"), "Referral"),
    (entry(source="null", medium=""), "Direct"),
]


class Channel(unittest.TestCase):
    def test_each_branch_of_posthogs_default_rules(self):
        for found, expected in CASES:
            with self.subTest(entry=found):
                self.assertEqual(web_channel.channel(found), expected)

    def test_the_definitions_are_posthogs_with_both_kinds(self):
        definitions = web_channel._definitions()
        self.assertEqual(definitions["source"]["google"], ["Paid Search", "Organic Search"])
        self.assertEqual(definitions["medium"]["email"], [None, "Email"])


if __name__ == "__main__":
    unittest.main()
