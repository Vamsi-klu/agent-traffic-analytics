"""The local pages in the release: web/ compiled with `npm ci && npm run build`, copied into the package.

The pages are built in the exported commit (source.py), from its package-lock.json, so no local node_modules or
uncommitted file takes part. `npm run build` ends with check:dist, which fails when sample data reached web/dist. The
result goes into the package, in the folder agentcake/data/web.json names ("folders" -> "release"), which is where
agentcake.paths.web_dir() looks first: inside the package, so a wheel installed anywhere has its pages. The
build also writes the bundled packages' licence notices into web/dist; notices.py checks they were copied.
"""
import os
import shutil

from tools.releasing import commands, notices
from tools.releasing.settings import ReleaseError, package_folder


def build(tree, settings):
    """Compile the pages in tree and copy them into the package; returns the folder they were copied to."""
    web = settings["web"]
    folder = os.path.join(tree, web["folder"])
    target = package_folder(tree, settings, web)
    if os.path.exists(target):
        raise ReleaseError(f"{os.path.relpath(target, tree)} is already in the commit: the compiled pages go there")
    for command in web["commands"]:
        commands.run(command, folder, tree)
    shutil.copytree(os.path.join(folder, web["dist"]), target)
    notices.check(tree, settings, target)
    return target
