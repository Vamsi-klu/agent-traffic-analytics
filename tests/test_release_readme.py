"""tools/releasing/readme.py: a release names README's pictures at its own tag.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Between releases README.md and its Chinese translation show the repository's pictures from its main branch
(test_readme_docs.py), so the repository's page shows the pictures main has. The files a release ships name every
address of the repository's files there at the release's tag: PyPI shows the wheel's README as the package's page for
good, and the release folder carries both READMEs. An address at an older tag stops the build. Made-up trees
(release_trees.py), and the repository's own READMEs as the release would ship them.
"""
import os
import re
import unittest

from release_trees import ROOT, VERSION, edit_pyproject, make_tree, settings

from tools.releasing import readme
from tools.releasing.project import Project
from tools.releasing.settings import ReleaseError

REPOSITORY = "example-owner/example-project"  # made up
TAG = "v" + VERSION
RAW, PAGE = f"https://raw.githubusercontent.com/{REPOSITORY}", f"https://github.com/{REPOSITORY}/blob"


def pinned(text):
    return readme.pin(text, REPOSITORY, "main", TAG)


class Pin(unittest.TestCase):
    def test_a_picture_on_main_is_named_at_the_release_tag(self):
        text = (f"![The demo]({RAW}/main/docs/assets/readme/demo.png)\n"
                f'<img src="{RAW}/main/docs/assets/readme/crumb.png" alt="AgentCake" width="112">\n')
        self.assertEqual(pinned(text), text.replace("/main/", f"/{TAG}/"))

    def test_a_link_to_a_file_on_main_is_named_at_the_release_tag(self):
        text = f"[the guide]({PAGE}/main/INSTALL.md)\n"
        self.assertEqual(pinned(text), f"[the guide]({PAGE}/{TAG}/INSTALL.md)\n")

    def test_what_names_the_release_tag_or_no_file_of_the_repository_stays(self):
        text = "\n".join([
            f"[LICENSE]({PAGE}/{TAG}/LICENSE)",
            f"Install by following {RAW}/{TAG}/INSTALL.md step by step.",
            f"[issues](https://github.com/{REPOSITORY}/issues), [releases](https://github.com/{REPOSITORY}/releases)",
            "![a picture of another project](https://raw.githubusercontent.com/another-owner/a-project/main/x.png)",
            "[English](../../../README.md), ![a badge](https://img.shields.io/badge/License-MIT-ff5c8a)",
            "a branch called main, and main/ in a path",
        ]) + "\n"
        self.assertEqual(pinned(text), text)

    def test_an_address_at_another_tag_stops_the_release(self):
        with self.assertRaises(ReleaseError) as caught:
            pinned(f"![The demo]({RAW}/main/docs/assets/readme/demo.png)\n[LICENSE]({PAGE}/v0.0.1/LICENSE)\n")
        self.assertIn("v0.0.1", str(caught.exception))
        self.assertIn("LICENSE", str(caught.exception))

    def test_pinning_twice_changes_nothing_more(self):
        once = pinned(f"![The demo]({RAW}/main/docs/assets/readme/demo.png)\n")
        self.assertEqual(pinned(once), once)


class PinTree(unittest.TestCase):
    """The build's step: the exported commit's READMEs, before the wheel and the release folder are written."""

    def tree(self, files):
        root = make_tree(self, files)
        source = f'[project.urls]\nSource = "https://github.com/{REPOSITORY}"\n\n'
        edit_pyproject(root, "[project.scripts]", source + "[project.scripts]")
        return root

    def test_each_readme_of_the_commit_names_its_pictures_at_the_release_tag(self):
        picture = f"![The demo]({RAW}/main/docs/assets/readme/demo.png)\n"
        root = self.tree({"README.md": "# A made-up AgentCake\n\n" + picture,
                          "docs/locales/zh-CN/README.md": "# 一个编出来的 AgentCake\n\n" + picture})
        project = Project(root, settings())
        changed = readme.pin_tree(root, settings(), project)
        self.assertEqual(changed, {"README.md": 1, "docs/locales/zh-CN/README.md": 1})
        for rel in changed:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                self.assertIn(f"{RAW}/{TAG}/docs/assets/readme/demo.png", f.read())
        self.assertIn(f"{RAW}/{TAG}/docs/assets/readme/demo.png", project.metadata())  # PyPI's page

    def test_a_readme_release_json_names_must_be_in_the_commit(self):
        root = self.tree({})
        with self.assertRaises(ReleaseError) as caught:
            readme.pin_tree(root, settings(), Project(root, settings()))
        self.assertIn("docs/locales/zh-CN/README.md", str(caught.exception))


class TheRepositorysReadmes(unittest.TestCase):
    def test_a_release_of_this_version_ships_them_with_its_own_pictures(self):
        """Only the addresses on main change, each to this version's tag; every picture of the repository is then
        named at that tag, as on 0.5.0's page on PyPI."""
        release = settings()
        project = Project(ROOT, release)
        repository = readme.repository(project, release)
        tag = release["tag_prefix"] + project.version
        branch = release["readme"]["branch"]
        for rel in release["readme"]["files"]:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                text = f.read()
            shipped = readme.pin(text, repository, branch, tag)
            on_main = f"https://raw.githubusercontent.com/{repository}/{branch}/"
            self.assertGreater(text.count(on_main), 0, rel)
            self.assertEqual(shipped, text.replace(on_main, f"https://raw.githubusercontent.com/{repository}/{tag}/"))
            pictures = re.findall(rf"https://raw\.githubusercontent\.com/{re.escape(repository)}/([^/]+)/docs/assets/",
                                  shipped)
            self.assertEqual(set(pictures), {tag}, rel)


if __name__ == "__main__":
    unittest.main()
