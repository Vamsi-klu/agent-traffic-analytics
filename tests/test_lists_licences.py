"""Each repository the lists are built from ships its licence file beside them, as <source>.LICENSE.txt.

    python3 -I -m unittest discover -s tests -p test_lists_licences.py -v      (from the cake folder)

botscent, PostHog and ai.robots.txt are MIT, which asks for the copyright notice and the permission notice in every
copy. The build already reads each repository's licence file at the commit it reads the lists from (to check it still
says what sources.json expects); it writes that file, unchanged, beside the lists it writes: into the release's
agentcake/data/lists/ (tools/build_lists.py) and into each snapshot of `agentcake lists update`. So a release that
refreshes the lists from newer commits ships those commits' notices. Offline, with test_lists_build.py's small world.
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path[:0] = [ROOT, TESTS]
from agentcake.detect import lists, lists_build  # noqa: E402
from test_lists_build import NOW, fetcher, recipe, world  # noqa: E402

LICENCE = "MIT License\n\nCopyright (c) 2026 Made-up Maintainers\n\n\"MIT Expat\" license\nPermission is hereby granted\n"


def licence_names(sources):
    return sorted(lists_build.licence_file(source) for source in sources["repos"])


class BuildTest(unittest.TestCase):
    def test_the_build_gives_each_sources_licence_file_as_it_was_fetched(self):
        sources = recipe()
        files = lists_build.build(sources, lists_build.read_recipe()[1],
                                  fetcher(world(sources, license_text=LICENCE)), None, NOW)
        licences = {name: text for name, text in files.items() if not name.endswith(".json")}
        self.assertEqual(licences, {name: LICENCE for name in licence_names(sources)})

    def test_a_licence_file_is_written_unchanged_beside_the_lists(self):
        folder = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, folder)
        lists_build.write_files({"a.json": {"v": 1}, lists_build.licence_file("made-up"): LICENCE}, folder)
        with open(os.path.join(folder, lists_build.licence_file("made-up")), encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), LICENCE)

    def test_an_update_keeps_the_licences_with_its_snapshot(self):
        root = tempfile.mkdtemp(prefix="cake-lists-")
        self.addCleanup(shutil.rmtree, root)
        sources = recipe()
        with mock.patch.object(lists_build, "read_recipe", return_value=(sources, lists_build.read_recipe()[1])):
            later = datetime.datetime.combine(
                datetime.date.fromisoformat(lists.Lists.load().built) + datetime.timedelta(days=1),
                datetime.time(12), datetime.timezone.utc)
            folder = lists_build.update(fetcher(world(sources, license_text=LICENCE)), later, root)
        self.assertEqual(sorted(os.listdir(folder)), sorted([*lists.SNAPSHOT_FILES, *licence_names(sources)]))


class ShippedTest(unittest.TestCase):
    """The release's own lists folder holds every source's licence file, and THIRD_PARTY.md points to each."""

    def test_every_source_of_the_lists_ships_its_licence_and_third_party_md_names_it(self):
        sources, _ = lists_build.read_recipe()
        with open(os.path.join(ROOT, "THIRD_PARTY.md"), encoding="utf-8") as f:
            third_party = f.read()
        for source, spec in sources["repos"].items():
            with self.subTest(source=source):
                path = os.path.join(lists.BUNDLED_DIR, lists_build.licence_file(source))
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                for words in (spec["license_marker"], "Copyright (c)", "Permission is hereby granted"):
                    self.assertIn(words, text)
                where = os.path.relpath(path, ROOT).replace(os.sep, "/")
                self.assertTrue(f"`{where}`" in third_party, f"THIRD_PARTY.md does not name {where}")

    def test_the_lists_folder_holds_no_licence_of_a_source_it_does_not_use(self):
        sources, _ = lists_build.read_recipe()
        shipped = sorted(name for name in os.listdir(lists.BUNDLED_DIR) if not name.endswith(".json"))
        self.assertEqual(shipped, licence_names(sources))


if __name__ == "__main__":
    unittest.main()
