/* ============================================================================
 * wulfram_sim_kernel.h  --  C ABI for the native sim kernel.
 *
 * This is the C port of shared/wulfram2_protocol/sim_kernel/rotation.py.
 * Contract: bit-for-bit identical results to that Python module, which is
 * itself byte-exact against the captured original-client corpus. Match the
 * Python, and parity to the original Wulfram II client follows.
 *
 * Precision discipline (the whole ballgame):
 *   - `double` is used everywhere the Python uses native float64: the
 *     euler->matrix trig, and the sqrt/cos/sin inside the Rodrigues path.
 *   - `float` (via wf_f32) is used everywhere the Python calls f32().
 * Matrices are row-major. Euler order is XYZ (X=roll, Y=pitch, Z=heading).
 * ==========================================================================*/
#ifndef WULFRAM_SIM_KERNEL_H
#define WULFRAM_SIM_KERNEL_H

#ifdef __cplusplus
extern "C" {
#endif

#ifdef _WIN32
#define WF_API __declspec(dllexport)
#else
#define WF_API __attribute__((visibility("default")))
#endif

/* Round-trip a double through float32 (matches rotation.py f32()). */
WF_API float wf_f32(double value);

/* Normalize angle to [0, 2*pi] (matches normalize_angle_client). */
WF_API float wf_normalize_angle_client(double angle);

/* Euler XYZ -> 3x3 row-major matrix. Trig at float64; out is 9 DOUBLES. */
WF_API void wf_matrix3_from_euler_xyz(double ex, double ey, double ez,
                                      double out9[9]);

/* Axis-angle (Rodrigues) -> 3x3 row-major matrix. out is 9 FLOATS.
 * Inputs are DOUBLE: the reference keeps omega at full float64 (angle_sq is not
 * f32'd, and raw omega feeds nx = f32(omega * inv_len)). */
WF_API void wf_matrix3_from_axis_angle(double omega_x, double omega_y,
                                       double omega_z, float out9[9]);

/* Extract euler XYZ (roll,pitch,heading) from a 3x3 matrix. out is 3 FLOATS.
 * Returns RAW float32 euler (NOT normalized), matching extract_euler_angles. */
WF_API void wf_extract_euler_angles(const double m[9], float out3[3]);

#ifdef __cplusplus
}
#endif

#endif /* WULFRAM_SIM_KERNEL_H */
