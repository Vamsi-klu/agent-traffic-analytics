"""README.md and its Chinese translation (docs/locales/zh-CN/README.md) against the release and each other
(readme-preview).

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Each README has one install sentence, in its own language (D21) and in a code block to copy, that names this version
and points at the INSTALL.md of this tag; it names curl and the GitHub CLI, which reads that file signed in while the
repository is a private preview (its raw address answers 404 then). The pictures are files of the repository
(docs/assets/readme/, made by web/scripts/readme-images.mjs) or shields.io's static badges, which draw while the
repository is private and link to it. The Chinese README shows the same pictures, links, commands and version as the
English one, and each links to the other at the top. Each README's connect sentence is the one the local page shows in
its language. test_install_docs.py checks what both READMEs share with INSTALL.md (commands, links, addresses).
"""
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake.wording import product, text  # noqa: E402  (needs the path above)
from cake_server import ROOT, read  # noqa: E402
from test_install_docs import (INSTALL_MD, LINK, README_MD, README_ZH, READMES, VERSION, code_blocks,  # noqa: E402
                               documented_commands, readme_name, release_tag, repositories, section)

PICTURE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)|<img\s[^>]*\bsrc=\"([^\"]+)\"")
BADGE = re.compile(r"\[!\[[^\]]*\]\(([^)\s]+)\)\]\(([^)\s]+)\)")  # [![alt](picture)](link)
STATIC_BADGE = "https://img.shields.io/badge/"  # protocol: shields.io's badges drawn from the URL alone
RAW_INSTALL_MD = re.compile(r"https://raw\.githubusercontent\.com/\S+/INSTALL\.md")
CJK = re.compile(r"[一-鿿]")
TWO_WAYS = ("curl", "GitHub CLI")  # the sentence's two ways to read INSTALL.md: public, then signed in while private


def install_sentences(markdown):
    """The code blocks that point at INSTALL.md on a tag, each block's lines joined: the sentence to paste."""
    joined = (" ".join(lines) for lines in code_blocks(markdown))
    return [sentence for sentence in joined if RAW_INSTALL_MD.search(sentence)]


def pictures(path):
    """Every picture a document shows (Markdown or <img>): (as written, the file it names or None for a URL)."""
    found = [markdown or html for markdown, html in PICTURE.findall(read(path))]
    folder = os.path.dirname(path)
    return [(picture, None if re.match(r"^\w+:", picture) else os.path.normpath(os.path.join(folder, picture)))
            for picture in found]


def repository_targets(path):
    """The files of the repository a document links to, as paths from the repository's root."""
    return {os.path.relpath(os.path.normpath(os.path.join(os.path.dirname(path), target.split("#")[0])), ROOT)
            for target in LINK.findall(read(path)) if not re.match(r"^(https?:|mailto:|#)", target)}


class ReadmeDocuments(unittest.TestCase):
    """What a newcomer reads first, in English and in Chinese, matches the release and says the same."""

    @classmethod
    def setUpClass(cls):
        cls.readme, cls.readme_zh = read(README_MD), read(README_ZH)
        cls.version, cls.tag = release_tag()
        cls.name = readme_name(cls.readme)
        cls.repository, = repositories(read(INSTALL_MD))

    def test_each_readme_has_one_install_sentence_for_this_version_and_its_install_md(self):
        """README's in English and the Chinese README's in Chinese (D21), each in a code block under Install. It works
        whether the repository is public (curl reads the raw address) or a private preview, where that address
        answers 404 and the GitHub CLI, signed in, reads the same file: the sentence names both."""
        url = f"https://raw.githubusercontent.com/{self.repository}/{self.tag}/INSTALL.md"
        for path, install_heading, _, chinese in READMES:
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
            local = [(picture, file) for picture, file in pictures(path) if not picture.startswith(STATIC_BADGE)]
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
                if re.match(r"^https?:", link):
                    self.assertTrue(link.startswith(f"https://github.com/{self.repository}/"), link)
                else:
                    self.assertTrue(os.path.exists(os.path.join(os.path.dirname(path), link)), link)

    def test_the_chinese_readme_shows_what_the_english_one_does(self):
        self.assertEqual({file for _, file in pictures(README_MD)}, {file for _, file in pictures(README_ZH)})
        self.assertEqual(repository_targets(README_MD) - {"docs/locales/zh-CN/README.md"},
                         repository_targets(README_ZH) - {"README.md"})
        self.assertEqual(set(documented_commands(self.readme)), set(documented_commands(self.readme_zh)))
        self.assertEqual(set(VERSION.findall(self.readme)), set(VERSION.findall(self.readme_zh)))
        self.assertIn("[简体中文](docs/locales/zh-CN/README.md)", self.readme)
        self.assertIn("[English](../../../README.md)", self.readme_zh)

    def test_connect_sentences_are_the_ones_the_local_page_shows(self):
        for path, _, connect_heading, chinese in READMES:
            sentence = text("site_sentence", lang="zh" if chinese else "en", launcher=product()["command"],
                            name=self.name)
            self.assertIn(f"> {sentence}", section(read(path), connect_heading), path)


if __name__ == "__main__":
    unittest.main()
