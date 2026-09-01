"""Shared helpers for live GCP eval scripts."""

from __future__ import annotations

import os
import shutil
import subprocess


def gcloud_bin() -> str:
    for name in ("gcloud", "gcloud.cmd", "gcloud.exe"):
        path = shutil.which(name)
        if path:
            return path
    # Common Windows Cloud SDK install path.
    win = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Google", "Cloud SDK", "google-cloud-sdk", "bin", "gcloud.cmd",
    )
    if win and os.path.isfile(win):
        return win
    raise RuntimeError("gcloud CLI not found on PATH")


def gcloud(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [gcloud_bin(), *args],
        capture_output=True,
        text=True,
        check=check,
    )
