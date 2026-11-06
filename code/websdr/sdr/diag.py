"""Sample the host's health (CPU, memory, temperature, throttling, Wi-Fi) and the WebSDR's own processes for the diagnostics page."""

import os
import re
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path

import psutil

INTERVAL_S = 2.0
HISTORY = 900                               # samples kept: 30 min at INTERVAL_S

# Our processes, found by the file name of the script they run; the server is always this process.
PROCESSES = {"bridge": "iq_bridge.py", "engine": "engine.py", "ft8": "ft8_service.py"}

# vcgencmd get_throttled bits: now, and since boot.
THROTTLE_BITS = {0: "under-voltage", 1: "frequency capped", 2: "throttled", 3: "soft temperature limit"}
THROTTLE_SYSFS = Path("/sys/devices/platform/soc/soc:firmware/get_throttled")   # same bits, Pi kernels


def read_temp() -> float | None:
    """
    Read the CPU temperature.

    Returns:
        float | None: °C, or None where the OS doesn't report it (macOS)
    """
    temps = getattr(psutil, "sensors_temperatures", lambda: {})()
    for name in ("cpu_thermal", "coretemp", "k10temp", "soc_thermal"):
        if temps.get(name):
            return round(temps[name][0].current, 1)
    return None


def read_throttled() -> dict | None:
    """
    Read the Raspberry Pi's throttling flags.

    Returns:
        dict | None: {"now": [...], "since_boot": [...]} flag names, or None off a Pi
    """
    try:
        if THROTTLE_SYSFS.exists():         # works inside a container, where vcgencmd doesn't
            bits = int(THROTTLE_SYSFS.read_text().strip(), 16)
        elif shutil.which("vcgencmd"):
            out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2).stdout
            bits = int(out.strip().split("=")[1], 16)
        else:
            return None
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None
    return {"now": [n for b, n in THROTTLE_BITS.items() if bits >> b & 1],
            "since_boot": [n for b, n in THROTTLE_BITS.items() if bits >> (b + 16) & 1]}


def read_wifi() -> float | None:
    """
    Read the Wi-Fi signal level from /proc/net/wireless.

    Returns:
        float | None: dBm, or None without Wi-Fi or off Linux
    """
    path = Path("/proc/net/wireless")
    if not path.exists():
        return None
    for line in path.read_text().splitlines()[2:]:
        fields = re.split(r"\s+", line.strip())
        if len(fields) > 3:
            return float(fields[3].rstrip("."))
    return None


class Diagnostics:
    """A rolling history of host and process samples."""

    def __init__(self):
        """Start an empty history and prime psutil's CPU counters."""
        self.history: deque[dict] = deque(maxlen=HISTORY)
        self.procs: dict[int, psutil.Process] = {}
        psutil.cpu_percent()

    def processes(self) -> dict:
        """
        Find our processes and read their CPU and memory.

        Returns:
            dict: name -> {"pid", "cpu", "rss_mb"}, or None for a process that isn't running
        """
        pids = {name: None for name in PROCESSES}
        for p in psutil.process_iter(["pid", "cmdline"]):
            scripts = {os.path.basename(arg) for arg in (p.info["cmdline"] or [])[1:3]}
            for name, script in PROCESSES.items():
                if script in scripts and pids[name] is None:
                    pids[name] = p.info["pid"]
        pids["server"] = os.getpid()
        found = {}
        for name, pid in pids.items():
            found[name] = None
            if pid is None:
                continue
            proc = self.procs.setdefault(pid, psutil.Process(pid))
            try:
                found[name] = {"pid": pid, "cpu": round(proc.cpu_percent(), 1),
                               "rss_mb": round(proc.memory_info().rss / 2**20, 1)}
            except psutil.Error:
                pass
        alive = {v["pid"] for v in found.values() if v}
        self.procs = {pid: p for pid, p in self.procs.items() if pid in alive}
        return found

    def sample(self, app: dict) -> dict:
        """
        Take one sample and add it to the history.

        Args:
            app (dict): the server's own figures (listeners, stream rates, engine state)

        Returns:
            dict: the sample
        """
        mem = psutil.virtual_memory()
        s = {
            "t": round(time.time(), 1),
            "cpu": psutil.cpu_percent(),
            "load1": round(psutil.getloadavg()[0], 2),
            "mem_pct": mem.percent,
            "mem_used_mb": round((mem.total - mem.available) / 2**20),
            "mem_total_mb": round(mem.total / 2**20),
            "disk_pct": psutil.disk_usage("/").percent,
            "temp_c": read_temp(),
            "throttled": read_throttled(),
            "wifi_dbm": read_wifi(),
            "uptime_s": round(time.time() - psutil.boot_time()),
            "procs": self.processes(),
            **app,
        }
        self.history.append(s)
        return s

    def since(self, t: float) -> list[dict]:
        """
        Return the samples newer than a time.

        Args:
            t (float): Unix time; 0 for the whole history

        Returns:
            list[dict]: samples, oldest first
        """
        return [s for s in self.history if s["t"] > t]
