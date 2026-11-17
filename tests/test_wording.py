"""agentcake/wording.py: the words AgentCake prints, and the address of every document of the repository they name.

A wheel and a .pyz carry the package only: SERVER.md, PRIVACY.md and the other documents are in the repository (and
the release folder). So a sentence that names one gives its address too, the repository at this version's tag:
{source}, which product() fills from data/product.json and the version, so no release writes it by hand.

    python3 -I -m unittest discover -s tests -p test_wording.py -v      (from the repository root)
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import agentcake  # noqa: E402
from agentcake import wording  # noqa: E402

DOCUMENT = re.compile(r"[A-Za-z0-9_./-]+\.md\b")
WORD_FILES = ("copy.en.json", "api.en.json", "coverage.en.json", "judging.en.json")
RELEASE_SETTINGS = os.path.join(ROOT, "tools", "releasing", "release.json")


def strings(value, where=""):
    """Every string of a word file, with where it is."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if not key.startswith(("$", "_")):
                yield from strings(inner, f"{where}.{key}")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from strings(inner, f"{where}[{index}]")
    elif isinstance(value, str):
        yield where, value


def repository_documents(text):
    """The documents of the repository a text names that the package does not carry."""
    return [name for name in DOCUMENT.findall(text)
            if os.path.isfile(os.path.join(ROOT, name)) and not name.startswith("agentcake/")]


def without_comments(source):
    """A page's source without its comments (/* … */, {/* … */} and // to the end of a line)."""
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", source, flags=re.S))


class Source(unittest.TestCase):
    def test_source_is_the_repository_at_this_versions_tag(self):
        with open(RELEASE_SETTINGS, encoding="utf-8") as f:
            tag = json.load(f)["tag_prefix"] + agentcake.__version__
        self.assertEqual(wording.product()["source"],
                         f"https://github.com/tartini-ai/agent-traffic-analytics/blob/{tag}")

    def test_every_document_a_sentence_names_comes_with_its_address(self):
        named = 0
        for name in WORD_FILES:
            with open(os.path.join(ROOT, "agentcake", "data", name), encoding="utf-8") as f:
                words = json.load(f)
            for where, text in strings(words):
                for document in repository_documents(text):
                    named += 1
                    with self.subTest(f"{name}{where}: {document}"):
                        self.assertIn("{source}/" + document, text)
        self.assertGreater(named, 0)

    def test_every_document_a_page_names_links_to_its_address(self):
        """The local pages name a document only as a DocumentLink, which links to it at {source} (vite.config.ts)."""
        named = 0
        for folder, _, files in os.walk(os.path.join(ROOT, "web", "src")):
            for file in files:
                if not file.endswith(".tsx"):
                    continue
                with open(os.path.join(folder, file), encoding="utf-8") as f:
                    text = without_comments(f.read())
                for document in repository_documents(text):
                    named += 1
                    with self.subTest(f"{file}: {document}"):
                        self.assertNotIn(document, re.sub(r'<DocumentLink path="[^"]+" />', "", text))
        self.assertGreater(named, 0)

    def test_the_address_is_filled_in_where_the_words_are_printed(self):
        sentence = wording.text("site_sentence", launcher="agentcake")
        self.assertIn(wording.product()["source"] + "/SERVER.md", sentence)
        self.assertNotIn("{source}", sentence)


if __name__ == "__main__":
    unittest.main()
