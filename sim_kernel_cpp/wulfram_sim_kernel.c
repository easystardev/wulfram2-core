/* ============================================================================
 * wulfram_sim_kernel.c  --  native port of rotation.py.
 *
 * Every function here mirrors the matching function in
 * shared/wulfram2_protocol/sim_kernel/rotation.py. Read the two side by side;
 * the line-for-line correspondence IS the spec. Build with -ffp-contract=off
 * and WITHOUT -ffast-math (see build.ps1) or the FMA/excess-precision will
 * break the last-bit parity.
 * ==========================================================================*/
#include "wulfram_sim_kernel.h"
#include <math.h>

/* --------------------------------------------------------------------------
 * wf_f32: round-trip a double through float32.
 *
 * `volatile` forces an actual store-to-float + load, so the rounding to single
 * precision really happens regardless of what the optimizer would prefer to
 * keep in a wider register. This is the C analogue of rotation.py's
 * _f32_buf[0] = value; return _f32_buf[0].
 * ------------------------------------------------------------------------*/
float wf_f32(double value) {
    volatile float q = (float)value;
    return q;
}

/* F32_TWO_PI: float32(6.2831855), the exact single-precision 2*pi the original
 * client uses for angle wrapping. */
static const float WF_F32_TWO_PI = 6.2831855f;

/* --------------------------------------------------------------------------
 * wf_normalize_angle_client: mirrors normalize_angle_client (rotation.py).
 *
 * Discipline: carry `a` in double and round with wf_f32() at exactly the points
 * the Python does (entry, and each loop add/subtract). The float32 boundary is
 * therefore explicit in the source rather than dependent on the optimizer.
 * ------------------------------------------------------------------------*/
float wf_normalize_angle_client(double angle) {
    double a = wf_f32(angle);
    if (a > 20000.0 || a < -20000.0) return 0.0f;
    while (a < 0.0)           a = wf_f32(a + WF_F32_TWO_PI);
    while (a > WF_F32_TWO_PI) a = wf_f32(a - WF_F32_TWO_PI);
    return (float)a;
}

/* --------------------------------------------------------------------------
 * wf_matrix3_from_euler_xyz: R = Rz * Ry * Rx, all in float64.
 * Mirrors matrix3_from_euler_xyz (rotation.py:61).
 * ------------------------------------------------------------------------*/
void wf_matrix3_from_euler_xyz(double ex, double ey, double ez, double out9[9]) {
    double cx = cos(ex), sx = sin(ex);
    double cy = cos(ey), sy = sin(ey);
    double cz = cos(ez), sz = sin(ez);

    out9[0] = cz * cy;
    out9[1] = cz * sy * sx - sz * cx;
    out9[2] = sz * sx + cz * cx * sy;
    out9[3] = sz * cy;
    out9[4] = sy * sx * sz + cz * cx;
    out9[5] = sy * cx * sz - cz * sx;
    out9[6] = -sy;
    out9[7] = cy * sx;
    out9[8] = cx * cy;
}

/* --------------------------------------------------------------------------
 * wf_matrix3_from_axis_angle: Rodrigues. sqrt/cos/sin at float64, everything
 * else float32. Mirrors matrix3_from_axis_angle (rotation.py:92).
 * ------------------------------------------------------------------------*/
void wf_matrix3_from_axis_angle(double omega_x, double omega_y, double omega_z,
                                float out9[9]) {
    /* angle_sq stays float64 (the reference never f32's it); only `angle` and
     * the algebra below drop to float32. */
    double angle_sq = omega_x * omega_x + omega_y * omega_y + omega_z * omega_z;
    double angle_f64 = sqrt(angle_sq);
    float angle = wf_f32(angle_f64);

    /* Original source threshold is `<= 1e-05`. 1e-05 is not float32-
     * representable, so `<=` collapses to `<` for any float32 angle; we keep
     * `<=` for source fidelity. DIVERGENCE: the isfinite() guard mirrors the
     * Python oracle -- an intentional safety extension beyond the original,
     * which would emit a NaN matrix on a non-finite angle. */
    if (!isfinite(angle_f64) || (double)angle <= 1e-05) {
        out9[0] = 1.0f; out9[1] = 0.0f; out9[2] = 0.0f;
        out9[3] = 0.0f; out9[4] = 1.0f; out9[5] = 0.0f;
        out9[6] = 0.0f; out9[7] = 0.0f; out9[8] = 1.0f;
        return;
    }

    float inv_len = wf_f32(1.0 / (double)angle);
    float nx = wf_f32((double)omega_x * (double)inv_len);
    float ny = wf_f32((double)omega_y * (double)inv_len);
    float nz = wf_f32((double)omega_z * (double)inv_len);

    float c = wf_f32(cos(angle_f64));
    float s = wf_f32(sin(angle_f64));
    float t = wf_f32(1.0 - (double)c);

    float t_nx = wf_f32((double)nx * (double)t);
    float t_ny = wf_f32((double)ny * (double)t);
    float t_nz = wf_f32((double)nz * (double)t);

    out9[0] = wf_f32((double)wf_f32((double)nx * (double)t_nx) + (double)c);
    out9[1] = wf_f32((double)wf_f32((double)ny * (double)t_nx) + (double)wf_f32((double)nz * (double)s));
    out9[2] = wf_f32((double)wf_f32((double)t_nx * (double)nz) - (double)wf_f32((double)ny * (double)s));
    out9[3] = wf_f32((double)wf_f32((double)t_ny * (double)nx) - (double)wf_f32((double)nz * (double)s));
    out9[4] = wf_f32((double)wf_f32((double)ny * (double)t_ny) + (double)c);
    out9[5] = wf_f32((double)wf_f32((double)t_ny * (double)nz) + (double)wf_f32((double)nx * (double)s));
    out9[6] = wf_f32((double)wf_f32((double)nx * (double)t_nz) + (double)wf_f32((double)ny * (double)s));
    out9[7] = wf_f32((double)wf_f32((double)ny * (double)t_nz) - (double)wf_f32((double)nx * (double)s));
    out9[8] = wf_f32((double)wf_f32((double)nz * (double)t_nz) + (double)c);
}

/* --------------------------------------------------------------------------
 * wf_extract_euler_angles: atan2 euler extraction.
 * Mirrors extract_euler_angles (rotation.py:144).
 * ------------------------------------------------------------------------*/
void wf_extract_euler_angles(const double m[9], float out3[3]) {
    float fm0 = wf_f32(m[0]);
    float fm1 = wf_f32(m[1]);
    float fm3 = wf_f32(m[3]);
    float fm6 = wf_f32(m[6]);
    float fm7 = wf_f32(m[7]);
    float fm8 = wf_f32(m[8]);

    /* gimbal = sqrt(fm0^2 + fm1^2), computed at float64. */
    double gimbal = sqrt((double)fm0 * (double)fm0 + (double)fm1 * (double)fm1);

    if (gimbal <= 1.9073486328125e-06) { /* 2^-19 */
        out3[0] = wf_f32(atan2((double)fm7, (double)fm8));
        out3[1] = wf_f32(atan2(-(double)fm6, gimbal));
        out3[2] = 0.0f;
    } else {
        out3[0] = wf_f32(atan2((double)fm7, (double)fm8));
        out3[1] = wf_f32(atan2(-(double)fm6, gimbal));
        out3[2] = wf_f32(atan2((double)fm3, (double)fm0));
    }
}
