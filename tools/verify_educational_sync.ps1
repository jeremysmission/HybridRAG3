<#
=== NON-PROGRAMMER GUIDE ===
Purpose: Automates the verify educational sync operational workflow for developers or operators.
How to follow: Read variables first, then each command block in order.
Inputs: Environment variables, script parameters, and local files.
Outputs: Console messages, changed files, or system configuration updates.
Safety notes: Run in a test environment before using on production systems.
=============================
#>
﻿param(
    [string]$PrivateRepo = "D:\HybridRAG3",
    [string]$EducationalRepo = "D:\HybridRAG3_Educational",
    [switch]$SkipSync,
    [switch]$NoCompile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host "[OK] $Message"
}

function Write-WarnMsg([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-FailMsg([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Invoke-Step([string]$Name, [scriptblock]$Action) {
    Write-Host "`r`n[OK] Step: $Name" -ForegroundColor Cyan
    & $Action
}

function Get-LastCommitFiles([string]$RepoPath) {
    $raw = git -C $RepoPath show --name-only --pretty=format: HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get changed files from private repo"
    }
    return @($raw | Where-Object { $_ -and $_.Trim().Length -gt 0 } | ForEach-Object { $_.Trim() })
}

function Should-ExpectInEducational([string]$RelativePath) {
    $path = $RelativePath.Replace('\\', '/').ToLowerInvariant()

    if ($path.StartsWith("docs/05_security/")) { return $false }
    if ($path.StartsWith("docs/09_project_mgmt/")) { return $false }
    if ($path.StartsWith("docs/logs/")) { return $false }
    if ($path.StartsWith("docs/research/")) { return $false }
    if ($path.StartsWith("docs/claudecli_codex_collabs/")) { return $false }
    if ($path -eq "tools/sync_to_educational.py") { return $false }
    if ($path -like "*virtual_test*") { return $false }
    if ($path.EndsWith(".docx") -or $path.EndsWith(".xlsx")) { return $false }

    return $true
}

function Test-RepoPath([string]$PathToCheck, [string]$Label) {
    if (-not (Test-Path $PathToCheck)) {
        throw "$Label not found: $PathToCheck"
    }
    if (-not (Test-Path (Join-Path $PathToCheck ".git"))) {
        throw "$Label is not a git repo: $PathToCheck"
    }
}

Invoke-Step "Validate repos" {
    Test-RepoPath -PathToCheck $PrivateRepo -Label "Private repo"
    Test-RepoPath -PathToCheck $EducationalRepo -Label "Educational repo"
    Write-Info "Private repo: $PrivateRepo"
    Write-Info "Educational repo: $EducationalRepo"
}

$privateHead = ""
$privateFiles = @()
Invoke-Step "Read private HEAD + changed files" {
    $privateHead = (git -C $PrivateRepo rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read private HEAD"
    }
    $privateFiles = Get-LastCommitFiles -RepoPath $PrivateRepo
    Write-Info "Private HEAD: $privateHead"
    Write-Info "Files in last private commit: $($privateFiles.Count)"
}

if (-not $SkipSync) {
    Invoke-Step "Run sanitizer sync" {
        Push-Location $PrivateRepo
        try {
            python tools/sync_to_educational.py
            if ($LASTEXITCODE -ne 0) {
                throw "sync_to_educational.py returned non-zero exit code"
            }
            Write-Info "Sanitizer sync completed"
        }
        finally {
            Pop-Location
        }
    }
}
else {
    Write-WarnMsg "Skipping sync run (--SkipSync supplied)"
}

$missing = @()
$checked = 0
$skipped = 0
Invoke-Step "Verify changed files propagated to educational repo" {
    foreach ($rel in $privateFiles) {
        if (-not (Should-ExpectInEducational -RelativePath $rel)) {
            $skipped += 1
            continue
        }
        $checked += 1
        $dst = Join-Path $EducationalRepo $rel
        if (-not (Test-Path $dst)) {
            $missing += $rel
        }
    }

    Write-Info "Checked expected files: $checked"
    Write-Info "Skipped by sanitization rules: $skipped"
    if ($missing.Count -gt 0) {
        foreach ($m in $missing) {
            Write-FailMsg "Missing in educational repo: $m"
        }
        throw "Propagation check failed ($($missing.Count) missing files)"
    }
    Write-Info "Propagation check passed"
}

Invoke-Step "Show educational repo state" {
    $eduHead = (git -C $EducationalRepo rev-parse --short HEAD).Trim()
    $eduLog = (git -C $EducationalRepo log -1 --oneline).Trim()
    Write-Info "Educational HEAD: $eduHead"
    Write-Host "[OK] Educational latest commit: $eduLog"

    $status = git -C $EducationalRepo status --short
    if ($status) {
        Write-WarnMsg "Educational repo has uncommitted changes"
        $status | ForEach-Object { Write-Host "  $_" }
    }
    else {
        Write-Info "Educational repo working tree is clean"
    }
}

if (-not $NoCompile) {
    Invoke-Step "Run quick py_compile smoke on changed Python files" {
        $pyFiles = @()
        foreach ($rel in $privateFiles) {
            if (-not $rel.EndsWith(".py")) { continue }
            if (-not (Should-ExpectInEducational -RelativePath $rel)) { continue }
            $target = Join-Path $EducationalRepo $rel
            if (Test-Path $target) {
                $pyFiles += $target
            }
        }

        if ($pyFiles.Count -eq 0) {
            Write-WarnMsg "No changed Python files to compile"
        }
        else {
            python -m py_compile @pyFiles
            if ($LASTEXITCODE -ne 0) {
                throw "py_compile failed on educational changed Python files"
            }
            Write-Info "py_compile passed for $($pyFiles.Count) changed Python files"
        }
    }
}
else {
    Write-WarnMsg "Skipping py_compile (--NoCompile supplied)"
}

Write-Host "`r`n[OK] verify_educational_sync completed successfully" -ForegroundColor Green