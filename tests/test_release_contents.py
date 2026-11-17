"""What a release carries of this repository's package: tools/releasing/project.py package_files(), the one list the
wheel, the .pyz and the release folder are written from. Each file answers for itself: a folder is one chosen here, a
data file is named by the code or another data file that ships (a comment or a docstring naming it reads nothing),
cake.js ships built while its sources stay in the checkout, the evaluation stays in the checkout with eval/, and a
licence file is one that THIRD_PARTY.md or cake.js's build names. The release adds web/ (the compiled pages) and edge/ (the sites' middleware) when it builds:
test_release_webapp.py and test_release_middleware.py cover those.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import ast
import json
import os
import posixpath
import unittest

from release_trees import ROOT, settings

from tools.releasing.project import Project

PACKAGE = "agentcake"
FOLDERS = {"agentcake", "agentcake/api", "agentcake/data", "agentcake/data/lists", "agentcake/detect", "agentcake/static",
           "agentcake/static/src"}
EVALUATION = ("agentcake/eval.py", "agentcake/evaluation/", "agentcake/data/eval.json", "agentcake/data/splice.json")
BUILT_SCRIPT = "agentcake/static/cake.js"
SOURCES_FOLDER = "agentcake/static/src/"
DATA_FOLDER = "agentcake/data/"
LICENCE_SUFFIX = ".LICENSE.txt"
DATA_SUFFIX = ".json"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def string_literals(path):
    """The strings a Python module's code holds, without its docstrings."""
    tree = ast.parse(read(path), path)
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


class ReleasedPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {name: path for name, path, _ in Project(ROOT, settings()).package_files()}

    def test_it_has_only_the_folders_chosen_here(self):
        self.assertEqual({posixpath.dirname(name) for name in self.files}, FOLDERS)

    def test_cake_js_ships_built_and_of_its_sources_only_the_licences(self):
        parts = json.loads(read(os.path.join(ROOT, PACKAGE, "data", "cakejs.json")))["build"]["parts"]
        licences = {f"{PACKAGE}/{part['licence']}" for part in parts if "licence" in part}
        self.assertIn(BUILT_SCRIPT, self.files)
        self.assertEqual({name for name in self.files if name.startswith(SOURCES_FOLDER)}, licences)

    def test_the_evaluation_stays_in_the_checkout(self):
        self.assertEqual([name for name in self.files if name.startswith(EVALUATION)], [])

    def test_every_data_file_is_named_by_code_or_data_that_ships(self):
        code = "\n".join(text for name, path in self.files.items() if name.endswith(".py")
                         for text in string_literals(path))
        data = {name: read(path) for name, path in self.files.items() if name.endswith(DATA_SUFFIX)}
        third_party = read(os.path.join(ROOT, "THIRD_PARTY.md"))
        for name in self.files:
            if not name.startswith(DATA_FOLDER):
                continue
            with self.subTest(name):
                if name.endswith(LICENCE_SUFFIX):
                    self.assertIn(name, third_party)
                    continue
                named_by = code + "\n".join(text for other, text in data.items() if other != name)
                self.assertTrue(posixpath.basename(name) in named_by, "no code or data that ships names it")


if __name__ == "__main__":
    unittest.main()
