"""ctypes binding for the native (C) sim kernel.

Exposes the SAME API as `rotation.py` so the server/client adapters can swap
between the pure-Python kernel and the native one (e.g. behind an env gate).
The contract is bit-for-bit equality with `rotation.py` (itself byte-exact
against the captured original-client corpus); `shared/test_native_kernel_parity.py`
is the regression that enforces it.

Build the DLL first: `pwsh sim_kernel_cpp/build.ps1`.
Override the DLL path with WULFRAM_SIM_KERNEL_DLL if needed.
"""

import ctypes
import os
from pathlib import Path

_DLL_NAME = "wulfram_sim_kernel.dll"


def _resolve_dll_path() -> Path:
    override = os.environ.get("WULFRAM_SIM_KERNEL_DLL")
    if override:
        return Path(override)
    # native.py -> sim_kernel -> wulfram2_protocol -> <submodule root (shared/)>
    submodule_root = Path(__file__).resolve().parents[2]
    return submodule_root / "sim_kernel_cpp" / _DLL_NAME


_DLL_PATH = _resolve_dll_path()


class NativeKernelUnavailable(RuntimeError):
    """Raised when the native DLL is missing or fails to load."""


def _load():
    if not _DLL_PATH.exists():
        raise NativeKernelUnavailable(
            f"{_DLL_PATH} not found -- run `pwsh sim_kernel_cpp/build.ps1` first"
        )
    lib = ctypes.CDLL(str(_DLL_PATH))

    lib.wf_f32.restype = ctypes.c_float
    lib.wf_f32.argtypes = [ctypes.c_double]

    lib.wf_normalize_angle_client.restype = ctypes.c_float
    lib.wf_normalize_angle_client.argtypes = [ctypes.c_double]

    lib.wf_matrix3_from_euler_xyz.restype = None
    lib.wf_matrix3_from_euler_xyz.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
    ]

    lib.wf_matrix3_from_axis_angle.restype = None
    lib.wf_matrix3_from_axis_angle.argtypes = [
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.POINTER(ctypes.c_float),
    ]

    lib.wf_extract_euler_angles.restype = None
    lib.wf_extract_euler_angles.argtypes = [
        ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_float),
    ]
    return lib


_LIB = _load()


def f32(value: float) -> float:
    return float(_LIB.wf_f32(value))


def normalize_angle_client(angle: float) -> float:
    return float(_LIB.wf_normalize_angle_client(angle))


def matrix3_from_euler_xyz(ex: float, ey: float, ez: float) -> list:
    out = (ctypes.c_double * 9)()
    _LIB.wf_matrix3_from_euler_xyz(ex, ey, ez, out)
    return [out[i] for i in range(9)]


def matrix3_from_axis_angle(omega_x: float, omega_y: float, omega_z: float) -> tuple:
    out = (ctypes.c_float * 9)()
    _LIB.wf_matrix3_from_axis_angle(omega_x, omega_y, omega_z, out)
    return tuple(float(out[i]) for i in range(9))


def extract_euler_angles(m) -> tuple:
    arr = (ctypes.c_double * 9)(*[float(m[i]) for i in range(9)])
    out = (ctypes.c_float * 3)()
    _LIB.wf_extract_euler_angles(arr, out)
    return tuple(float(out[i]) for i in range(3))
