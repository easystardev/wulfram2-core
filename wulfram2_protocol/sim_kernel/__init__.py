"""Single shared copy of the deterministic simulation kernel.

This package holds the ONE canonical copy of the contract-surface sim math that
was previously duplicated across `server/wulfram/physics.py`,
`client/wulfram_client/simulation/physics.py`, and the `_shared` family in
`shared/wulfram2_protocol/entities.py`. Server and client now import thin
adapters over these functions so the two kernels can never silently diverge
during server iteration (precondition for using the clone as a server oracle —
see docs/precise-clone-goal-loop.md, GOAL CH1).

Determinism is the contract: every function operates in float32 (`f32`) exactly
where the original Wulfram II client does, so results are bit-for-bit
reproducible and comparable as exact IEEE-754 hex.

Backend gate (`WULFRAM_NATIVE_KERNEL`): import the gated names from THIS package
(`wulfram2_protocol.sim_kernel`), not from `.rotation` directly, and the backend
follows the env var:
  - unset / `0` / `false`  -> pure-Python `rotation` (default; no DLL needed)
  - any other value        -> native C kernel via `native` (requires the built
                              DLL; raises NativeKernelUnavailable if missing)
Both backends are bit-for-bit identical (enforced by test_native_kernel_parity),
so flipping the gate cannot change results -- it only swaps the implementation.
`KERNEL_BACKEND` reports the active choice ("python" | "native").
"""

import os as _os

_native_requested = _os.environ.get("WULFRAM_NATIVE_KERNEL", "").strip().lower() not in (
    "",
    "0",
    "false",
    "no",
    "off",
)

if _native_requested:
    # Opt-in: fail loudly (not silently to Python) if the DLL is unavailable, so
    # "I'm testing native" can never quietly mean "I'm still on Python".
    from . import native as _backend

    KERNEL_BACKEND = "native"
else:
    from . import rotation as _backend

    KERNEL_BACKEND = "python"

F32_TWO_PI = _backend.F32_TWO_PI
extract_euler_angles = _backend.extract_euler_angles
f32 = _backend.f32
matrix3_from_axis_angle = _backend.matrix3_from_axis_angle
matrix3_from_euler_xyz = _backend.matrix3_from_euler_xyz
normalize_angle_client = _backend.normalize_angle_client

__all__ = [
    "KERNEL_BACKEND",
    "F32_TWO_PI",
    "extract_euler_angles",
    "f32",
    "matrix3_from_axis_angle",
    "matrix3_from_euler_xyz",
    "normalize_angle_client",
]
