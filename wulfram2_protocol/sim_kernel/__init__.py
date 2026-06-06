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
follows the env var (tri-state):
  - unset (DEFAULT)        -> PREFER native; fall back to pure-Python with a
                              RuntimeWarning if the DLL can't load (so a fresh
                              checkout / non-Windows host still imports).
  - `1` / `true` / etc.    -> REQUIRE native; raise NativeKernelUnavailable if
                              the DLL is missing (no silent fallback -- the
                              "I'm testing native" case).
  - `0` / `false` / `off`  -> force pure-Python `rotation` (no DLL needed).
Both backends are bit-for-bit identical (enforced by test_native_kernel_parity),
so the choice cannot change results -- it only swaps the implementation.
`KERNEL_BACKEND` reports the active choice ("python" | "native").
"""

import os as _os
import warnings as _warnings

_env = _os.environ.get("WULFRAM_NATIVE_KERNEL", "").strip().lower()

if _env in ("0", "false", "no", "off"):
    from . import rotation as _backend

    KERNEL_BACKEND = "python"
elif _env == "":
    # Default: prefer native, fall back to Python (with a visible warning) so the
    # kernel always imports even without a built DLL.
    try:
        from . import native as _backend

        KERNEL_BACKEND = "native"
    except Exception as _exc:  # NativeKernelUnavailable, OSError, etc.
        from . import rotation as _backend

        KERNEL_BACKEND = "python"
        _warnings.warn(
            f"native sim kernel unavailable ({_exc}); using pure-Python kernel. "
            "Build it with `pwsh shared/sim_kernel_cpp/build.ps1`, or set "
            "WULFRAM_NATIVE_KERNEL=0 to silence this warning.",
            RuntimeWarning,
            stacklevel=2,
        )
else:
    # Explicitly requested: fail loudly if the DLL is unavailable.
    from . import native as _backend

    KERNEL_BACKEND = "native"

F32_TWO_PI = _backend.F32_TWO_PI
extract_euler_angles = _backend.extract_euler_angles
f32 = _backend.f32
integrate_verlet = _backend.integrate_verlet
matrix3_from_axis_angle = _backend.matrix3_from_axis_angle
matrix3_from_euler_xyz = _backend.matrix3_from_euler_xyz
normalize_angle_client = _backend.normalize_angle_client

__all__ = [
    "KERNEL_BACKEND",
    "F32_TWO_PI",
    "extract_euler_angles",
    "f32",
    "integrate_verlet",
    "matrix3_from_axis_angle",
    "matrix3_from_euler_xyz",
    "normalize_angle_client",
]
