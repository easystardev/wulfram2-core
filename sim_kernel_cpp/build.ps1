# Build the native sim kernel to a DLL with clang (LLVM).
# Float-control flags are part of CORRECTNESS, not optimization:
#   -ffp-contract=off : never fuse a*b+c into an FMA (would change the last bit)
#   (no -ffast-math)  : keep IEEE semantics so results match the Python kernel
[CmdletBinding()]
param(
    [string]$Clang = "C:\Program Files\LLVM\bin\clang.exe",
    [switch]$DebugBuild
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $here "wulfram_sim_kernel.c"
$out  = Join-Path $here "wulfram_sim_kernel.dll"

if (-not (Test-Path $Clang)) { throw "clang not found at $Clang -- pass -Clang <path>" }

$opt = if ($DebugBuild) { "-O0", "-g" } else { "-O2" }
$flags = @("-shared", "-ffp-contract=off") + $opt

Write-Host "clang $($flags -join ' ') -o $out $src"
& $Clang @flags -o $out $src
if ($LASTEXITCODE -ne 0) { throw "build failed ($LASTEXITCODE)" }
Write-Host "OK -> $out"
