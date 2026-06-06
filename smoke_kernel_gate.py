"""Thorough smoke test for the WULFRAM_NATIVE_KERNEL gate (all modes).

The env var must be read at import time, so each case runs in a fresh subprocess.
Covers: default(=native when DLL present), forced python, forced native, truthy
aliases, the fallback-to-python-with-warning path, and the hard-fail path.

Run:  uv run python smoke_kernel_gate.py
"""

import subprocess
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent
BOGUS_DLL = str(SHARED / "sim_kernel_cpp" / "does_not_exist.dll")

CHILD = (
    "import warnings; warnings.simplefilter('always')\n"
    "from wulfram2_protocol import sim_kernel\n"
    "print('BACKEND=' + sim_kernel.KERNEL_BACKEND)\n"
)


def run(env_overrides):
    import os
    env = {k: v for k, v in os.environ.items()
           if k not in ("WULFRAM_NATIVE_KERNEL", "WULFRAM_SIM_KERNEL_DLL")}
    env["PYTHONPATH"] = str(SHARED)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", CHILD],
        capture_output=True, text=True, env=env,
    )


def backend_of(proc):
    for line in proc.stdout.splitlines():
        if line.startswith("BACKEND="):
            return line.split("=", 1)[1].strip()
    return None


CASES = [
    # (label, env, expect_backend or None, expect_fail, needle_in_stderr)
    ("default (unset) -> native", {}, "native", False, None),
    ("=0 -> python", {"WULFRAM_NATIVE_KERNEL": "0"}, "python", False, None),
    ("=false -> python", {"WULFRAM_NATIVE_KERNEL": "false"}, "python", False, None),
    ("=1 -> native", {"WULFRAM_NATIVE_KERNEL": "1"}, "native", False, None),
    ("=true -> native", {"WULFRAM_NATIVE_KERNEL": "true"}, "native", False, None),
    ("unset + bad DLL -> python+warn",
     {"WULFRAM_SIM_KERNEL_DLL": BOGUS_DLL}, "python", False, "native sim kernel unavailable"),
    ("=1 + bad DLL -> HARD FAIL",
     {"WULFRAM_NATIVE_KERNEL": "1", "WULFRAM_SIM_KERNEL_DLL": BOGUS_DLL},
     None, True, "NativeKernelUnavailable"),
]


def main() -> int:
    rc = 0
    for label, env, expect_backend, expect_fail, needle in CASES:
        proc = run(env)
        failed = proc.returncode != 0
        backend = backend_of(proc)
        ok = True
        detail = ""

        if expect_fail:
            if not failed:
                ok, detail = False, f"expected non-zero exit, got 0 (backend={backend})"
        else:
            if failed:
                ok, detail = False, f"unexpected failure rc={proc.returncode}: {proc.stderr.strip()[:200]}"
            elif backend != expect_backend:
                ok, detail = False, f"backend={backend!r} expected {expect_backend!r}"

        if ok and needle and needle not in proc.stderr:
            ok, detail = False, f"expected {needle!r} in stderr; got: {proc.stderr.strip()[:200]}"

        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))
        if not ok:
            rc = 1
    print("ALL GATE MODES OK" if rc == 0 else "GATE SMOKE FAILED")
    return rc


if __name__ == "__main__":
    sys.exit(main())
