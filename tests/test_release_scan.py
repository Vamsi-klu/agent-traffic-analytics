"""tools/releasing/scan.py: compiled Python, node_modules and this computer's paths are found in a
release file and named without their value; a clean release has no problem.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import os
import unittest

from release_trees import ROOT, scratch, settings

from tools.releasing import reproducible, scan

EPOCH = 1794528000  # 2026-11-12 00:00:00 UTC, a made-up commit time
MODES = {"file": 0o644, "executable": 0o755, "folder": 0o755}
LEVEL = 9
MADE_UP_HOME = "/home/made-up-builder"
TEXTS = {"this computer's home folder": MADE_UP_HOME}


class Problems(unittest.TestCase):
    def setUp(self):
        self.out = scratch(self)

    def zip_of(self, name, entries):
        path = os.path.join(self.out, name)
        reproducible.write_zip(path, [(n, d, False) for n, d in entries], EPOCH, MODES, LEVEL)
        return path

    def test_a_clean_release_file_has_none(self):
        path = self.zip_of("clean.whl", [("agentcake/a.py", b"A = 1\n")])
        self.assertEqual(scan.problems([path], TEXTS, settings()), [])

    def test_a_personal_path_is_found_and_not_printed(self):
        path = self.zip_of("leak.whl", [("agentcake/web/app.js", f"//# {MADE_UP_HOME}/src/app.ts".encode())])
        found = scan.problems([path], TEXTS, settings())
        self.assertEqual(found, ["leak.whl: agentcake/web/app.js contains this computer's home folder"])
        self.assertNotIn(MADE_UP_HOME, found[0])

    def test_compiled_python_and_node_modules_are_found(self):
        path = self.zip_of("junk.whl", [("agentcake/__pycache__/a.cpython-314.pyc", b"x"),
                                        ("agentcake/web/node_modules/dep/index.js", b"x"), ("agentcake/b.pyc", b"x")])
        found = scan.problems([path], TEXTS, settings())
        self.assertEqual(found, ["junk.whl: agentcake/__pycache__/a.cpython-314.pyc has __pycache__",
                                 "junk.whl: agentcake/web/node_modules/dep/index.js has node_modules",
                                 "junk.whl: agentcake/b.pyc is compiled Python"])

    def test_a_tar_gz_is_read_and_its_wheel_left_alone(self):
        wheel_bytes = f"a wheel that mentions {MADE_UP_HOME}".encode()
        path = os.path.join(self.out, "folder.tar.gz")
        reproducible.write_tar_gz(path, [("top", None, True), ("top/README.md", MADE_UP_HOME.encode(), False),
                                         ("top/dist/x.whl", wheel_bytes, False)], EPOCH, MODES, LEVEL)
        self.assertEqual(scan.problems([path], TEXTS, settings()),
                         ["folder.tar.gz: top/README.md contains this computer's home folder"])


class PersonalTexts(unittest.TestCase):
    def test_home_repository_and_build_folder_are_looked_for(self):
        build_folder = scratch(self)
        texts = scan.personal_texts(ROOT, build_folder, settings()["scan"]["min_chars"])
        self.assertEqual(texts["the repository's folder"], ROOT)
        self.assertEqual(texts["the build folder"], build_folder)
        if len(os.path.expanduser("~")) >= settings()["scan"]["min_chars"]:
            self.assertEqual(texts["this computer's home folder"], os.path.expanduser("~"))

    def test_a_value_shorter_than_the_minimum_is_not_looked_for(self):
        build_folder = scratch(self)
        texts = scan.personal_texts(ROOT, build_folder, len(build_folder) + 1)
        self.assertNotIn("the build folder", texts)


if __name__ == "__main__":
    unittest.main()
