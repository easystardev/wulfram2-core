"""Regression: the shared axis-angle attitude step must stay finite.

A degenerate/injected steep pose can overflow the tank's angular velocity to
inf/NaN. Before 2026-05-31, `_matrix3_from_axis_angle_shared` then computed an
infinite angle and `math.cos(inf)` raised `ValueError: math domain error`,
which the server tick loop caught per-tick (`[TICK] Client N Error: math domain
error`). The fix treats a non-finite axis-angle as identity (no rotation).

Run: `uv run python shared/test_attitude_finite.py`
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wulfram2_protocol.entities import _matrix3_from_axis_angle_shared  # noqa: E402

IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def test_non_finite_axis_angle_returns_identity() -> None:
    cases = [
        (math.inf, 0.0, 0.0),
        (0.0, math.inf, 0.0),
        (0.0, 0.0, math.inf),
        (math.nan, 0.0, 0.0),
        (-math.inf, math.inf, 0.0),
        (1e200, 1e200, 1e200),  # finite but squares overflow to inf
    ]
    for omega in cases:
        matrix = _matrix3_from_axis_angle_shared(*omega)
        assert matrix == IDENTITY, f"omega={omega} should be identity, got {matrix}"
        assert all(math.isfinite(v) for v in matrix), f"omega={omega} produced non-finite matrix"


def test_normal_axis_angle_still_rotates() -> None:
    matrix = _matrix3_from_axis_angle_shared(0.0, 0.0, 0.5)
    assert all(math.isfinite(v) for v in matrix)
    assert matrix != IDENTITY, "a real rotation must not collapse to identity"


if __name__ == "__main__":
    test_non_finite_axis_angle_returns_identity()
    test_normal_axis_angle_still_rotates()
    print("OK: attitude axis-angle finiteness regression passed")
