"""tools/releasing/webapp.py (plan step S6.4): the web build's commands run in web/, and web/dist is copied into the
package, into the folder agentcake/data/web.json names; a commit without that file cannot have its pages served.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

npm itself is replaced by a stand-in that writes web/dist (the real build runs in tools/release.py build), with the
third-party notices the real build writes there (tests/test_release_notices.py checks what notices.py refuses).
"""
import json
import os
import unittest
from unittest import mock

from release_trees import make_tree, settings, write

from tools.releasing import webapp
from tools.releasing.settings import ReleaseError

WEB = settings()["web"]
WEB_JSON = {WEB["settings_file"]: '{"folders": {"release": "web", "checkout": ["web", "dist"]}}\n'}
NOTICES = {WEB["notices"]["settings_file"]: json.dumps({"file": "NOTICES.txt"}),
           WEB["notices"]["lockfile"]: json.dumps({"packages": {"node_modules/made-up-ui": {"version": "1.0.0"}}})}


def stand_in_npm(command, folder, tree):
    """What `npm run build` leaves behind; `npm ci` leaves nothing that is shipped."""
    if command == WEB["commands"][-1]:
        write(folder, "dist/index.html", "<!doctype html>\n")
        write(folder, "dist/assets/app-1a2b3c.js", "console.log(1)\n")
        write(folder, "dist/NOTICES.txt", "NOTICES\n\n  made-up-ui 1.0.0 (MIT)\n\n" + "=" * 80
              + "\nmade-up-ui 1.0.0\nLicense: MIT\n\n----- LICENSE -----\n\nMIT License\n")


class Build(unittest.TestCase):
    def test_the_commands_run_in_web_and_dist_goes_into_the_package(self):
        tree = make_tree(self, {**WEB_JSON, **NOTICES, "web/package.json": "{}\n"})
        with mock.patch("tools.releasing.commands.run", side_effect=stand_in_npm) as run:
            target = webapp.build(tree, settings())
        self.assertEqual([call.args[0] for call in run.call_args_list], WEB["commands"])
        self.assertTrue(all(call.args[1] == os.path.join(tree, "web") for call in run.call_args_list))
        self.assertEqual(target, os.path.join(tree, "agentcake", "web"))
        self.assertTrue(os.path.isfile(os.path.join(target, "assets", "app-1a2b3c.js")))
        self.assertTrue(os.path.isfile(os.path.join(target, "NOTICES.txt")))

    def test_a_build_that_wrote_no_notices_stops_the_release(self):
        tree = make_tree(self, {**WEB_JSON, **NOTICES, "web/package.json": "{}\n"})

        def without_notices(command, folder, tree):
            stand_in_npm(command, folder, tree)
            if command == WEB["commands"][-1]:
                os.remove(os.path.join(folder, "dist", "NOTICES.txt"))

        with mock.patch("tools.releasing.commands.run", side_effect=without_notices), \
                self.assertRaisesRegex(ReleaseError, "the compiled pages have no NOTICES.txt"):
            webapp.build(tree, settings())

    def test_a_commit_without_web_json_stops_the_release_before_npm_runs(self):
        tree = make_tree(self, {"web/package.json": "{}\n"})
        with mock.patch("tools.releasing.commands.run") as run, self.assertRaisesRegex(ReleaseError, "web.json"):
            webapp.build(tree, settings())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
