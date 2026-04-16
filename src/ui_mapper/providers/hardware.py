"""Hardware detection — GPU VRAM, system info."""

from __future__ import annotations
import subprocess
import platform
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """Detected GPU information."""
    name: str
    vram_mb: int
    driver_version: str = ""

    @property
    def vram_gb(self) -> float:
        return self.vram_mb / 1024


@dataclass
class SystemInfo:
    """System hardware summary."""
    os: str
    gpu: GPUInfo | None
    ram_gb: float
    recommended_model: str


def detect_gpu() -> GPUInfo | None:
    """Detect NVIDIA GPU and VRAM using nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            name = parts[0]
            vram_mb = int(float(parts[1]))
            driver = parts[2] if len(parts) > 2 else ""
            return GPUInfo(name=name, vram_mb=vram_mb, driver_version=driver)
    except FileNotFoundError:
        log.info("nvidia-smi not found — no NVIDIA GPU or drivers not installed")
    except Exception as e:
        log.warning(f"GPU detection failed: {e}")
    return None


def detect_system() -> SystemInfo:
    """Detect full system info and recommend best Ollama model."""
    from .ollama import OllamaProvider

    gpu = detect_gpu()
    vram_gb = gpu.vram_gb if gpu else 0

    # Get system RAM
    ram_gb = 0.0
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB"],
                capture_output=True, text=True, timeout=10,
            )
            ram_gb = float(result.stdout.strip())
        else:
            import os
            ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3)
    except Exception:
        pass

    recommended = OllamaProvider.recommend_model(vram_gb)

    return SystemInfo(
        os=f"{platform.system()} {platform.release()}",
        gpu=gpu,
        ram_gb=round(ram_gb, 1),
        recommended_model=recommended,
    )
