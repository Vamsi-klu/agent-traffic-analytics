"""How the name and verification lists are read: agentcake/detect/lists.py.

    python3 -I -m unittest discover -s tests -p test_lists_reading.py -v      (from the AgentCake folder)

The release's lists are parsed once per process, whichever CAKE_HOME asks, and again only when their files change;
each load keeps its own record of the updates it skipped. Address blocks are read as ipaddress reads them, faster:
the same first and last address and the same errors, for every bundled block and for other spellings.
"""
import datetime
import ipaddress
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake.detect import lists  # noqa: E402

BUNDLED = lists.BUNDLED_DIR  # the release's own lists


class ParsedOnceTest(unittest.TestCase):
    """The release's lists are parsed once per process, whichever CAKE_HOME asks (every test, `agentcake serve` and
    each command have their own), and parsed again only when their files change."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, self.root)

    def copy_bundled(self, name, built=None, indent=None):
        """A snapshot folder under the scratch root holding the bundled files, every one saying `built` if given."""
        target = os.path.join(self.root, name)
        os.makedirs(target, exist_ok=True)
        for file in lists.SNAPSHOT_FILES:
            with open(os.path.join(BUNDLED, file), encoding="utf-8") as f:
                data = json.load(f)
            data["built"] = built or data["built"]
            with open(os.path.join(target, file), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent)
        return target

    def parsing(self):
        """Counts the snapshot folders parsed while it is active."""
        return mock.patch.object(lists.Lists, "from_dir", wraps=lists.Lists.from_dir)

    def test_the_bundled_lists_are_parsed_once_whichever_user_root_asks(self):
        lists.Lists.load(BUNDLED)  # parsed now, unless an earlier test did
        with self.parsing() as from_dir:
            loaded = [lists.Lists.load(BUNDLED, user_root=os.path.join(self.root, f"home{n}")) for n in range(3)]
        from_dir.assert_not_called()
        self.assertEqual({snapshot.location for snapshot in loaded}, {"bundled"})

    def test_a_folder_whose_files_change_is_parsed_again(self):
        release = self.copy_bundled("release")
        built = lists.Lists.load(release).built
        newer = str(datetime.date.fromisoformat(built) + datetime.timedelta(days=1))
        with self.parsing() as from_dir:
            self.assertEqual(lists.Lists.load(release).built, built)
            from_dir.assert_not_called()
            self.copy_bundled("release", built=newer, indent=1)  # rewritten, as tools/build_lists.py does
            self.assertEqual(lists.Lists.load(release).built, newer)
            from_dir.assert_called_once()

    def test_newer_downloaded_list_still_resolves_a_retired_product_id(self):
        newer = datetime.date.fromisoformat(lists.Lists.load(BUNDLED).built) + datetime.timedelta(days=1)
        user_root = os.path.join(self.root, "home")
        cached = self.copy_bundled(os.path.join("home", str(newer)), built=str(newer))
        path = os.path.join(cached, "names.json")
        with open(path, encoding="utf-8") as f:
            snapshot = json.load(f)
        canonical = next(entry for entry in snapshot["names"] if entry["id"] == "grok-bot")
        token = next(pattern for pattern in canonical["patterns"] if pattern["text"] == "GrokAgent")
        canonical["patterns"].remove(token)
        evidence = canonical.pop("evidence")
        snapshot["names"].append({"id": "grokagent", "name": "GrokAgent", "operator": "xAI", "kind": "cloud-agent",
                                  "evidence": evidence, "sources": ["cake"], "patterns": [token]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)

        loaded = lists.Lists.load(BUNDLED, user_root=user_root)
        self.assertEqual(loaded.location, cached)
        for ua in ("GrokAgent/1.0", "Grok Bot GrokAgent/1.0"):
            with self.subTest(ua=ua):
                found = loaded.match_ua(ua)
                self.assertEqual((found["id"], found["name"], found["operator"], found["evidence"]),
                                 ("grok-bot", "Grok Bot", "Anysphere", "unverified"))

    def test_each_load_says_what_it_skipped(self):
        newer = datetime.date.fromisoformat(lists.Lists.load(BUNDLED).built) + datetime.timedelta(days=5)
        broken = self.copy_bundled(os.path.join("home", str(newer)))
        with open(os.path.join(broken, "names.json"), "w", encoding="utf-8") as f:
            f.write("{ not json")
        with_broken = lists.Lists.load(BUNDLED, user_root=os.path.join(self.root, "home"))
        clean = lists.Lists.load(BUNDLED, user_root=os.path.join(self.root, "empty-home"))
        self.assertEqual((with_broken.location, len(with_broken.skipped)), ("bundled", 1))
        self.assertEqual(clean.skipped, [], "one load's skipped updates are not another's")


class NetworkSpanTest(unittest.TestCase):
    """An address block is read as ipaddress.ip_network reads it: the same first and last address, the same errors,
    for every block of the bundled lists and for spellings the lists might hold one day."""
    # documentation addresses (RFC 5737, RFC 3849): a prefix with a leading zero, no prefix, a netmask, everything,
    # IPv6 spellings, host bits set, a leading zero in the address, a prefix too long, too few parts, a space, a scope,
    # not an address, nothing, and an integer (ipaddress takes one)
    ODD = ["198.51.100.0/24", "198.51.100.0/024", "198.51.100.7", "192.0.2.0/255.255.255.0", "0.0.0.0/0",
           "2001:db8::/32", "2001:0DB8::/32", "::ffff:192.0.2.0/120", "::/0", "192.0.2.1/24", "192.0.02.0/24",
           "192.0.2.0/33", "192.0.2/24", " 192.0.2.0/24", "2001:db8::1%eth0/64", "a/b", "", 3221225984]

    @staticmethod
    def outcome(read, block):
        try:
            return read(block)
        except ValueError as error:
            return f"ValueError: {error}"

    @staticmethod
    def by_ipaddress(block):
        network = ipaddress.ip_network(block)
        return network.version, int(network.network_address), int(network.broadcast_address)

    def test_every_bundled_block_reads_as_ipaddress_reads_it(self):
        with open(os.path.join(BUNDLED, "ip_ranges.json"), encoding="utf-8") as f:
            blocks = [block for spec in json.load(f)["ranges"] for block in spec.get("v4", []) + spec.get("v6", [])]
        self.assertTrue(blocks)
        self.assertEqual([lists.network_span(block) for block in blocks],
                         [self.by_ipaddress(block) for block in blocks])

    def test_other_spellings_read_or_fail_as_ipaddress_does(self):
        for block in self.ODD:
            with self.subTest(block=block):
                self.assertEqual(self.outcome(lists.network_span, block), self.outcome(self.by_ipaddress, block))


if __name__ == "__main__":
    unittest.main()
