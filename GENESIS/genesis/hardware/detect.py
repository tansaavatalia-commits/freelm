"""Read-only hardware detection using only the standard library.

Nothing here changes the system. Windows values come from read-only APIs
(``GlobalMemoryStatusEx``) and registry keys opened for reading; Linux values
from ``/proc`` and ``/sys``. Whatever cannot be read is reported as ``None``
with an explanation in ``notes`` — never guessed.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MB = 1024 * 1024
GB = 1024 * MB
PCI_VENDORS = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel", "0x1af4": "Virtio", "0x15ad": "VMware"}
_WIN_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


@dataclass(frozen=True)
class GPU:
    name: str
    vram_mb: int | None


@dataclass(frozen=True)
class HardwareInfo:
    os_name: str
    os_release: str
    os_version: str
    machine: str
    python: str
    cpu_model: str | None
    cpu_logical: int | None
    ram_total_mb: int | None
    ram_available_mb: int | None
    disk_path: str
    disk_total_gb: float | None
    disk_free_gb: float | None
    gpus: tuple[GPU, ...] | None  # None = could not be detected; () = detected, none present
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def max_vram_mb(self) -> int:
        return max((g.vram_mb or 0 for g in self.gpus or ()), default=0)


def detect(disk_path: Path | str | None = None) -> HardwareInfo:
    system = platform.system()
    if system == "Windows":
        ram, cpu, gpus = _win_memory(), _win_cpu(), _win_gpus()
    elif system == "Linux":
        ram, cpu, gpus = _linux_memory(), _linux_cpu(), _linux_gpus()
    elif system == "Darwin":
        total = _sysctl("hw.memsize")
        ram = (int(total) // MB if total and total.isdigit() else None, None)
        cpu, gpus = _sysctl("machdep.cpu.brand_string"), None
    else:
        ram, cpu, gpus = (None, None), None, None
    disk_total, disk_free, where = _disk(disk_path)
    notes = []
    if ram[0] is None:
        notes.append("RAM non rilevata su questo sistema")
    if cpu is None:
        notes.append("modello di CPU non rilevato")
    if gpus is None:
        notes.append("GPU non rilevata (rilevamento non disponibile o non permesso)")
    if disk_total is None:
        notes.append("spazio su disco non rilevato")
    return HardwareInfo(
        os_name=system or "unknown",
        os_release=platform.release(),
        os_version=platform.version(),
        machine=platform.machine(),
        python=platform.python_version(),
        cpu_model=cpu,
        cpu_logical=os.cpu_count(),
        ram_total_mb=ram[0],
        ram_available_mb=ram[1],
        disk_path=where,
        disk_total_gb=disk_total,
        disk_free_gb=disk_free,
        gpus=gpus,
        notes=tuple(notes),
    )


def _disk(path: Path | str | None) -> tuple[float | None, float | None, str]:
    p = Path(path) if path else Path.home()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        usage = shutil.disk_usage(p)
    except OSError:
        return None, None, str(p)
    return round(usage.total / GB, 1), round(usage.free / GB, 1), str(p)


# -- Windows ---------------------------------------------------------------------


def _win_memory() -> tuple[int | None, int | None]:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
            return None, None
    except (AttributeError, OSError):
        return None, None
    return int(stat.ullTotalPhys // MB), int(stat.ullAvailPhys // MB)


def _win_cpu() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip() or None
    except OSError:
        return None


def _win_gpus() -> tuple[GPU, ...] | None:
    import winreg

    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WIN_DISPLAY_CLASS)
    except OSError:
        return None
    gpus: list[GPU] = []
    with root:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not sub.isdigit():  # skips "Properties" and similar
                continue
            try:
                with winreg.OpenKey(root, sub) as key:
                    name = str(winreg.QueryValueEx(key, "DriverDesc")[0])
                    gpus.append(GPU(name, _win_vram(key)))
            except OSError:
                continue
    return tuple(gpus)


def _win_vram(key: Any) -> int | None:
    import winreg

    for value_name in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
        try:
            raw = winreg.QueryValueEx(key, value_name)[0]
        except OSError:
            continue
        if isinstance(raw, bytes):
            raw = int.from_bytes(raw[:8], "little")
        try:
            return int(raw) // MB or None
        except (TypeError, ValueError):
            return None
    return None


# -- Linux -----------------------------------------------------------------------


def _linux_memory() -> tuple[int | None, int | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0])  # kB
    except OSError:
        return None, None
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    return (total // 1024 if total else None, available // 1024 if available else None)


def _linux_cpu() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key.strip() in ("model name", "Model", "Hardware") and value.strip():
                return value.strip()
    except OSError:
        pass
    return platform.processor() or None


def _linux_gpus() -> tuple[GPU, ...] | None:
    drm = Path("/sys/class/drm")
    if not drm.is_dir():
        return None
    gpus: list[GPU] = []
    for card in sorted(drm.iterdir()):
        if not re.fullmatch(r"card\d+", card.name):
            continue
        try:
            vendor = (card / "device" / "vendor").read_text().strip()
            device = (card / "device" / "device").read_text().strip()
        except OSError:
            continue
        try:
            vram: int | None = int((card / "device" / "mem_info_vram_total").read_text()) // MB or None
        except (OSError, ValueError):
            vram = None
        gpus.append(GPU(f"{PCI_VENDORS.get(vendor, vendor)} {device}", vram))
    return tuple(gpus)


# -- macOS -----------------------------------------------------------------------


def _sysctl(name: str) -> str | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None
