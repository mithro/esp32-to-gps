"""Pytest fixtures for the GNSS core host tests.

    TASMOTA_DIR=~/github/mithro/Tasmota/.worktrees/esp32-to-gps \\
        uv run --with pytest --with cffi --with pyubx2 --with pynmeagps --with pyrtcm pytest firmware/tests
"""

from __future__ import annotations

import pathlib

import pytest

from gnsslib import load

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="session")
def core():
    """(ffi, lib) for the compiled core."""
    return load()


@pytest.fixture
def ffi(core):
    return core[0]


@pytest.fixture
def lib(core):
    return core[1]


@pytest.fixture
def state(ffi, lib):
    s = ffi.new("gnss_state_t *")
    lib.gnss_state_init(s)
    return s
