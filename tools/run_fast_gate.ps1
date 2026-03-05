<#
=== NON-PROGRAMMER GUIDE ===
Purpose: Automates the fast gate operational workflow for developers or operators.
How to follow: Read variables first, then each command block in order.
Inputs: Environment variables, script parameters, and local files.
Outputs: Console messages, changed files, or system configuration updates.
Safety notes: Run in a test environment before using on production systems.
=============================
#>
$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot | Join-Path -ChildPath ".")

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[FAIL] Python venv not found at $py"
    exit 1
}

New-Item -ItemType Directory -Force output\tmp, output\pytest_tmp | Out-Null
$env:TEMP = (Resolve-Path output\tmp).Path
$env:TMP = $env:TEMP

function Run-Step {
    param(
        [string]$Name,
        [string]$Command,
        [int]$TimeoutSec = 180
    )
    Write-Host ""
    Write-Host "=== $Name (timeout ${TimeoutSec}s) ==="
    $proc = Start-Process -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $Command) `
        -NoNewWindow -PassThru

    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill() } catch {}
        Write-Host "[FAIL] $Name timed out after ${TimeoutSec}s"
        exit 124
    }

    if ($proc.ExitCode -ne 0) {
        Write-Host "[FAIL] $Name (exit $($proc.ExitCode))"
        exit $proc.ExitCode
    }
    Write-Host "[PASS] $Name"
}

Run-Step "Core API/Index" "$py -m pytest tests/test_api_router.py tests/test_fastapi_server.py tests/test_query_engine.py tests/test_indexer.py tests/test_runtime_limiter.py --basetemp output/pytest_tmp -q" 240
Run-Step "Security/Sanitizers" "$py -m pytest tests/test_pii_scrubber.py tests/test_response_sanitizer.py tests/test_deployment_routing.py --basetemp output/pytest_tmp -q" 180
Run-Step "GUI Matrix" "$py tools/validate_gui_matrix.py" 60
Run-Step "GUI Wiring" "$py tools/dev_verify_gui_wiring.py" 60
Run-Step "Mode Switch Headless" "$py tools/test_mode_switch_headless.py" 180
Run-Step "Quick Index Smoke" "$py tools/quick_index_smoke.py" 60

Write-Host ""
Write-Host "FAST GATE COMPLETE: PASS"
exit 0
