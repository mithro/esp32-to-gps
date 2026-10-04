#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build the ESP32-C3 GPS Tasmota firmware from the pinned mithro/Tasmota fork.

SPDX-License-Identifier: Apache-2.0

    uv run firmware/build.py                    # clone the fork at TASMOTA_SHA (first time), overlay, compile
    uv run firmware/build.py --fetch-only       # just clone and check out (for the host tests)
    uv run firmware/build.py --clean            # wipe the .pio build directory first
    TASMOTA_DIR=~/github/mithro/Tasmota/.worktrees/esp32-to-gps uv run firmware/build.py
                                                # build a local checkout of the fork instead

The driver and its pure-C core live in the fork (branch esp32-to-gps), so the
build pins the fork by commit. This repository adds only the build settings:
platformio_override.ini and tasmota/user_config_override.h. The script refuses
to build a pinned checkout that is not at TASMOTA_SHA or has other changes.
PlatformIO is pioarduino, the fork upstream Tasmota builds with, run as
`uv tool run --from pioarduino==6.2.0 pio`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

TASMOTA_REPO = "https://github.com/mithro/Tasmota.git"
TASMOTA_BRANCH = "esp32-to-gps"
TASMOTA_SHA = "323e0a355866187377527835b74dfd9d40531191"  # branch saved-receiver (mithro/Tasmota#1)
ENV = "tasmota32c3-gps"
PIOARDUINO = "pioarduino==6.2.0"  # the PlatformIO fork upstream Tasmota CI builds with

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")
OVERLAY = [
    (os.path.join(HERE, "overlay", "user_config_override.h"), "tasmota/user_config_override.h"),
    (os.path.join(HERE, "overlay", "platformio_override.ini"), "platformio_override.ini"),
]
OWNED_PATHS = [rel for _, rel in OVERLAY]


def run(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True)


def checkout() -> tuple[str, bool]:
    """(path, pinned): the fork checkout to build, and whether it is the pinned one."""
    local = os.environ.get("TASMOTA_DIR")
    if local:
        return os.path.abspath(os.path.expanduser(local)), False
    clone = os.path.join(BUILD, "Tasmota")
    if not os.path.isdir(os.path.join(clone, ".git")):
        os.makedirs(BUILD, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", "--no-checkout", TASMOTA_REPO, clone])
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=clone, capture_output=True, text=True).stdout.strip()
    if head != TASMOTA_SHA:
        run(["git", "fetch", "--filter=blob:none", "origin", TASMOTA_SHA], cwd=clone)
        run(["git", "checkout", "--detach", TASMOTA_SHA], cwd=clone)
    return clone, True


def assert_clean(tree: str) -> None:
    out = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=tree, text=True)
    bad = [line for line in out.splitlines() if not any(line[3:].startswith(p) for p in OWNED_PATHS)]
    if bad:
        sys.exit("The pinned fork checkout has changes this build did not make:\n" + "\n".join(bad))


def apply_overlay(tree: str) -> None:
    for src, rel in OVERLAY:
        dst = os.path.join(tree, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    print("overlay applied")


def collect(tree: str, env: str, pinned: bool) -> None:
    os.makedirs(DIST, exist_ok=True)
    src = os.path.join(tree, ".pio", "build", env)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=tree, text=True).strip())
    info = {"tasmota_repo": TASMOTA_REPO, "tasmota_sha": sha, "pinned": pinned, "fork_dirty": dirty, "env": env,
            "built": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "artefacts": {}}
    for name in ("firmware.bin", "firmware.factory.bin", "firmware.elf", "firmware.map"):
        p = os.path.join(src, name)
        if os.path.exists(p):
            dst = os.path.join(DIST, name.replace("firmware", env))
            shutil.copy2(p, dst)
            info["artefacts"][os.path.basename(dst)] = os.path.getsize(dst)
    with open(os.path.join(DIST, f"build-info-{env}.json"), "w") as f:
        json.dump(info, f, indent=2)
    print(json.dumps(info, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default=ENV)
    ap.add_argument("--fetch-only", action="store_true", help="clone and check out the pinned fork, nothing else")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--jobs", type=int, default=0)
    args = ap.parse_args()
    tree, pinned = checkout()
    if args.fetch_only:
        print(tree)
        return
    if pinned:
        assert_clean(tree)
    apply_overlay(tree)
    if args.clean:
        shutil.rmtree(os.path.join(tree, ".pio", "build", args.env), ignore_errors=True)
    cmd = ["uv", "tool", "run", "--from", PIOARDUINO, "pio", "run", "-e", args.env]
    if args.jobs:
        cmd += ["-j", str(args.jobs)]
    run(cmd, cwd=tree)
    collect(tree, args.env, pinned)


if __name__ == "__main__":
    main()
