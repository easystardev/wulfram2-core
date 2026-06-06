"""Single shared copy of the deterministic simulation kernel.

This package holds the ONE canonical copy of the contract-surface sim math that
was previously duplicated across `server/wulfram/physics.py`,
`client/wulfram_client/simulation/physics.py`, and the `_shared` family in
`shared/wulfram2_protocol/entities.py`. Server and client now import thin
adapters over these functions so the two kernels can never silently diverge
during server iteration (precondition for using the clone as a server oracle —
see docs/precise-clone-goal-loop.md, GOAL CH1).

Determinism is the contract: every function operates in float32 (`f32`) exactly
where the azurefishy decompile does, so results are bit-for-bit reproducible and
comparable as exact IEEE-754 hex.
"""

from .rotation import (
    F32_TWO_PI,
    extract_euler_angles,
    f32,
    matrix3_from_axis_angle,
    matrix3_from_euler_xyz,
    normalize_angle_client,
)

__all__ = [
    "F32_TWO_PI",
    "extract_euler_angles",
    "f32",
    "matrix3_from_axis_angle",
    "matrix3_from_euler_xyz",
    "normalize_angle_client",
]
