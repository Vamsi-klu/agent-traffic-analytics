"""tools/releasing/project.py (plan step S6.4): the version comes from agentcake/__init__.py alone, the metadata from
pyproject.toml, and the package is every file of agentcake/ except what is never shipped.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import unittest

from release_trees import ROOT, VERSION, edit_pyproject, make_tree, settings, write

import agentcake  # noqa: E402  (release_trees puts the repository on sys.path)
from tools.releasing.project import Project
from tools.releasing.settings import ReleaseError

NO_DEPENDENCIES = "dependencies = []"


class Version(unittest.TestCase):
    def test_the_version_is_read_from_the_package(self):
        self.assertEqual(Project(make_tree(self), settings()).version, VERSION)

    def test_the_repository_version_is_agentcake_init(self):
        self.assertEqual(Project(ROOT, settings()).version, agentcake.__version__)

    def test_a_version_in_pyproject_stops_the_release(self):
        tree = make_tree(self)
        write(tree, "pyproject.toml", '[project]\nname = "agentcake"\nversion = "9.9.9"\ndynamic = ["description"]\n')
        with self.assertRaises(ReleaseError):
            Project(tree, settings())

    def test_no_version_in_the_package_stops_the_release(self):
        tree = make_tree(self, {"agentcake/__init__.py": '"""No version here."""\n'})
        with self.assertRaisesRegex(ReleaseError, "__version__"):
            Project(tree, settings())


class Metadata(unittest.TestCase):
    def test_fields_come_from_pyproject_and_the_docstring(self):
        text = Project(make_tree(self), settings()).metadata()
        head, body = text.split("\n\n", 1)
        self.assertEqual(head.splitlines(), [
            "Metadata-Version: 2.2", "Name: agentcake", f"Version: {VERSION}",
            "Summary: A made-up Agent Cake for the release tests.", "Requires-Python: >=3.11",
            "Description-Content-Type: text/markdown"])
        self.assertEqual(body, "# A made-up Agent Cake\n\nFor the release tests.\n")

    def test_a_license_expression_and_file_need_metadata_2_4(self):
        tree = make_tree(self, {"LICENSE": "made-up licence text\n"})
        edit_pyproject(tree, NO_DEPENDENCIES, NO_DEPENDENCIES + '\nlicense = "MIT"')
        lines = Project(tree, settings()).metadata().splitlines()
        self.assertIn("Metadata-Version: 2.4", lines)
        self.assertIn("License-Expression: MIT", lines)
        self.assertIn("License-File: LICENSE", lines)

    def test_a_license_file_alone_is_listed(self):
        project = Project(make_tree(self, {"LICENSE": "made-up licence text\n"}), settings())
        self.assertEqual(project.license_files(), ["LICENSE"])
        self.assertIn("License-File: LICENSE", project.metadata().splitlines())

    def test_no_license_file_yet_is_fine(self):
        self.assertEqual(Project(make_tree(self), settings()).license_files(), [])

    def test_a_license_files_pattern_that_matches_nothing_stops_the_release(self):
        tree = make_tree(self)
        edit_pyproject(tree, NO_DEPENDENCIES, NO_DEPENDENCIES + '\nlicense-files = ["COPYING"]')
        with self.assertRaisesRegex(ReleaseError, "COPYING"):
            Project(tree, settings()).metadata()

    def test_dependencies_stop_the_release(self):
        tree = make_tree(self)
        edit_pyproject(tree, NO_DEPENDENCIES, 'dependencies = ["requests"]')
        with self.assertRaisesRegex(ReleaseError, "dependencies"):
            Project(tree, settings())

    def test_a_project_key_the_release_does_not_write_stops_it(self):
        tree = make_tree(self)
        edit_pyproject(tree, NO_DEPENDENCIES, NO_DEPENDENCIES + '\nkeywords = ["agents"]')
        with self.assertRaisesRegex(ReleaseError, "keywords"):
            Project(tree, settings())

    def test_entry_points_name_the_command(self):
        self.assertEqual(Project(make_tree(self), settings()).entry_points(),
                         "[console_scripts]\nagentcake = agentcake.cli:main\n")


class Files(unittest.TestCase):
    def test_package_files_leave_out_compiled_python_and_junk(self):
        tree = make_tree(self, {"agentcake/__pycache__/cli.cpython-314.pyc": "x", "agentcake/old.pyc": "x",
                                "agentcake/.DS_Store": "x", "agentcake/web/node_modules/dep/index.js": "x",
                                "agentcake/web/index.html": "<!doctype html>\n"})
        names = [name for name, _, _ in Project(tree, settings()).package_files()]
        self.assertEqual(names, ["agentcake/__init__.py", "agentcake/cli.py", "agentcake/data/product.json",
                                 "agentcake/web/index.html"])

    def test_package_files_say_which_are_executable(self):
        tree = make_tree(self, {"agentcake/tool.sh": "#!/bin/sh\n"}, executable=("agentcake/tool.sh",))
        flags = {name: executable for name, _, executable in Project(tree, settings()).package_files()}
        self.assertTrue(flags["agentcake/tool.sh"])
        self.assertFalse(flags["agentcake/cli.py"])

    def test_names_follow_the_wheel_and_source_distribution_formats(self):
        tree = make_tree(self)
        edit_pyproject(tree, 'name = "agentcake"', 'name = "Agent.Cake-Tool"')
        project = Project(tree, settings())
        self.assertEqual(project.wheel_name(), f"agent_cake_tool-{VERSION}-py3-none-any.whl")
        self.assertEqual(project.dist_info(), f"agent_cake_tool-{VERSION}.dist-info")
        self.assertEqual(project.sdist_base(), f"agent_cake_tool-{VERSION}")


if __name__ == "__main__":
    unittest.main()
