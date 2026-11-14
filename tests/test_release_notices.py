"""tools/releasing/notices.py (job web-notices): a release stops unless the compiled pages it copied into the package
hold the third-party notices `npm run build` wrote, each entry with a licence text and each package at the version
web/package-lock.json locks.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The notices here are made up, written the way web/scripts/notices.mjs writes them (web/scripts/notices.test.mjs
checks the real build's).
"""
import json
import os
import unittest

from release_trees import make_tree, settings, write

from tools.releasing import notices
from tools.releasing.settings import ReleaseError

RULE = "=" * 80
NOTICES_JSON = {"web/notices.json": json.dumps({"file": "THIRD_PARTY_NOTICES.txt"})}
LOCKFILE = {"web/package-lock.json": json.dumps({"packages": {
    "": {"name": "made-up-web"},
    "node_modules/made-up-ui": {"version": "1.2.0"},
    "node_modules/@made-up/icons": {"version": "0.4.1"},
    "node_modules/made-up-ui/node_modules/made-up-ui-core": {"version": "2.0.0"},
}})}
MIT = "MIT License\n\nCopyright (c) 2026 Made-up Maintainers\n\nPermission is hereby granted ..."


def entry(title, licence, texts):
    lines = ["", RULE, title, f"License: {licence}"]
    for name, text in texts:
        lines += ["", f"----- {name} -----", "", text]
    return lines


def notices_text(entries, index=None):
    """Notices as the build writes them: a header, the index, then the entries ((title, licence, [(file, text)]))."""
    lines = ["THIRD-PARTY SOFTWARE NOTICES", "", "Made-up header.", "", "Listed below:", ""]
    lines += [f"  {title} ({licence})" for title, licence, _ in (index or entries)]
    for title, licence, texts in entries:
        lines += entry(title, licence, texts)
    return "\n".join(lines) + "\n"


SOUND = [
    ("@made-up/icons 0.4.1", "ISC", [("LICENSE", "ISC License\n\nCopyright (c) 2026 Made-up Icons")]),
    ("made-up-ui 1.2.0", "MIT", [("LICENSE", MIT + "\n\n" + RULE + "\nBundled parts\n" + RULE), ("NOTICE", "Made-up UI")]),
    ("made-up-ui-core 2.0.0", "MIT", [("LICENSE", MIT)]),
    ("Made-up-Font.ttf", "OFL-1.1", [("Made-up-OFL.txt", "Copyright 2026 The Made-up Font Project Authors")]),
]


class Check(unittest.TestCase):
    def pages(self, text):
        """A tree with the notices settings and the lockfile, and compiled pages holding text (None: no notices)."""
        tree = make_tree(self, {**NOTICES_JSON, **LOCKFILE})
        pages = os.path.join(tree, "agentcake", "web")
        write(pages, "index.html", "<!doctype html>\n")
        if text is not None:
            write(pages, "THIRD_PARTY_NOTICES.txt", text)
        return tree, pages

    def test_sound_notices_pass_a_rule_of_equals_signs_inside_a_licence_included(self):
        tree, pages = self.pages(notices_text(SOUND))
        notices.check(tree, settings(), pages)

    def test_pages_without_the_notices_stop_the_release(self):
        tree, pages = self.pages(None)
        with self.assertRaisesRegex(ReleaseError, "the compiled pages have no THIRD_PARTY_NOTICES.txt"):
            notices.check(tree, settings(), pages)

    def test_an_entry_without_a_licence_text_stops_the_release(self):
        bare = [*SOUND[:2], ("made-up-ui-core 2.0.0", "MIT", []), SOUND[3]]
        tree, pages = self.pages(notices_text(bare))
        with self.assertRaisesRegex(ReleaseError, "made-up-ui-core 2.0.0 has no licence text"):
            notices.check(tree, settings(), pages)

    def test_a_package_at_a_version_the_lockfile_does_not_lock_stops_the_release(self):
        other = [SOUND[0], ("made-up-ui 1.1.9", "MIT", [("LICENSE", MIT)]), *SOUND[2:]]
        tree, pages = self.pages(notices_text(other))
        with self.assertRaisesRegex(ReleaseError, "made-up-ui 1.1.9 is not a package web/package-lock.json locks"):
            notices.check(tree, settings(), pages)

    def test_an_index_line_without_an_entry_stops_the_release(self):
        tree, pages = self.pages(notices_text(SOUND[:3], index=SOUND))
        with self.assertRaisesRegex(ReleaseError, "Made-up-Font.ttf is in the index but has no entry"):
            notices.check(tree, settings(), pages)

    def test_notices_that_list_nothing_stop_the_release(self):
        tree, pages = self.pages(notices_text([]))
        with self.assertRaisesRegex(ReleaseError, "they list nothing"):
            notices.check(tree, settings(), pages)

    def test_a_commit_without_web_notices_json_stops_the_release(self):
        tree = make_tree(self, LOCKFILE)
        with self.assertRaisesRegex(ReleaseError, "web/notices.json is not in this commit"):
            notices.check(tree, settings(), os.path.join(tree, "agentcake", "web"))


if __name__ == "__main__":
    unittest.main()
