param(
    [ValidateSet("status", "snapshot", "nudge", "policy", "tail")]
    [string]$Command = "status",
    [string]$ProjectRoot = "D:\JCoder",
    [string]$BridgeProjectRoot = "D:\JCoder",
    [string]$QueueRoot = "",
    [string]$Prompt = "",
    [string]$RequestId = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-StorageRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Ensure-Dir {
    param([string]$Path)
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Invoke-GitText {
    param(
        [string]$RepoRoot,
        [string[]]$GitArgs,
        [switch]$AllowNonZero
    )
    $output = & git -C $RepoRoot @GitArgs 2>&1
    $code = $LASTEXITCODE
    if (-not $AllowNonZero -and $code -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code ${code}: $($output | Out-String)"
    }
    return ($output | Out-String).TrimEnd()
}

function Get-MonitorRoot {
    return (Join-Path (Get-StorageRoot) "logs\jcoder_monitor")
}

function New-SnapshotDir {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $dir = Join-Path (Get-MonitorRoot) $stamp
    Ensure-Dir -Path $dir
    return $dir
}

function Get-RepoSnapshot {
    param([string]$RepoRoot)

    $branch = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("rev-parse", "--abbrev-ref", "HEAD")
    $head = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("log", "-1", "--oneline")
    $statusShort = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("status", "--short")
    $statusPorcelain = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("status", "--porcelain=v1")
    $diffStat = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("diff", "--stat")
    $diffNames = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("diff", "--name-only")
    $stagedNames = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("diff", "--cached", "--name-only")
    $untracked = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("ls-files", "--others", "--exclude-standard")
    $patch = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("diff")
    $stagedPatch = Invoke-GitText -RepoRoot $RepoRoot -GitArgs @("diff", "--cached")

    $changedFiles = @()
    foreach ($line in ($statusPorcelain -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $path = $line.Substring(3).Trim()
        if (-not [string]::IsNullOrWhiteSpace($path) -and -not $changedFiles.Contains($path)) {
            $changedFiles += $path
        }
    }

    return [ordered]@{
        project_root = $RepoRoot
        branch = $branch
        head = $head
        clean = [string]::IsNullOrWhiteSpace($statusPorcelain)
        status_short = $statusShort
        diff_stat = $diffStat
        diff_names = $diffNames
        staged_names = $stagedNames
        untracked = $untracked
        patch = $patch
        staged_patch = $stagedPatch
        changed_files = $changedFiles
    }
}

function Show-SnapshotSummary {
    param([hashtable]$Snapshot)
    Write-Host "Repo    : $($Snapshot.project_root)"
    Write-Host "Branch  : $($Snapshot.branch)"
    Write-Host "HEAD    : $($Snapshot.head)"
    Write-Host "Clean   : $($Snapshot.clean)"
    Write-Host "Changed : $($Snapshot.changed_files.Count)"
    if (-not $Snapshot.clean) {
        if ($Snapshot.changed_files.Count -gt 0) {
            Write-Host "Files   :"
            foreach ($file in $Snapshot.changed_files) {
                Write-Host "  $file"
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($Snapshot.diff_stat)) {
            Write-Host ""
            Write-Host $Snapshot.diff_stat
        }
    }
}

function Write-SnapshotFiles {
    param(
        [hashtable]$Snapshot,
        [string]$Dir
    )
    Ensure-Dir -Path $Dir
    ($Snapshot | Select-Object project_root, branch, head, clean, changed_files | ConvertTo-Json -Depth 6) | Set-Content -Path (Join-Path $Dir "summary.json") -Encoding UTF8
    $Snapshot.status_short | Set-Content -Path (Join-Path $Dir "status_short.txt") -Encoding UTF8
    $Snapshot.diff_stat | Set-Content -Path (Join-Path $Dir "diff_stat.txt") -Encoding UTF8
    $Snapshot.diff_names | Set-Content -Path (Join-Path $Dir "diff_names.txt") -Encoding UTF8
    $Snapshot.staged_names | Set-Content -Path (Join-Path $Dir "staged_names.txt") -Encoding UTF8
    $Snapshot.untracked | Set-Content -Path (Join-Path $Dir "untracked.txt") -Encoding UTF8
    $Snapshot.patch | Set-Content -Path (Join-Path $Dir "diff.patch") -Encoding UTF8
    $Snapshot.staged_patch | Set-Content -Path (Join-Path $Dir "diff_staged.patch") -Encoding UTF8
}

function Build-NudgePrompt {
    param([hashtable]$Snapshot)
    if ($Snapshot.clean) {
        return "State your current active JCoder task, any blockers, and the next concrete step. Do not edit files in this response."
    }

    $files = $Snapshot.changed_files | Select-Object -First 12
    $fileBlock = ($files | ForEach-Object { "- $_" }) -join "`r`n"
    return @"
You are working in JCoder. Do a read-only self-review of your current uncommitted changes and do not edit anything yet.

Changed files:
$fileBlock

Reply with exactly:
1. Current task
2. Top 3 concrete risks or bugs in these changes
3. Whether you should fix anything before committing
"@
}

function Build-WorkflowPolicyPrompt {
    return @"
Treat this as workflow policy for the active JCoder sprint.

Operating rules:
1. Work one scoped objective at a time.
2. Use at most 1-2 background jobs unless there is a clear dependency-free reason.
3. Prefer targeted tests first. Run full suite only before commit/push or when the change surface is broad.
4. Do not narrate trivial checks or obvious facts. Report evidence instead.
5. For every external QA finding:
   - verify against current code
   - fix if valid
   - run relevant regressions
   - reply with verdict, files changed, tests run, residual risk
   - if invalid, rebut with exact code evidence
6. Before committing, state what remains unverified.
7. Do not claim a fix is complete if the code still carries a reduced but unresolved version of the original problem.
8. Keep responses concise and engineering-focused.

Reply with exactly:
1. acknowledged
2. the current scoped objective
3. the next test gate you will run before the next commit
"@
}

function Invoke-BridgeEnqueue {
    param(
        [string]$BridgeProjectRoot,
        [string]$QueueRoot,
        [string]$PromptText,
        [string]$RequestId,
        [switch]$DryRun
    )
    $bridgeScript = Join-Path $PSScriptRoot "claude_bridge.ps1"
    $args = @(
        "-File", $bridgeScript,
        "enqueue",
        "-ProjectRoot", $BridgeProjectRoot,
        "-Prompt", $PromptText
    )
    if (-not [string]::IsNullOrWhiteSpace($QueueRoot)) {
        $args += @("-QueueRoot", $QueueRoot)
    }
    if (-not [string]::IsNullOrWhiteSpace($RequestId)) {
        $args += @("-RequestId", $RequestId)
    }
    if ($DryRun) {
        Write-Host "Dry run only. Would enqueue bridge prompt:"
        Write-Host $PromptText
        return
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass @args
    if ($LASTEXITCODE -ne 0) {
        throw "Bridge enqueue failed with exit code $LASTEXITCODE."
    }
}

function Get-LatestSnapshotDir {
    $root = Get-MonitorRoot
    if (-not (Test-Path $root)) {
        return $null
    }
    return Get-ChildItem $root -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

switch ($Command) {
    "status" {
        $snapshot = Get-RepoSnapshot -RepoRoot $ProjectRoot
        Show-SnapshotSummary -Snapshot $snapshot
        break
    }
    "snapshot" {
        $snapshot = Get-RepoSnapshot -RepoRoot $ProjectRoot
        $dir = New-SnapshotDir
        Write-SnapshotFiles -Snapshot $snapshot -Dir $dir
        Show-SnapshotSummary -Snapshot $snapshot
        Write-Host ""
        Write-Host "Snapshot : $dir"
        break
    }
    "nudge" {
        $snapshot = Get-RepoSnapshot -RepoRoot $ProjectRoot
        $dir = New-SnapshotDir
        Write-SnapshotFiles -Snapshot $snapshot -Dir $dir
        $promptText = if ([string]::IsNullOrWhiteSpace($Prompt)) { Build-NudgePrompt -Snapshot $snapshot } else { $Prompt }
        Write-Host "Snapshot : $dir"
        Invoke-BridgeEnqueue -BridgeProjectRoot $BridgeProjectRoot -QueueRoot $QueueRoot -PromptText $promptText -RequestId $RequestId -DryRun:$DryRun
        break
    }
    "policy" {
        $snapshot = Get-RepoSnapshot -RepoRoot $ProjectRoot
        $dir = New-SnapshotDir
        Write-SnapshotFiles -Snapshot $snapshot -Dir $dir
        $promptText = if ([string]::IsNullOrWhiteSpace($Prompt)) { Build-WorkflowPolicyPrompt } else { $Prompt }
        Write-Host "Snapshot : $dir"
        Invoke-BridgeEnqueue -BridgeProjectRoot $BridgeProjectRoot -QueueRoot $QueueRoot -PromptText $promptText -RequestId $RequestId -DryRun:$DryRun
        break
    }
    "tail" {
        $latest = Get-LatestSnapshotDir
        if ($null -eq $latest) {
            throw "No monitor snapshots found."
        }
        Write-Host "Latest snapshot: $($latest.FullName)"
        Get-Content (Join-Path $latest.FullName "summary.json")
        break
    }
}
