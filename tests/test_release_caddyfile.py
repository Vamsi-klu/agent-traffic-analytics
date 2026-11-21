"""tools/releasing/caddyfile.py: deploy/Caddyfile trusts exactly the Cloudflare ranges of the lists that ship.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

refresh() writes the lists' ranges into the Caddyfile's trusted_proxies line, IPv4 then IPv6, and changes nothing else
of the file; a second refresh changes nothing. check() refuses a tree whose line names other ranges, and says how to
fix it. A Caddyfile without the line, or lists without the entry, are refused. The repository's own Caddyfile passes.
"""
import json
import os
import unittest

from release_trees import ROOT, make_tree, settings, write

from tools.releasing import caddyfile
from tools.releasing.settings import ReleaseError

V4, V6 = ["198.51.100.0/24", "203.0.113.0/24"], ["2001:db8::/32"]  # documentation ranges, standing in for Cloudflare's
CADDYFILE = """# a made-up Caddyfile
{
\tservers {
\t\ttrusted_proxies static 192.0.2.0/24
\t\tclient_ip_headers CF-Connecting-IP
\t}
}

cake.example.com {
\trespond 404
}
"""


def lists_with(entries):
    return json.dumps({"ranges": entries}) + "\n"


class Repository(unittest.TestCase):
    def test_the_repositorys_caddyfile_names_the_lists_ranges(self):
        caddyfile.check(ROOT, settings())
        named = caddyfile.named(ROOT, settings())
        self.assertTrue(any(":" in r for r in named) and any("." in r for r in named), "IPv4 and IPv6 alike")


class Refresh(unittest.TestCase):
    def setUp(self):
        rules = settings()["caddyfile"]
        entries = [{"id": "elsewhere", "v4": ["192.0.2.0/24"], "v6": []},
                   {"id": rules["range_id"], "v4": V4, "v6": V6}]
        self.tree = make_tree(self, {rules["file"]: CADDYFILE, rules["ranges_file"]: lists_with(entries)})
        self.path = os.path.join(self.tree, rules["file"])

    def text(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_it_writes_the_lists_ranges_and_keeps_the_rest_of_the_file(self):
        self.assertTrue(caddyfile.refresh(self.tree, settings()))
        expected = CADDYFILE.replace("static 192.0.2.0/24", "static " + " ".join(V4 + V6))
        self.assertEqual(self.text(), expected)
        self.assertEqual(caddyfile.named(self.tree, settings()), V4 + V6)
        caddyfile.check(self.tree, settings())

    def test_a_second_refresh_changes_nothing(self):
        caddyfile.refresh(self.tree, settings())
        before = self.text()
        self.assertFalse(caddyfile.refresh(self.tree, settings()))
        self.assertEqual(self.text(), before)

    def test_check_refuses_other_ranges_and_says_what_to_do(self):
        with self.assertRaisesRegex(ReleaseError, r"release\.py refresh"):
            caddyfile.check(self.tree, settings())

    def test_a_caddyfile_without_the_line_is_refused(self):
        write(self.tree, settings()["caddyfile"]["file"], CADDYFILE.replace("trusted_proxies", "# trusted_proxies"))
        for step in (caddyfile.refresh, caddyfile.check):
            with self.subTest(step=step.__name__), self.assertRaisesRegex(ReleaseError, "trusted_proxies static"):
                step(self.tree, settings())

    def test_lists_without_the_entry_are_refused(self):
        rules = settings()["caddyfile"]
        write(self.tree, rules["ranges_file"], lists_with([{"id": "elsewhere", "v4": V4, "v6": V6}]))
        with self.assertRaisesRegex(ReleaseError, rules["range_id"]):
            caddyfile.refresh(self.tree, settings())


if __name__ == "__main__":
    unittest.main()
