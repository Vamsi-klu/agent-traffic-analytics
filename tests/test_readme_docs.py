"""README.md and its Chinese translation (docs/locales/zh-CN/README.md) against the release and each other.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Each README shows its install prompt below the title and again under Install. The prompt names this version
and points at the INSTALL.md of this tag; it names both ways to read that file, curl and the GitHub CLI. The pictures
are files of the repository (docs/assets/readme/, drawn by scripts in web/scripts/: the dashboard preview by
readme-preview.mjs, the icon by readme-images.mjs) or shields.io's static badges,
which link to the repository. Both READMEs name their pictures by full addresses on the repository's main branch: the
release's files leave docs/assets/ out, so a path would show nothing in a downloaded copy, and PyPI shows README.md as
the package's page (pyproject.toml's readme), where a path in the repository leads nowhere. On main, the repository's
page shows the pictures main has between releases; a release names them at its own tag in the files it ships
(tools/releasing/readme.py, test_release_readme.py), so its page on PyPI keeps them. For that page README.md also
names the files it links to by their pages on GitHub at this release's tag; the Chinese README, which only GitHub and
the release's folder show, links to them by their paths. The Chinese README shows the same pictures, links, commands
and version as the English one, and each links to the other at the top.
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
from tools.releasing import settings as release_settings  # noqa: E402

PICTURE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)|<img\s[^>]*\bsrc=\"([^\"]+)\"")
BADGE = re.compile(r"\[!\[[^\]]*\]\(([^)\s]+)\)\]\(([^)\s]+)\)")  # [![alt](picture)](link)
STATIC_BADGE = "https://img.shields.io/badge/"  # protocol: shields.io's badges drawn from the URL alone
RAW_INSTALL_MD = re.compile(r"https://raw\.githubusercontent\.com/\S+/INSTALL\.md")
CJK = re.compile(r"[一-鿿]")
TWO_WAYS = ("curl", "GitHub CLI")  # the sentence's two ways to read INSTALL.md
# An agent without network reads no guide, so the sentence itself has it ask for network access when the download
# fails (Codex in a sandbox without network asked only for the guide's text, and the release's files fail alike)
ASK_FOR_NETWORK = {False: "If the download fails, ask for network access.",
                   True: "如果下载失败，请申请网络访问权限。"}
PASTE_INSTRUCTIONS = {
    False: "Copy and paste these instructions into Claude Code or Codex to complete the installation.",
    True: "要完成安装，请将下面的说明复制并粘贴到 Claude Code 或 Codex 的对话框中。",
}


def readme_branch():
    """The branch both READMEs name the repository's pictures on (release.json "readme"), as a release reads it."""
    return release_settings.load()["readme"]["branch"]


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
        cls.branch = readme_branch()
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
            self.assertIn(ASK_FOR_NETWORK[chinese], sentence)
            self.assertEqual(set(VERSION.findall(install)), {self.version}, path)

    def test_the_title_highlights_the_original_install_prompt_before_the_badges(self):
        fence = r"```text\n(.+?)\n```"
        for path, heading, chinese in READMES:
            with self.subTest(path=os.path.relpath(path, ROOT)):
                markdown = read(path)
                install = section(markdown, heading)
                original, = re.findall(r"^" + fence + r"$", install, re.M | re.S)
                lead = re.escape(PASTE_INSTRUCTIONS[chinese])
                top = re.search(r"^# [^\n]+\n\n" + lead + r'\n\n(?:<div align="left">\n\n)?' + fence, markdown, re.M | re.S)
                self.assertIsNotNone(top, "missing install instructions immediately below the title")
                self.assertLess(top.end(), BADGE.search(markdown).start())
                self.assertEqual(top[1], original)
                self.assertEqual(len(original.splitlines()), 1 if chinese else 3)
                self.assertEqual(install_sentences(markdown), [" ".join(original.splitlines())] * 2)

    def test_the_install_instructions_at_the_top_are_left_aligned(self):
        """The top block is centered (<div align="center">), and a code block takes its alignment from the block around
        it: each line of the instructions was centered. A left-aligned block around the fence, with a blank line on
        each side so GitHub still renders the fence, keeps the lines flush left; the sentence above stays centered."""
        for path, *_ in READMES:
            with self.subTest(path=os.path.relpath(path, ROOT)):
                markdown = read(path)
                left = re.search(r'\n\n<div align="left">\n\n```text\n[^`]*?/v0\.6\.0/INSTALL\.md[^`]*?\n```\n\n</div>\n\n',
                                 markdown)
                self.assertIsNotNone(left, "no left-aligned block around the instructions at the top")
                self.assertLess(markdown.index('<div align="center">'), left.start())
                self.assertLessEqual(left.end(), markdown.index("[!["))

    def test_the_dashboard_preview_folds_the_cake_style_and_shows_the_minimal_style(self):
        """The dashboard preview is two folded <details> blocks with the same table in each, in both READMEs: Cake
        style folded, Minimal style open (readme-preview.mjs --style minimal), the same pictures in the same order and
        the same line of no-break spaces under each. A README runs no script, so folding is the closest it comes to
        the pages' Style menu. A blank line after each title lets GitHub render the table; the animation above stays
        unfolded."""
        titles = {False: ("Cake style", "Minimal style"), True: ("Cake 样式", "Minimal 样式")}
        for path, _, chinese in READMES:
            with self.subTest(path=os.path.relpath(path, ROOT)):
                markdown = read(path)
                blocks = re.findall(r"<details( open)?>\n<summary>([^<]+)</summary>\n\n(.*?)\n</details>", markdown, re.S)
                self.assertEqual([(opened, title) for opened, title, _ in blocks],
                                 [("", titles[chinese][0]), (" open", titles[chinese][1])])
                cake, minimal = (body for _, _, body in blocks)
                pictures = [m or h for m, h in PICTURE.findall(cake)]
                self.assertEqual(len(pictures), 6)
                self.assertTrue(all("/preview-" in picture for picture in pictures), pictures)
                self.assertIn("&nbsp;" * 100, cake)
                self.assertEqual(minimal, cake.replace('.png"', '-minimal.png"'))
                unfolded = markdown[:markdown.index("<details")]
                self.assertTrue(any("/demo.png" in (m or h) for m, h in PICTURE.findall(unfolded)))

    def test_each_readme_says_the_registration_goes_to_tartini_ai_once(self):
        """As the local page and PRIVACY.md say: only the registration details, to Tartini AI, once, when you choose
        Register and continue."""
        expected = {False: r"Choosing \*\*Register and continue\*\* sends your registration details to Tartini AI once\.",
                    True: r"只有在你选择 \*\*Register and continue\*\* 后，AgentCake 才会将你的注册信息发送给 Tartini AI，且仅发送一次。"}
        for path, _, chinese in READMES:
            with self.subTest(path=os.path.relpath(path, ROOT)):
                self.assertRegex(" ".join(read(path).split()), expected[chinese])

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

    def test_readme_md_names_the_repositorys_files_by_full_addresses(self):
        """PyPI shows README.md as the package's page, where a path in the repository leads nowhere: each picture of
        the repository is its raw address on main (a release names it at its own tag, test_release_readme.py) and each
        file README.md links to is its page on GitHub at this release's tag, so they show alike on GitHub and on
        PyPI."""
        raw = f"https://raw.githubusercontent.com/{self.repository}/{self.branch}/"
        page = f"https://github.com/{self.repository}/blob/{self.tag}/"
        shown = {picture for picture, _ in pictures(README_MD, self.repository)}
        targets = shown | set(LINK.findall(self.readme)) | {link for _, link in BADGE.findall(self.readme)}
        self.assertTrue([target for target in targets if repository_file(target, self.repository)])
        for target in sorted(targets):
            self.assertRegex(target, r"^(https://|mailto:|#)", f"README.md: {target} is not a full address")
            if repository_file(target, self.repository):
                self.assertTrue(target.startswith(raw if target in shown else page), target)

    def test_each_readme_shows_the_repositorys_pictures_from_main(self):
        """Between releases the repository's page shows the pictures main has: each README names every picture of the
        repository by its raw address on main, never at a tag, where a picture stays as it was however main changes
        it. A full address, not a path: the release's files leave docs/assets/ out, so a path would be missing in the
        downloaded folder's copy of either README."""
        raw = f"https://raw.githubusercontent.com/{self.repository}/{self.branch}/"
        for path, *_ in READMES:
            shown = [picture for picture, file in pictures(path, self.repository) if file]
            self.assertTrue(shown, path)
            for picture in shown:
                self.assertTrue(picture.startswith(raw), f"{path} shows {picture}, not its address on {self.branch}")

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
