"""agentcake.pyz: the package as one file that Python runs, `python3 agentcake.pyz <command>`.

A .pyz is a zip behind a shebang line, as the standard library's zipapp makes one (PEP 441); it is written here with
reproducible.py instead, so that its bytes are fixed. Its __main__.py is tools/releasing/pyz_main.py with three values
filled in: BUILD, the version and a hash of the packaged files (the folder the package is unpacked into, one per
build), UNPACK_FOLDER and FROM_ZIP, the commands run without unpacking (release.json). The package files are the
wheel's, and the bootstrap is read from the same tree (the exported commit), so the .pyz depends on the commit alone.
The project's license files (pyproject.toml's license-files: LICENSE, THIRD_PARTY.md) sit at the top of the zip, as
the wheel and the release folder carry them; the bootstrap unpacks only the package, so they leave the hash alone.
"""
import hashlib
import json
import os
import pathlib

from tools.releasing import reproducible
from tools.releasing.settings import ReleaseError, file_name, modes

MAIN = "__main__.py"  # protocol: the module Python runs in a zip it is given


def content_hash(files):
    """A hash of (name, contents) of every file, in order: the same files give the same hash."""
    digest = hashlib.sha256()
    for name, data, _ in files:
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()


def fill(template, values):
    """The bootstrap with each "@key@" string replaced by its value, written as a Python string."""
    for key, value in values.items():
        slot = f'"@{key}@"'
        if template.count(slot) != 1:
            raise ReleaseError(f"{MAIN} of the .pyz must hold {slot} exactly once")
        template = template.replace(slot, json.dumps(value))
    return template


def entries(project, settings):
    """(name, bytes, executable) of every file of the .pyz: __main__.py, the license files, then the package."""
    licenses = [(name, pathlib.Path(project.root, name).read_bytes(), False) for name in project.license_files()]
    files = [(name, pathlib.Path(path).read_bytes(), executable)
             for name, path, executable in project.package_files()]
    chars = settings["pyz"]["build_hash_chars"]
    build_id = f"{project.version}-{content_hash(files)[:chars]}"
    template = pathlib.Path(project.root, settings["pyz"]["bootstrap"]).read_bytes().decode("utf-8")
    main = fill(template, {"build": build_id, "unpack_folder": settings["pyz"]["unpack_folder"],
                           "from_zip": settings["pyz"]["from_zip"]})
    return [(MAIN, main.encode("utf-8"), False)] + licenses + files


def build(project, out_dir, epoch, settings):
    """Write the .pyz into out_dir, executable; returns its path."""
    path = os.path.join(out_dir, file_name(settings, "pyz", project.name, project.version))
    prefix = (settings["pyz"]["shebang"] + "\n").encode("utf-8")
    reproducible.write_zip(path, entries(project, settings), epoch, modes(settings), settings["zip_compresslevel"],
                           prefix=prefix)
    os.chmod(path, modes(settings)["executable"])
    return path
