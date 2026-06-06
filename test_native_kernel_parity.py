"""Bit-exact parity: native C kernel vs the pure-Python reference kernel.

The Python kernel (sim_kernel/rotation.py) is byte-exact against the captured
original-client corpus, so it is the oracle here. The native kernel must
reproduce it bit-for-bit -- we compare exact IEEE-754 byte patterns, not
approximate floats.

Run:  uv run python shared/test_native_kernel_parity.py
(also importable as pytest test_* functions)
"""

import math
import struct
import sys

from wulfram2_protocol.sim_kernel import rotation as py
from wulfram2_protocol.sim_kernel import native as nv


def _f_bits(x):
    return struct.pack("<f", x)


def _d_bits(x):
    return struct.pack("<d", x)


def _seeded_floats(n, lo, hi, seed):
    """Deterministic pseudo-random floats (no Date/random dependency)."""
    out = []
    state = seed & 0xFFFFFFFF
    for _ in range(n):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        out.append(lo + (hi - lo) * (state / 0x7FFFFFFF))
    return out


ANGLE_CASES = [
    0.0, -0.0, 0.1, -0.1, 3.0, 6.0, 6.2831855, 6.2831856, 7.0, -7.0,
    100.0, -100.0, 6.5, -6.5, 19999.0, 20001.0, -20001.0, math.pi, -math.pi,
] + _seeded_floats(200, -50.0, 50.0, 1)


AXIS_CASES = [
    (0.0, 0.0, 0.0),
    (1e-6, 0.0, 0.0),
    (0.0, 0.0, 0.05),
    (0.1, -0.2, 0.3),
    (1.0, 2.0, 3.0),
    (float("inf"), 0.0, 0.0),
    (float("nan"), 0.0, 0.0),
] + list(zip(
    _seeded_floats(150, -2.0, 2.0, 2),
    _seeded_floats(150, -2.0, 2.0, 3),
    _seeded_floats(150, -2.0, 2.0, 4),
))


EULER_CASES = [
    (0.0, 0.0, 0.0),
    (0.1, 0.2, 0.3),
    (-0.5, 1.2, -2.1),
    (math.pi / 2, 0.0, 0.0),
] + list(zip(
    _seeded_floats(150, -3.2, 3.2, 5),
    _seeded_floats(150, -3.2, 3.2, 6),
    _seeded_floats(150, -3.2, 3.2, 7),
))


INTEGRATE_CASES = [
    # (pos, vel, acc, dt)
    ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0 / 30.0),
    ((100.0, 200.0, 3.377), (1.5, -0.5, 0.0), (0.2, -0.1, -9.8), 0.084),
    ((5183.0, 3072.0, 2.427), (0.0, 0.0, 0.0), (0.0, 0.0, 0.95), 0.084),
    ((-12.5, 7.25, 30.0), (-3.3, 2.2, -1.1), (0.5, -0.5, 0.5), 1.0 / 30.0),
] + list(zip(
    list(zip(_seeded_floats(120, -6000.0, 6000.0, 9),
             _seeded_floats(120, -6000.0, 6000.0, 10),
             _seeded_floats(120, 0.0, 60.0, 11))),
    list(zip(_seeded_floats(120, -50.0, 50.0, 12),
             _seeded_floats(120, -50.0, 50.0, 13),
             _seeded_floats(120, -50.0, 50.0, 14))),
    list(zip(_seeded_floats(120, -20.0, 20.0, 15),
             _seeded_floats(120, -20.0, 20.0, 16),
             _seeded_floats(120, -20.0, 20.0, 17))),
    _seeded_floats(120, 0.01, 0.12, 18),
))


def _check(name, fails, cond, detail):
    if not cond:
        fails.append(f"{name}: {detail}")


def test_f32():
    fails = []
    for v in _seeded_floats(300, -1e6, 1e6, 8) + [0.0, 1.0, math.pi, 1e-30, 1e30]:
        a, b = py.f32(v), nv.f32(v)
        _check("f32", fails, _f_bits(a) == _f_bits(b), f"{v!r}: py={a!r} nv={b!r}")
    assert not fails, "\n".join(fails)


def test_normalize_angle_client():
    fails = []
    for v in ANGLE_CASES:
        a, b = py.normalize_angle_client(v), nv.normalize_angle_client(v)
        _check("normalize", fails, _f_bits(a) == _f_bits(b),
               f"{v!r}: py={a!r} nv={b!r}")
    assert not fails, "\n".join(fails)


def test_matrix3_from_euler_xyz():
    fails = []
    for (ex, ey, ez) in EULER_CASES:
        a, b = py.matrix3_from_euler_xyz(ex, ey, ez), nv.matrix3_from_euler_xyz(ex, ey, ez)
        for i in range(9):
            _check("euler", fails, _d_bits(a[i]) == _d_bits(b[i]),
                   f"({ex},{ey},{ez})[{i}]: py={a[i]!r} nv={b[i]!r}")
    assert not fails, "\n".join(fails[:20])


def test_matrix3_from_axis_angle():
    fails = []
    for (ox, oy, oz) in AXIS_CASES:
        a, b = py.matrix3_from_axis_angle(ox, oy, oz), nv.matrix3_from_axis_angle(ox, oy, oz)
        for i in range(9):
            _check("axis", fails, _f_bits(a[i]) == _f_bits(b[i]),
                   f"({ox},{oy},{oz})[{i}]: py={a[i]!r} nv={b[i]!r}")
    assert not fails, "\n".join(fails[:20])


def test_extract_euler_angles():
    fails = []
    # Feed matrices produced by both generators (covers the realistic domain).
    mats = [py.matrix3_from_euler_xyz(*c) for c in EULER_CASES]
    mats += [list(py.matrix3_from_axis_angle(*c)) for c in AXIS_CASES]
    for m in mats:
        a, b = py.extract_euler_angles(m), nv.extract_euler_angles(m)
        for i in range(3):
            _check("extract", fails, _f_bits(a[i]) == _f_bits(b[i]),
                   f"m={m}[{i}]: py={a[i]!r} nv={b[i]!r}")
    assert not fails, "\n".join(fails[:20])


def test_integrate_verlet():
    fails = []
    for (pos, vel, acc, dt) in INTEGRATE_CASES:
        a = py.integrate_verlet(pos, vel, acc, dt)
        b = nv.integrate_verlet(pos, vel, acc, dt)
        for part in range(2):  # 0 = pos, 1 = vel
            for i in range(3):
                _check("integrate", fails, _f_bits(a[part][i]) == _f_bits(b[part][i]),
                       f"{(pos, vel, acc, dt)} part{part}[{i}]: "
                       f"py={a[part][i]!r} nv={b[part][i]!r}")
    assert not fails, "\n".join(fails[:20])


def main():
    tests = [
        ("f32", test_f32),
        ("normalize_angle_client", test_normalize_angle_client),
        ("matrix3_from_euler_xyz", test_matrix3_from_euler_xyz),
        ("matrix3_from_axis_angle", test_matrix3_from_axis_angle),
        ("extract_euler_angles", test_extract_euler_angles),
        ("integrate_verlet", test_integrate_verlet),
    ]
    rc = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            rc = 1
            print(f"  FAIL  {name}\n{e}")
    print("ALL BIT-EXACT" if rc == 0 else "PARITY MISMATCH")
    return rc


if __name__ == "__main__":
    sys.exit(main())
