from __future__ import annotations

import pytest

from genesis.app import Genesis
from genesis.hardware.detect import HardwareInfo

# The owner's PC as described in the master prompt: Windows 10, 4 GB RAM.
LITE_HW = HardwareInfo(
    os_name="Windows", os_release="10", os_version="10.0.19045", machine="AMD64", python="3.13.0",
    cpu_model="Test CPU", cpu_logical=4, ram_total_mb=4096, ram_available_mb=1500,
    disk_path="C:\\", disk_total_gb=120.0, disk_free_gb=40.0, gpus=(), notes=(),
)


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    # Never touch the real data folder of whoever runs the tests.
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path / "default-home"))


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


@pytest.fixture
def app(home):
    g = Genesis(home, hardware=LITE_HW)
    yield g
    g.close()


def write_config(home, text: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "genesis.toml").write_text(text, encoding="utf-8")
