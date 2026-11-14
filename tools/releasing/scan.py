"""What must never be in a release (S6.4), looked for in every file of every release file before they are kept.

- names: compiled Python (__pycache__, .pyc), node_modules, .git, .DS_Store (release.json "package_files");
- contents: this computer's paths (the home folder, the repository, the build folder) and the git user's name and
  email, which a build step could have written into a file (a source map, a path in a bundle, a stamp).

Each problem says the release file, the file inside it and what was found, never the value itself (it is personal).
A wheel or .pyz is read as a zip, the release folder as a tar; the wheel inside the release folder is the same file as
the wheel (build.py checks that), so it is not opened twice.
"""
import os
import subprocess
import tarfile
import zipfile


def personal_texts(repository, build_folder, min_chars):
    """{what it is: text} of the values no release file may contain. A value shorter than min_chars (release.json
    "scan") is not looked for: a short home folder or user name could be found by chance in minified code."""
    texts = {"this computer's home folder": os.path.expanduser("~"),
             "the repository's folder": os.path.abspath(repository),
             "the build folder": os.path.abspath(build_folder),
             "the build folder's real path": os.path.realpath(build_folder)}
    for key, label in (("user.email", "the git user's email"), ("user.name", "the git user's name")):
        value = git_config(repository, key)
        if value:
            texts[label] = value
    return {label: text for label, text in texts.items() if len(text) >= min_chars}


def git_config(repository, key):
    out = subprocess.run(["git", "-C", repository, "config", "--get", key], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def members(path):
    """(name, bytes or None) of every file inside a release file; None for what is not opened (a nested wheel)."""
    if path.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as tar:
            for info in tar.getmembers():
                if info.isfile():
                    data = None if info.name.endswith(".whl") else tar.extractfile(info).read()
                    yield info.name, data
        return
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            yield name, archive.read(name)


def name_problem(name, skip):
    parts = name.split("/")
    for part in parts:
        if part in skip["skip_dirs"] or part in skip["skip_names"]:
            return f"has {part}"
    if name.endswith(tuple(skip["skip_suffixes"])):
        return "is compiled Python"
    return None


def problems(paths, texts, settings):
    """One line per thing found that must not be in a release (paths: the wheel, the .pyz and the release folder);
    empty when there is none."""
    skip = settings["package_files"]
    encoded = {label: text.encode("utf-8") for label, text in texts.items()}
    found = []
    for path in paths:
        for name, data in members(path):
            problem = name_problem(name, skip)
            if problem:
                found.append(f"{os.path.basename(path)}: {name} {problem}")
            for label, text in encoded.items():
                if data is not None and text in data:
                    found.append(f"{os.path.basename(path)}: {name} contains {label}")
    return found
