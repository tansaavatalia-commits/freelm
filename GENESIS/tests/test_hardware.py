from __future__ import annotations

import dataclasses
import platform

import pytest

from genesis.hardware.detect import GPU, HardwareInfo, detect
from genesis.hardware.profiles import select_profile

from .conftest import LITE_HW


def _hw(ram=None, gpus=()):
    return dataclasses.replace(LITE_HW, ram_total_mb=ram, gpus=gpus)


def test_detect_on_this_machine(tmp_path):
    hw = detect(tmp_path)
    assert hw.os_name == platform.system() and hw.python == platform.python_version()
    assert hw.cpu_logical is None or hw.cpu_logical >= 1
    assert hw.disk_total_gb is None or hw.disk_total_gb > 0
    assert isinstance(hw.to_dict(), dict)
    if platform.system() in ("Windows", "Linux"):
        assert hw.ram_total_mb and hw.ram_total_mb > 256
    if platform.system() == "Windows":
        assert hw.cpu_model and isinstance(hw.gpus, tuple)
    for note in hw.notes:
        assert isinstance(note, str) and note


@pytest.mark.parametrize("ram,gpus,expected", [
    (4096, (), "lite-4gb"),
    (None, None, "lite-4gb"),
    (8192, (GPU("Intel UHD", 128),), "standard"),
    (16384, (), "standard"),
    (32768, (GPU("NVIDIA RTX", 8192),), "gpu"),
    (8192, (GPU("NVIDIA RTX", 8192),), "standard"),  # VRAM alone is not enough
])
def test_automatic_profile(ram, gpus, expected):
    profile, reason = select_profile(_hw(ram, gpus))
    assert profile.name == expected and reason


def test_requested_profile_cannot_exceed_hardware():
    profile, reason = select_profile(_hw(4096), "gpu")
    assert profile.name == "lite-4gb" and "non lo supporta" in reason
    profile, _ = select_profile(_hw(32768, (GPU("NVIDIA", 8192),)), "lite-4gb")
    assert profile.name == "lite-4gb"  # asking for less is always allowed


def test_lite_profile_is_sequential_without_local_models():
    profile, _ = select_profile(LITE_HW)
    assert profile.max_workers == 1 and profile.max_parallel_online == 1 and not profile.local_models


def test_unknown_gpu_counts_as_none():
    assert HardwareInfo(**{**LITE_HW.to_dict(), "gpus": None}).max_vram_mb == 0
