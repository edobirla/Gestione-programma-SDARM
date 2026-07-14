# Finds a Windows x64 (AMD64) Python 3.11-3.13 interpreter and prints its
# full path — used by build_windows.bat. An x64 build is required even on a
# Windows-on-ARM machine (Snapdragon/Copilot+ PC): x64 apps run everywhere
# (natively on Intel/AMD, via emulation on ARM), but an ARM64-compiled app
# runs ONLY on ARM64 Windows — the wrong default for something meant to be
# distributed to other church PCs. Prints nothing if no x64 3.11-3.13 is found.
#
# Preference order 3.13 > 3.12 > 3.11 (checked against python.org's Windows
# downloads page in 2026-07): Python 3.12 no longer ships a Windows
# installer at all (source-only "security fixes only" maintenance since
# 3.12.10) and 3.14 has no pygame wheel yet (see build_windows.bat) — 3.13
# is the only currently-downloadable version confirmed to have a prebuilt
# pygame wheel for Windows x64. 3.12/3.11 are still tried first-if-already-
# installed (nothing wrong with a machine that already has one), just not
# the one this script's own error message tells people to go download.

$candidates = @{}
try { $lines = & py -0p 2>$null } catch { $lines = $null }
if ($lines) {
    foreach ($line in $lines) {
        if ($line -match '(?i)arm64') { continue }
        if ($line -match '3\.(11|12|13)\b') {
            $ver = "3." + $Matches[1]
            if ($line -match '(?<path>[A-Za-z]:\\.*?python\.exe)') {
                if (-not $candidates.ContainsKey($ver)) {
                    $candidates[$ver] = $Matches.path
                }
            }
        }
    }
}

$best = $null
foreach ($v in '3.13', '3.12', '3.11') {
    if ($candidates.ContainsKey($v)) { $best = $candidates[$v]; break }
}

if (-not $best) {
    $p = Get-Command python -ErrorAction SilentlyContinue
    # Skip the Microsoft Store's "python" app-execution-alias stub (lives
    # under WindowsApps) — running it with -c either no-ops or pops the
    # Store open instead of actually executing Python.
    if ($p -and $p.Source -notmatch '(?i)WindowsApps') {
        try {
            $info = & $p.Source -c "import sys,platform; print(platform.machine()); print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { $info = $null }
        if ($info) {
            $parts = $info -split "`r?`n" | Where-Object { $_ -ne '' }
            if ($parts.Count -ge 2) {
                $machine = $parts[0]; $ver = $parts[1]
                if (($machine -notmatch '(?i)arm64') -and (@('3.11', '3.12', '3.13') -contains $ver)) {
                    $best = $p.Source
                }
            }
        }
    }
}

if ($best) { Write-Output $best }
