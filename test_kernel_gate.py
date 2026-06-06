"""Verify the WULFRAM_NATIVE_KERNEL backend gate.

Run twice:
  uv run python test_kernel_gate.py                       # expects python
  $env:WULFRAM_NATIVE_KERNEL=1; uv run python test_kernel_gate.py   # expects native

Asserts (1) the active backend matches the env var, and (2) the gated functions
are bit-for-bit identical to the pure-Python oracle (so flipping the gate cannot
change results). The env must be set BEFORE import, which is why this is a
separate process per backend.
"""

import os
import struct
import sys

from wulfram2_protocol import sim_kernel
from wulfram2_protocol.sim_kernel import rotation as py


def _fb(x):
    return struct.pack("<f", x)


def _dll_loads() -> bool:
    try:
        import importlib
        importlib.import_module("wulfram2_protocol.sim_kernel.native")
        return True
    except Exception:
        return False


def main() -> int:
    env = os.environ.get("WULFRAM_NATIVE_KERNEL", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        expected = "python"
    elif env == "":
        # Default: prefer native, fall back to python only if the DLL won't load.
        expected = "native" if _dll_loads() else "python"
    else:
        expected = "native"
    if sim_kernel.KERNEL_BACKEND != expected:
        print(f"  FAIL  backend={sim_kernel.KERNEL_BACKEND!r} expected {expected!r}")
        return 1

    # Gated functions must match the python oracle bit-for-bit.
    fails = []
    for ang in [0.1, -0.1, 7.0, -100.0, 3.5, 6.2831856]:
        if _fb(sim_kernel.normalize_angle_client(ang)) != _fb(py.normalize_angle_client(ang)):
            fails.append(f"normalize({ang})")
    if _fb(sim_kernel.f32(6.2831855)) != _fb(py.f32(6.2831855)):
        fails.append("f32")
    for axis in [(0.1, -0.2, 0.3), (1.0, 2.0, 3.0)]:
        a = sim_kernel.matrix3_from_axis_angle(*axis)
        b = py.matrix3_from_axis_angle(*axis)
        if any(_fb(x) != _fb(y) for x, y in zip(a, b)):
            fails.append(f"axis_angle{axis}")
    m = py.matrix3_from_euler_xyz(0.1, 0.2, 0.3)
    if any(_fb(x) != _fb(y) for x, y in zip(
        sim_kernel.extract_euler_angles(m), py.extract_euler_angles(m))):
        fails.append("extract")

    if fails:
        print(f"  FAIL  backend={sim_kernel.KERNEL_BACKEND} diverges from python oracle: {fails}")
        return 1

    print(f"  PASS  backend={sim_kernel.KERNEL_BACKEND} (gated, bit-exact vs python oracle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
