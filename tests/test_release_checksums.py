"""tools/releasing/checksums.py (plan step S6.4): SHA256SUMS lines as shasum and sha256sum write them, which
`shasum -a 256 -c` accepts, and rejects once a file changed.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import hashlib
import os
import shutil
import subprocess
import unittest

from release_trees import make_tree, scratch, settings

from tools.releasing import checksums
from tools.releasing.project import Project


class Sums(unittest.TestCase):
    def setUp(self):
        self.out = scratch(self)
        self.paths = []
        for name, data in (("b.whl", b"wheel bytes"), ("a.tar.gz", b"tar bytes")):
            path = os.path.join(self.out, name)
            with open(path, "wb") as f:
                f.write(data)
            self.paths.append(path)
        self.sums = checksums.write(self.paths, self.out, settings(), Project(make_tree(self), settings()))

    def test_one_line_per_file_sorted_by_name(self):
        with open(self.sums, encoding="utf-8") as f:
            self.assertEqual(f.read(), f"{hashlib.sha256(b'tar bytes').hexdigest()}  a.tar.gz\n"
                                       f"{hashlib.sha256(b'wheel bytes').hexdigest()}  b.whl\n")
        self.assertEqual(os.path.basename(self.sums), settings()["files"]["checksums"])

    def test_shasum_checks_them_and_notices_a_change(self):
        if not shutil.which("shasum"):
            self.skipTest("no shasum on this computer")
        check = ["shasum", "-a", "256", "-c", os.path.basename(self.sums)]
        ok = subprocess.run(check, cwd=self.out, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(ok.stdout.count(": OK"), len(self.paths))
        with open(self.paths[0], "ab") as f:
            f.write(b"!")
        self.assertNotEqual(subprocess.run(check, cwd=self.out, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
