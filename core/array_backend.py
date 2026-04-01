"""
Thin numpy / CuPy abstraction for optional GPU acceleration.

All SCA engine code calls ``get_xp()`` instead of importing numpy directly.
When CuPy + CUDA is available and the user has enabled GPU mode, array
operations run on the GPU. Otherwise everything falls back to numpy.
"""

from __future__ import annotations

import numpy as np

try:
    import cupy as _cp  # type: ignore[import-untyped]
    _GPU_AVAILABLE: bool = _cp.cuda.runtime.getDeviceCount() > 0
    if _GPU_AVAILABLE:
        _GPU_DEVICE_NAME: str = _cp.cuda.runtime.getDeviceProperties(0)["name"].decode()
    else:
        _GPU_DEVICE_NAME = ""
except Exception:
    _cp = None
    _GPU_AVAILABLE = False
    _GPU_DEVICE_NAME = ""

_use_gpu: bool = _GPU_AVAILABLE


def get_xp():
    """Return the active array module (``cupy`` when GPU is enabled, else ``numpy``)."""
    if _use_gpu and _cp is not None:
        return _cp
    return np


def to_numpy(arr) -> np.ndarray:
    """Ensure *arr* is a plain ``numpy.ndarray`` (copies from GPU if needed)."""
    if hasattr(arr, "get"):
        return arr.get()
    return np.asarray(arr)


def gpu_available() -> bool:
    """Return ``True`` if CuPy detected a usable CUDA device."""
    return _GPU_AVAILABLE


def gpu_device_name() -> str:
    """Human-readable name of the first CUDA device, or ``""``."""
    return _GPU_DEVICE_NAME


def is_gpu_enabled() -> bool:
    """Return ``True`` if GPU mode is currently active."""
    return _use_gpu and _GPU_AVAILABLE


def set_gpu_enabled(enabled: bool) -> None:
    """Toggle GPU mode. Silently ignored when no CUDA device is present."""
    global _use_gpu
    _use_gpu = bool(enabled) and _GPU_AVAILABLE
