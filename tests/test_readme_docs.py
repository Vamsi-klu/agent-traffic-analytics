"""README.md and its Chinese translation (docs/locales/zh-CN/README.md) against the release and each other.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Each README has one install sentence, in its own language and in a code block to copy, that names this version
and points at the INSTALL.md of this tag; it names both ways to read that file, curl and the GitHub CLI. The pictures
are files of the repository (docs/assets/readme/, drawn by scripts in web/scripts/: the dashboard preview by
readme-preview.mjs, the icon by readme-images.mjs) or shields.io's static badges,
which link to the repository. Both READMEs name their pictures by full addresses at this release's tag: the release's
files leave docs/assets/ out, so a path would show nothing in a downloaded copy, and PyPI shows README.md as the
package's page (pyproject.toml's readme), where a path in the repository leads nowhere. For that page README.md also
names the files it links to by their pages on GitHub; the Chinese README, which only GitHub and the release's folder
show, links to them by their paths. The Chinese README shows the same pictures, links, commands and version as the
English one, and each links to the other at the top.
test_install_docs.py checks what both READMEs share with INSTALL.md (commands, links, addresses).
"""
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from cake_server import ROOT, read  # noqa: E402  (needs the path above)
from test_install_docs import (INSTALL_MD, LINK, README_MD, README_ZH, READMES, VERSION, code_blocks,  # noqa: E402
                               documented_commands, local_file, readme_name, release_tag, repositories,
                               repository_file, section)

PICTURE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)|<img\s[^>]*\bsrc=\"([^\"]+)\"")
BADGE = re.compile(r"\[!\[[^\]]*\]\(([^)\s]+)\)\]\(([^)\s]+)\)")  # [![alt](picture)](link)
STATIC_BADGE = "https://img.shields.io/badge/"  # protocol: shields.io's badges drawn from the URL alone
RAW_INSTALL_MD = re.compile(r"https://raw\.githubusercontent\.com/\S+/INSTALL\.md")
CJK = re.compile(r"[一-鿿]")
TWO_WAYS = ("curl", "GitHub CLI")  # the sentence's two ways to read INSTALL.md


def install_sentences(markdown):
    """The code blocks that point at INSTALL.md on a tag, each block's lines joined: the sentence to paste."""
    joined = (" ".join(lines) for lines in code_blocks(markdown))
    return [sentence for sentence in joined if RAW_INSTALL_MD.search(sentence)]


def pictures(path, repository):
    """Every picture a document shows (Markdown or <img>): (as written, the file of this checkout it names, or None
    for an address outside the repository)."""
    found = [markdown or html for markdown, html in PICTURE.findall(read(path))]
    return [(picture, local_file(picture, path, repository)) for picture in found]


def repository_targets(path, repository):
    """The files of the repository a document links to, as paths from the repository's root."""
    found = (local_file(target, path, repository) for target in LINK.findall(read(path)))
    return {os.path.relpath(local, ROOT) for local in found if local}


class ReadmeDocuments(unittest.TestCase):
    """What a newcomer reads first, in English and in Chinese, matches the release and says the same."""

    @classmethod
    def setUpClass(cls):
        cls.readme, cls.readme_zh = read(README_MD), read(README_ZH)
        cls.version, cls.tag = release_tag()
        cls.name = readme_name(cls.readme)
        cls.repository, = repositories(read(INSTALL_MD))

    def test_each_readme_has_one_install_sentence_for_this_version_and_its_install_md(self):
        """README's in English and the Chinese README's in Chinese, each in a code block under Install."""
        url = f"https://raw.githubusercontent.com/{self.repository}/{self.tag}/INSTALL.md"
        for path, install_heading, chinese in READMES:
            install = section(read(path), install_heading)
            sentence, = install_sentences(install)
            self.assertEqual(bool(CJK.search(sentence)), chinese, path)
            self.assertIn(f"{self.name} {self.version}", sentence)
            self.assertIn(url, sentence)
            for way in TWO_WAYS:
                self.assertIn(way, sentence)
            self.assertEqual(set(VERSION.findall(install)), {self.version}, path)

    def test_pictures_are_in_the_repository_or_are_static_badges(self):
        for path, *_ in READMES:
            local = [(picture, file) for picture, file in pictures(path, self.repository)
                     if not picture.startswith(STATIC_BADGE)]
            self.assertTrue(local, path)
            for picture, file in local:
                self.assertTrue(file, f"{path} shows {picture}, which is not in the repository")
                self.assertTrue(os.path.isfile(file), f"{path} shows {picture}, which is missing")

    def test_badges_are_static_and_link_to_this_repository(self):
        """Each links to the repository's own pages (releases, issues) or to a file in it."""
        for path, *_ in READMES:
            badges = BADGE.findall(read(path))
            self.assertTrue(badges, path)
            for picture, link in badges:
                self.assertTrue(picture.startswith(STATIC_BADGE), picture)
                local = local_file(link, path, self.repository)
                if local:
                    self.assertTrue(os.path.exists(local), link)
                else:
                    self.assertTrue(link.startswith(f"https://github.com/{self.repository}/"), link)

    def test_readme_md_names_the_repositorys_files_by_full_addresses_at_this_tag(self):
        """PyPI shows README.md as the package's page, where a path in the repository leads nowhere: each picture of
        the repository is its raw address and each file README.md links to is its page on GitHub, both at this
        release's tag, so they show alike on GitHub and on PyPI."""
        raw = f"https://raw.githubusercontent.com/{self.repository}/{self.tag}/"
        page = f"https://github.com/{self.repository}/blob/{self.tag}/"
        shown = {picture for picture, _ in pictures(README_MD, self.repository)}
        targets = shown | set(LINK.findall(self.readme)) | {link for _, link in BADGE.findall(self.readme)}
        self.assertTrue([target for target in targets if repository_file(target, self.repository)])
        for target in sorted(targets):
            self.assertRegex(target, r"^(https://|mailto:|#)", f"README.md: {target} is not a full address")
            if repository_file(target, self.repository):
                self.assertTrue(target.startswith(raw if target in shown else page), target)

    def test_each_readme_shows_the_repositorys_pictures_by_full_addresses_at_this_tag(self):
        """The release's files leave docs/assets/ out: a picture named by its path would be missing in the downloaded
        folder's copy of either README, where its raw address at the tag shows it as GitHub does."""
        raw = f"https://raw.githubusercontent.com/{self.repository}/{self.tag}/"
        for path, *_ in READMES:
            shown = [picture for picture, file in pictures(path, self.repository) if file]
            self.assertTrue(shown, path)
            for picture in shown:
                self.assertTrue(picture.startswith(raw), f"{path} shows {picture}, not its address at {self.tag}")

    def test_the_chinese_readme_shows_what_the_english_one_does(self):
        self.assertEqual({file for _, file in pictures(README_MD, self.repository)},
                         {file for _, file in pictures(README_ZH, self.repository)})
        self.assertEqual(repository_targets(README_MD, self.repository) - {"docs/locales/zh-CN/README.md"},
                         repository_targets(README_ZH, self.repository) - {"README.md"})
        self.assertEqual(set(documented_commands(self.readme)), set(documented_commands(self.readme_zh)))
        self.assertEqual(set(VERSION.findall(self.readme)), set(VERSION.findall(self.readme_zh)))
        self.assertIn(f"[简体中文](https://github.com/{self.repository}/blob/{self.tag}/docs/locales/zh-CN/README.md)",
                      self.readme)
        self.assertIn("[English](../../../README.md)", self.readme_zh)


if __name__ == "__main__":
    unittest.main()
