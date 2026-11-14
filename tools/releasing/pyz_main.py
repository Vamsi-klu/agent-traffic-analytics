"""Agent Cake as one file (plan step S6.4): python3 agentcake.pyz <command>. This is the zip's __main__.py.

Agent Cake reads its own files (data, local pages) from the folder its package is in, and a zip is not a
folder. So the first run unpacks the package once into <CAKE_HOME>/pyz/<version>-<hash>/ (CAKE_HOME as
agentcake.paths.home() says, imported from the zip), and every run imports the package from there and runs it in
this process, as `python3 -m agentcake` does: agentcake/__main__.py checks the Python version, then runs the command.
sys.argv[0] stays this file's full path, by which agentcake.paths.launcher() tells people how to run Agent Cake
again (S6.1). A newer release unpacks next to an older one; a folder no release uses any more can be deleted.

The commands in FROM_ZIP (--version, help) read only the package's own JSON files, which the package can read from
the zip (agentcake.datafiles.read): they run straight from the zip, unpack nothing and make no CAKE_HOME, so they also
work where CAKE_HOME cannot be written, such as a coding agent's sandbox (S6.6).

tools/releasing/pyz.py copies this file into the zip with BUILD, UNPACK_FOLDER and FROM_ZIP filled in. Any Python 3
must be able to read it, so that one too old for Agent Cake reaches the sentence saying which Python it needs.
"""
import os
import runpy
import shutil
import sys
import tempfile
import zipfile

BUILD = "@build@"  # <version>-<hash of the packaged files>: one folder per build
UNPACK_FOLDER = "@unpack_folder@"  # release.json "pyz" -> "unpack_folder", the folder under CAKE_HOME
FROM_ZIP = "@from_zip@"  # release.json "pyz" -> "from_zip", the commands run without unpacking
PACKAGE = "agentcake"


def unpacked(archive):
    """The folder holding this build's package, unpacked from archive by the first run that needed it."""
    from agentcake import paths  # from the zip: only home() is used, which reads no file of the package

    parent = os.path.join(paths.home(), UNPACK_FOLDER)
    target = os.path.join(parent, BUILD)
    if os.path.isdir(target):
        return target
    if not os.path.isdir(parent):
        os.makedirs(parent)
    scratch = tempfile.mkdtemp(prefix=BUILD + ".", dir=parent)
    try:
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(scratch, [name for name in zipped.namelist() if name.startswith(PACKAGE + "/")])
        try:
            os.rename(scratch, target)  # a run sees the whole package or none of it
        except OSError:
            if not os.path.isdir(target):  # not a run that unpacked the same build at the same moment
                raise
    finally:
        if os.path.isdir(scratch):
            shutil.rmtree(scratch)
    return target


def run():
    archive = os.path.abspath(sys.argv[0])
    sys.argv[0] = archive
    if len(sys.argv) == 2 and sys.argv[1] in FROM_ZIP:
        runpy.run_module(PACKAGE, run_name="__main__", alter_sys=False)  # imported from the zip, as Python ran it
        return
    folder = unpacked(archive)
    # From here on everything is imported from the unpacked copy, which has real files, not from the zip.
    sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry) != archive]
    sys.path.insert(0, folder)
    for name in [name for name in sys.modules if name == PACKAGE or name.startswith(PACKAGE + ".")]:
        del sys.modules[name]
    runpy.run_module(PACKAGE, run_name="__main__", alter_sys=False)


if __name__ == "__main__":
    run()
