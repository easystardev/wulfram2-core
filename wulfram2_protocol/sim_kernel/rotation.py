"""Canonical rotation/attitude kernel — the single shared copy.

Reproduces the original Wulfram II client's EXACT angular integration primitives:
a 3x3 rotation matrix (row-major doubles) with axis-angle Rodrigues
construction, float32 matrix multiply, and atan2 euler extraction. Faithfulness
is verified empirically against captured original-client behavior (the byte-exact
regression corpus).

This module is the ONE place these function bodies live. `server/wulfram/
physics.py`, `client/wulfram_client/simulation/physics.py`, and the `_shared`
family in `shared/wulfram2_protocol/entities.py` are thin adapters over it.

Everything operates in float32 (`f32`) exactly where the original client does so
the kernel is bit-for-bit reproducible (exact IEEE-754 hex; the determinism
contract). Where the original carried a wider intermediate than float64 can
represent, this is noted inline as a documented divergence.
"""

import array as _array
import math

TWO_PI = 2.0 * math.pi

# Single module-global float32 round-trip buffer. The simulation is
# single-threaded (server tick loop / client prediction), so one shared buffer
# is correct and is the fastest float32 quantizer available.
_f32_buf = _array.array("f", [0.0])


def f32(value: float) -> float:
    """Round-trip a float through float32 to match the original client's single-precision storage."""
    _f32_buf[0] = value
    return _f32_buf[0]


# Float32 2*pi constant — the exact single-precision value the original client
# uses for angle wrapping.
F32_TWO_PI = f32(6.2831855)


def normalize_angle_client(angle: float) -> float:
    """Normalize angle to [0, 2*pi] matching the original client.

      - Safety clamp: |angle| > 20000 -> 0.0
      - Iterative add/subtract of 6.2831855f (float32 2*pi), all in float32.
    """
    angle = f32(angle)
    if angle > 20000.0 or angle < -20000.0:
        return 0.0
    while angle < 0.0:
        angle = f32(angle + F32_TWO_PI)
    while angle > F32_TWO_PI:
        angle = f32(angle - F32_TWO_PI)
    return angle


def matrix3_from_euler_xyz(ex: float, ey: float, ez: float) -> list:
    """Build a 3x3 rotation matrix from euler XYZ angles (row-major doubles).

    XYZ intrinsic order: R = Rz * Ry * Rx. Input: X=roll, Y=pitch, Z=heading.
    Output: 9-element row-major list of doubles, stored in the client's entity
    rotation matrix slot. Trig and products run at float64.

    DIVERGENCE (platform-bounded): the original carried the trig/products in an
    extended-precision intermediate wider than float64. That width is not
    available on this target, so float64 is used; the residual is below the
    float32 extraction that always follows, and is corpus-validated.

    Returns a *list* because callers (server VehiclePhysics._matrix) mutate the
    result in place during the matrix-multiply write-back.
    """
    cx = math.cos(ex)
    sx = math.sin(ex)
    cy = math.cos(ey)
    sy = math.sin(ey)
    cz = math.cos(ez)
    sz = math.sin(ez)

    return [
        cz * cy,                        # M[0]
        cz * sy * sx - sz * cx,         # M[1]
        sz * sx + cz * cx * sy,         # M[2]
        sz * cy,                        # M[3]
        sy * sx * sz + cz * cx,         # M[4]
        sy * cx * sz - cz * sx,         # M[5]
        -sy,                            # M[6]
        cy * sx,                        # M[7]
        cx * cy,                        # M[8]
    ]


def matrix3_from_axis_angle(omega_x: float, omega_y: float, omega_z: float) -> tuple:
    """Build a 3x3 rotation matrix from an axis-angle vector via Rodrigues.

    Input: axis-angle vector (3 float32). Angle = ||vector||, axis =
    vector/||vector||. Output: 9-element row-major tuple of float32 values.

    All algebraic arithmetic is per-op float32; sqrt/cos/sin run at float64 then
    cast to float32.

    DIVERGENCE (intentional safety extension): a degenerate pose can overflow
    omega to inf/NaN; sqrt then yields a non-finite angle and math.cos(inf)
    raises "math domain error". The original has no such guard and would emit a
    NaN matrix. An infinite/NaN axis-angle has no valid rotation, so we treat it
    (like a sub-threshold angle) as identity to keep the attitude step finite.
    Affects only inputs outside the original's valid domain.
    Regression: shared/test_attitude_finite.py.
    """
    angle_sq = omega_x * omega_x + omega_y * omega_y + omega_z * omega_z
    angle_f64 = math.sqrt(angle_sq)
    angle = f32(angle_f64)

    # Identity threshold. The original source uses `<= 1e-05`. 1e-05 is not
    # float32-representable, so for any float32 `angle` the `== 1e-05` arm is
    # unsatisfiable and `<=` collapses to `<` -- identical output, but we keep
    # `<=` to match the original source. The isfinite() guard is the intentional
    # safety extension documented above.
    if not math.isfinite(angle_f64) or angle <= 1e-05:
        return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)

    inv_len = f32(1.0 / angle)
    nx = f32(omega_x * inv_len)
    ny = f32(omega_y * inv_len)
    nz = f32(omega_z * inv_len)

    # cos/sin at float64, then cast to float32.
    c = f32(math.cos(angle_f64))
    s = f32(math.sin(angle_f64))
    t = f32(1.0 - c)  # 1 - cos(angle)

    # Rodrigues: R = cos*I + (1-cos)*n*nT + sin*skew(n)
    t_nx = f32(nx * t)
    t_ny = f32(ny * t)
    t_nz = f32(nz * t)

    return (
        f32(f32(nx * t_nx) + c),             # R[0]
        f32(f32(ny * t_nx) + f32(nz * s)),   # R[1]
        f32(f32(t_nx * nz) - f32(ny * s)),   # R[2]
        f32(f32(t_ny * nx) - f32(nz * s)),   # R[3]
        f32(f32(ny * t_ny) + c),             # R[4]
        f32(f32(t_ny * nz) + f32(nx * s)),   # R[5]
        f32(f32(nx * t_nz) + f32(ny * s)),   # R[6]
        f32(f32(ny * t_nz) - f32(nx * s)),   # R[7]
        f32(f32(nz * t_nz) + c),             # R[8]
    )


def extract_euler_angles(m) -> tuple:
    """Extract XYZ euler angles from a 3x3 rotation matrix via atan2.

    Reproduces the original client's euler extraction. atan2 arguments come from
    the matrix elements:
      euler_x (roll)    = atan2(M[7], M[8])
      euler_y (pitch)   = atan2(-M[6], sqrt(M[0]^2 + M[1]^2))
      euler_z (heading) = atan2(M[3], M[0])

    Gimbal lock: when sqrt(M[0]^2 + M[1]^2) <= 2^(-19), roll is set to 0.

    Returns RAW float32 euler values (NOT normalized to [0, 2*pi]); callers that
    need normalization apply `normalize_angle_client`.
    """
    fm0 = f32(m[0])
    fm1 = f32(m[1])
    fm3 = f32(m[3])
    fm6 = f32(m[6])
    fm7 = f32(m[7])
    fm8 = f32(m[8])

    # Gimbal-lock check: sqrt(M[0][0]^2 + M[1][0]^2).
    gimbal = math.sqrt(fm0 * fm0 + fm1 * fm1)

    if gimbal <= 1.9073486328125e-06:  # 2^(-19)
        euler_x = f32(math.atan2(fm7, fm8))
        euler_y = f32(math.atan2(-fm6, gimbal))
        euler_z = 0.0
    else:
        euler_x = f32(math.atan2(fm7, fm8))
        euler_y = f32(float(math.atan2(-fm6, gimbal)))  # extra double cast (matches original)
        euler_z = f32(math.atan2(fm3, fm0))

    return (euler_x, euler_y, euler_z)
