"""The commit a release is built from: which one, its time, and a clean copy of it to build in.

A release is built from a commit, never from the working tree: export() writes the commit's files (`git archive`)
into an empty folder, so nothing that is not committed (an edited file, a local node_modules, __pycache__, a stray
file in web/public) can reach a release, and building the same commit twice starts from the same files. Every file
in the release carries the commit's time (SOURCE_DATE_EPOCH when it is set, as reproducible builds agree:
https://reproducible-builds.org/specs/source-date-epoch/). uncommitted() lists what the working tree has that the
commit has not, which the release leaves out and says so.
"""
import os
import subprocess
import tarfile

from tools.releasing.settings import ReleaseError

EPOCH_VARIABLE = "SOURCE_DATE_EPOCH"  # protocol: the reproducible-builds name


def git(repository, *args):
    """git's output, exactly as it wrote it."""
    out = subprocess.run(["git", "-C", repository, *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def head(repository):
    """The commit checked out (its full hash)."""
    return git(repository, "rev-parse", "--verify", "HEAD^{commit}").strip()


def commit_time(repository, commit, environ=os.environ):
    """The time stamped on every file of the release: SOURCE_DATE_EPOCH, else the commit's time."""
    if environ.get(EPOCH_VARIABLE):
        try:
            return int(environ[EPOCH_VARIABLE])
        except ValueError:
            raise ReleaseError(f"{EPOCH_VARIABLE} must be a whole number of seconds") from None
    return int(git(repository, "log", "-1", "--format=%ct", commit))


def uncommitted(repository):
    """Tracked files whose working-tree state differs from the commit. git status -z: entries "XY <path>" end in a
    NUL; a rename or copy (X is R or C) is followed by one more entry, the path it came from."""
    entries = iter(git(repository, "status", "--porcelain", "-z", "--untracked-files=no").split("\0"))
    paths = []
    for entry in entries:
        if not entry:
            continue
        paths.append(entry[len("XY "):])
        if entry[0] in "RC":
            next(entries, None)
    return paths


def export(repository, commit, folder):
    """Write the commit's files into folder (which must not exist yet)."""
    os.makedirs(folder)
    archive = subprocess.Popen(["git", "-C", repository, "archive", "--format=tar", commit], stdout=subprocess.PIPE)
    unreadable = None
    try:
        with tarfile.open(fileobj=archive.stdout, mode="r|") as tar:
            if hasattr(tarfile, "data_filter"):  # Python 3.11.4 and later: refuse links and paths leaving folder
                tar.extractall(folder, filter="data")
            else:
                tar.extractall(folder)
    except tarfile.TarError as error:
        unreadable = error
    finally:
        archive.stdout.close()
        code = archive.wait()
    if code != 0 or unreadable:
        raise ReleaseError(f"git archive {commit} failed (exit {code}{f', {unreadable}' if unreadable else ''})")
