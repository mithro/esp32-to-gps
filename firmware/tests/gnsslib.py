"""Compile the GNSS core from the Tasmota fork into a shared library and load
it with cffi.

The core lives in the fork at tasmota/tasmota_xsns_sensor/gnss/.  The tests
look for the fork checkout in $TASMOTA_DIR, else in firmware/build/Tasmota
(where build.py clones it), so they always run the code the device runs.

The cffi declarations are the core's own headers run through the C
preprocessor, so there is no second copy of the struct layouts to keep in
step.
"""

from __future__ import annotations

import glob
import os
import pathlib
import re
import subprocess

import cffi

HERE = pathlib.Path(__file__).resolve().parent
FIRMWARE = HERE.parent
BUILD = FIRMWARE / "build"
CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-Wshadow", "-Wconversion", "-O1", "-g", "-fPIC"]


def gnss_dir() -> pathlib.Path:
    root = pathlib.Path(os.environ.get("TASMOTA_DIR", BUILD / "Tasmota"))
    d = root / "tasmota" / "tasmota_xsns_sensor" / "gnss"
    if not d.is_dir():
        raise RuntimeError(f"GNSS core not found at {d}: set TASMOTA_DIR or run firmware/build.py --fetch-only")
    return d


def cdefs(src: pathlib.Path) -> str:
    """Every header, preprocessed, with what cffi's parser cannot take removed."""
    headers = sorted(src.glob("gnss_*.h"))
    # System headers first, then a marker, then ours: everything before the
    # marker is the C library's own declarations, which cffi does not need.
    marker = "typedef int gnss_cdef_marker_t;"
    text = "#include <stdbool.h>\n#include <stddef.h>\n#include <stdint.h>\n" + marker + "\n"
    text += "".join(f'#include "{h.name}"\n' for h in headers)
    out = subprocess.run(["cc", "-E", "-P", "-std=c99", "-I", str(src), "-"], input=text,
                         capture_output=True, text=True, check=True).stdout
    out = out[out.index(marker) + len(marker):]
    out = re.sub(r"__attribute__\s*\(\(.*?\)\)", "", out)
    # The preprocessor consumed the #defines; give cffi back the integer ones.
    defines = [m.group(0) for h in headers
               for m in re.finditer(r"^#define [A-Z][A-Z0-9_]+ +-?(0x[0-9a-fA-F]+|\d+)(?=\s*(/\*.*)?$)", h.read_text(), re.M)]
    return "\n".join(d.rstrip("u") for d in defines) + "\n" + out


def load():
    src = gnss_dir()
    BUILD.mkdir(parents=True, exist_ok=True)
    so = BUILD / "libgnss.so"
    srcs = sorted(glob.glob(str(src / "*.c")))
    subprocess.run(["cc", *CFLAGS, "-shared", "-I", str(src), "-o", str(so), *srcs], check=True)
    ffi = cffi.FFI()
    ffi.cdef(cdefs(src))
    return ffi, ffi.dlopen(str(so))
