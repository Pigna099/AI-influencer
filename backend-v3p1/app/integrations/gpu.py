"""Live GPU telemetry for the playground: NVML metrics plus host process mapping.

The API container runs with `gpus: all` and `pid: host`, so NVML sees the four
GPUs and /proc exposes the host processes (Ollama runners, ComfyUI).
"""

import re

import httpx

from ..config import settings

DIGEST_PATTERN = re.compile(r"sha256-([0-9a-f]{64})")


def _cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return handle.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _ollama_names() -> dict[str, str]:
    try:
        response = httpx.get(f"{settings.ollama_url}/api/tags", timeout=3)
        response.raise_for_status()
        return {
            model["digest"]: model["name"]
            for model in response.json().get("models", [])
            if model.get("digest")
        }
    except (httpx.HTTPError, KeyError, TypeError):
        return {}


def _ollama_loaded() -> list[tuple[str, int]]:
    try:
        response = httpx.get(f"{settings.ollama_url}/api/ps", timeout=3)
        response.raise_for_status()
        return [
            (model["name"], int(model.get("size_vram") or model.get("size") or 0))
            for model in response.json().get("models", [])
        ]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return []


def _assign_loaded_names(gpus: list[dict]) -> None:
    """A runner blob digest is a layer digest, not the manifest digest of /api/tags.
    Loaded models expose their total VRAM in /api/ps, so match each runner process
    to the closest loaded model by summed VRAM."""
    totals: dict[int, int] = {}
    for gpu in gpus:
        for process in gpu["processes"]:
            if process["kind"] == "ollama":
                totals[process["pid"]] = totals.get(process["pid"], 0) + process["vram"]
    candidates = [(name, size) for name, size in _ollama_loaded() if size > 0]
    used: set[int] = set()
    assignment: dict[int, str] = {}
    for pid, total in sorted(totals.items(), key=lambda item: -item[1]):
        best_index, best_diff = None, None
        for index, (_, size) in enumerate(candidates):
            if index in used:
                continue
            diff = abs(size - total) / size
            if best_diff is None or diff < best_diff:
                best_index, best_diff = index, diff
        if best_index is not None and best_diff is not None and best_diff < 0.4:
            used.add(best_index)
            assignment[pid] = candidates[best_index][0]
    for gpu in gpus:
        for process in gpu["processes"]:
            if process["pid"] in assignment:
                process["name"] = assignment[process["pid"]]


def _process_label(pid: int, names: dict[str, str]) -> tuple[str, str]:
    cmdline = _cmdline(pid)
    match = DIGEST_PATTERN.search(cmdline)
    if match and ("llama-server" in cmdline or "ollama" in cmdline):
        return names.get(match.group(1), f"ollama:{match.group(1)[:10]}"), "ollama"
    if "comfy" in cmdline.lower() or ("main.py" in cmdline and "listen" in cmdline):
        return "ComfyUI", "comfyui"
    first = cmdline.split(" ")[0].rsplit("/", 1)[-1] if cmdline else ""
    return first or f"pid {pid}", "process"


def _decode(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def gpu_status() -> dict:
    try:
        import pynvml

        pynvml.nvmlInit()
    except Exception as error:  # noqa: BLE001 - NVML is optional; report instead of failing the API
        return {"available": False, "error": str(error)[:200], "gpus": []}
    names = _ollama_names()
    gpus = []
    try:
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            try:
                power = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000, 1)
                power_limit = round(pynvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000, 1)
            except pynvml.NVMLError:
                power, power_limit = None, None
            try:
                temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except pynvml.NVMLError:
                temperature = None
            processes = []
            try:
                running = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
            except (pynvml.NVMLError, AttributeError):
                running = []
            for process in running:
                name, kind = _process_label(process.pid, names)
                processes.append(
                    {
                        "pid": process.pid,
                        "name": name,
                        "kind": kind,
                        "vram": process.usedGpuMemory or 0,
                    }
                )
            gpus.append(
                {
                    "index": index,
                    "name": _decode(pynvml.nvmlDeviceGetName(handle)),
                    "memory_total": memory.total,
                    "memory_used": memory.used,
                    "memory_free": memory.free,
                    "utilization": utilization.gpu,
                    "memory_utilization": utilization.memory,
                    "power_watts": power,
                    "power_limit": power_limit,
                    "temperature": temperature,
                    "processes": processes,
                }
            )
    finally:
        pynvml.nvmlShutdown()
    _assign_loaded_names(gpus)
    return {"available": True, "gpus": gpus}
