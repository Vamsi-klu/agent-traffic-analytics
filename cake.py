#!/usr/bin/env python3
"""cake 0.3.x's entry point, kept so 0.3.x installs and older deploy/cake.service files keep working.

`python3 [-I] cake.py <command>` is bin/agentcake <command>: it runs agentcake/__main__.py next to this file, which
checks the Python version, finds the package and runs the command line.
"""
import os
import runpy

if __name__ == "__main__":
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentcake", "__main__.py"),
                   run_name="__main__")
