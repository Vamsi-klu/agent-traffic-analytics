"""agentcake/datafiles.py: the JSON files that ship inside the package, read from the package's folder,
or from inside the .pyz when the bootstrap runs a command from the zip without unpacking it (--version, help), so that
those commands work where CAKE_HOME cannot be written, such as a coding agent's sandbox. And none of those files names
a key twice in one object: json.load keeps only the last one, so the first would be dead text nobody notices.

    python3 -I -m unittest discover -s tests -p test_datafiles.py -v      (from the AgentCake folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentcake import datafiles, paths  # noqa: E402


class Read(unittest.TestCase):
    def test_a_file_of_the_package_folder(self):
        with open(os.path.join(paths.PACKAGE_DIR, "data", "product.json"), encoding="utf-8") as f:
            self.assertEqual(datafiles.read("data/product.json"), f.read())

    def test_a_file_inside_the_zip_the_package_is_imported_from(self):
        folder = tempfile.mkdtemp(prefix="cake-datafiles-")
        self.addCleanup(shutil.rmtree, folder, True)
        archive = os.path.join(folder, "agentcake.pyz")
        with open(archive, "wb") as f:
            f.write(b"#!/usr/bin/env python3\n")  # a .pyz starts with a shebang line before the zip
        with zipfile.ZipFile(archive, "a") as zipped:
            zipped.writestr("agentcake/data/example.json", json.dumps({"from": "the zip"}))
        with mock.patch.object(paths, "PACKAGE_DIR", os.path.join(archive, "agentcake")):
            self.assertEqual(json.loads(datafiles.read("data/example.json")), {"from": "the zip"})


def each_key_once(pairs):
    """object_pairs_hook for json.load: an object that names a key twice is an error, not a silent overwrite."""
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise ValueError(f"key named twice: {', '.join(repeated)}")
    return dict(pairs)


class NoRepeatedKeys(unittest.TestCase):
    def test_a_key_named_twice_is_caught(self):
        with self.assertRaisesRegex(ValueError, "key named twice: text"):
            json.loads('{"reason": {"text": "first", "text": "second"}}', object_pairs_hook=each_key_once)

    def test_every_data_file_names_each_key_once(self):
        data = os.path.join(paths.PACKAGE_DIR, "data")
        problems, files = [], 0
        for folder, _, names in os.walk(data):
            for name in sorted(n for n in names if n.endswith(".json")):
                files += 1
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as f:
                    try:
                        json.load(f, object_pairs_hook=each_key_once)
                    except ValueError as error:
                        problems.append(f"{os.path.relpath(path, data)}: {error}")
        self.assertGreater(files, 0)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
