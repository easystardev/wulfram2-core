# Native sim kernel (C port of `sim_kernel/rotation.py`)

A bit-exact C port of the deterministic rotation/attitude kernel. The Python
kernel is byte-exact against the captured original-client corpus; this kernel's
contract is **bit-for-bit equality with the Python kernel**, so parity to the
original Wulfram II client follows transitively.

## Why this exists
- **Kills the `_f32()` bug class.** In Python every single-precision step needs a
  manual `f32()` round-trip; one missed call silently diverges. In C, `float` is
  `float` and the discipline is structural.
- **A stronger oracle.** Once it matches Python, the C kernel can be
  differential-tested directly against the original binary's functions.
- **One source for both worlds.** Bound back into the Python server/client via
  ctypes (`sim_kernel/native.py`), so a future C++ client and the current Python
  server share the exact same math.

Paths below are relative to this submodule's root (`shared/` in the superproject).

## Build
```pwsh
pwsh sim_kernel_cpp/build.ps1            # -> wulfram_sim_kernel.dll
```
clang (LLVM) is at `C:\Program Files\LLVM\bin\clang.exe`. The flags
`-ffp-contract=off` and "no `-ffast-math`" are **correctness** flags: they stop
the compiler from fusing `a*b+c` into an FMA or keeping intermediates wide, which
would change the last mantissa bit and break parity.

## Test (the feedback loop)
```pwsh
uv run python test_native_kernel_parity.py
```
Compares exact IEEE-754 byte patterns (not approximate floats) across hundreds of
seeded + edge-case inputs for all five functions.

## Why bit-exact is even reachable
clang here targets `x86_64-pc-windows-msvc`, so it links the **UCRT**. CPython on
Windows also uses the UCRT, so `cos/sin/sqrt/atan2` are the *same* library
functions in both kernels -- the transcendental results match to the bit.

---

## Fidelity audit (2026-06-06)

Re-audit of every kernel function against the original client's known behavior.
Two-link chain: **C == Python** (the bit-exact parity test, 5/5) and
**Python == original** (this audit, plus the byte-exact corpus). Result: faithful
on the entire finite input domain, with the divergences below explicitly recorded.

| Function | Verdict |
|---|---|
| `wf_f32` | faithful by construction (implicit single-precision store rounding) |
| `wf_normalize_angle_client` | exact; clamp/fall-through equivalent to early-return |
| `wf_matrix3_from_euler_xyz` | exact op-order (9/9); precision-bounded (see below) |
| `wf_matrix3_from_axis_angle` | exact op-order (9/9 + normalize); threshold + guard notes below |
| `wf_extract_euler_angles` | exact (both branches, threshold `<=`, double-cast on pitch) |

**Threshold `<=` vs `<` (axis-angle).** The original source is `<= 1e-05`. We use
`<=` for source fidelity, but it is provably a no-op: `1e-05` is not
float32-representable, so the `== 1e-05` arm is unsatisfiable for any float32
angle and `<=` collapses to `<`. Output is identical either way.

**DIVERGENCE (intentional safety extension): the `isfinite` guard.** On a
non-finite angle the original would emit a NaN-laden matrix; both our kernels
return identity instead (Python *needs* this -- `math.cos(inf)` raises; C does
not, but mirrors Python for parity). Affects only inputs outside the original's
valid domain. Regression: `test_attitude_finite.py`.

**DIVERGENCE (platform-bounded, cannot be closed on x64/MSVC).**
- The original carries trig + euler-matrix products in an extended-precision
  intermediate wider than float64, truncating to `double` on store.
  `x86_64-pc-windows-msvc` has no such type (`long double == double`), so we use
  `double`. The residual is below the float32 extraction that always follows, and
  is corpus-validated.
- The algebraic matrix products, by contrast, were per-op float32 in the original
  -- reproduced *exactly* by our `wf_f32()`-per-subproduct.
- Reproducing the exact extended/single *mix* would require a 32-bit
  extended-precision build, which would over-widen the per-op-float32 algebra.
  Not worth regressing the proven path.

## Design note: float32 discipline (`wf_normalize_angle_client` et al.)

All functions use the **"`double` + explicit `wf_f32()` at every rounding point"**
discipline: intermediates are carried in `double`, and we round to float32 only
at the exact points the original does. This was a deliberate choice over the
leaner "declare `float`, trust per-op SSE rounding" alternative -- it makes the
float32 boundary a visible fact in the source rather than a property of the build
flags, so a clone's fidelity is verifiable by reading, and `-ffp-contract`
regressions can't silently corrupt it. The bit-exact parity test is the backstop
either way.

Kernel is 5/5 bit-exact and fidelity-audited (see section above). Next step:
wire `native.py` into the server/client physics adapters behind an env gate
(`WULFRAM_NATIVE_KERNEL=1`), with `rotation.py` as the fallback/reference.
