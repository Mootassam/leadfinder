"""
Where Lead Finder reads bundled files from and writes its data to — the one
place that knows whether we run from source or as a packaged/installed app.
"""

from __future__ import annotations

import os
import sys

APP_NAME = "Lead Finder"
FROZEN = bool(getattr(sys, "frozen", False))
HERE = os.path.dirname(os.path.abspath(__file__))


def is_installed() -> bool:
    return FROZEN or os.path.isfile(os.path.join(HERE, ".installed"))


def bundle_dir() -> str:
    if FROZEN:
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return HERE


def static_dir() -> str:
    return os.path.join(bundle_dir(), "static")


def data_dir() -> str:
    override = os.environ.get("LEADFINDER_DATA")
    if override:
        d = override
    elif is_installed():
        d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME)
    else:
        d = HERE
    os.makedirs(d, exist_ok=True)
    return d
