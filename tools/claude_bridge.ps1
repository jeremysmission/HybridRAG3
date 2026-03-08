param(
    [ValidateSet("init", "send", "enqueue", "watch", "status", "tail", "reset")]
    [string]$Command = "status",
    [string]$Prompt = "",
    [string]$PromptFile = "",
    [string]$StatePath = "",
    [string]$QueueRoot = "",
    [string]$ProjectRoot = "",
    [string]$SessionId = "",
    [string]$Model = "",
    [ValidateSet("default", "acceptEdits", "plan", "dontAsk", "bypassPermissions", "auto")]
    [string]$PermissionMode = "",
    [string]$AllowedTools = "",
    [string]$SystemPromptFile = "",
    [string]$RequestId = "",
    [string]$RequestFile = "",
    [int]$PollSeconds = 5,
    [switch]$Once,
    [switch]$DryRun,
    [switch]$ForceNewSession
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:StorageRoot = Split-Path -Parent $PSScriptRoot
if (-not [string]::IsNullOrWhiteSpace($ProjectRoot)) {
    if (-not (Test-Path $ProjectRoot)) {
        throw "Project root not found: $ProjectRoot"
    }
    $script:ProjectRoot = (Resolve-Path $ProjectRoot).Path
}
else {
    $script:ProjectRoot = $script:StorageRoot
}
$script:ProjectSlug = ((Split-Path -Leaf $script:ProjectRoot) -replace '[^A-Za-z0-9._-]', '_')

function Get-RepoRoot {
    return $script:ProjectRoot
}

function Get-LogsRoot {
    return (Join-Path $script:StorageRoot "logs\claude_bridge\$($script:ProjectSlug)")
}

function Get-EffectiveStatePath {
    param([string]$ExplicitPath)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        return $ExplicitPath
    }
    return (Join-Path (Get-LogsRoot) "state.json")
}

function Get-EffectiveQueueRoot {
    param([string]$ExplicitPath)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        return $ExplicitPath
    }
    return (Join-Path $env:USERPROFILE ".ai_handoff\claude_bridge")
}

function Ensure-ParentDirectory {
    param([string]$Path)
    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
}

function Ensure-Directory {
    param([string]$Path)
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Resolve-ClaudePath {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        throw "claude.exe not found on PATH."
    }
    return $cmd.Source
}

function New-BridgeState {
    param(
        [string]$StatePath,
        [string]$SessionId,
        [string]$ClaudePath
    )
    return [ordered]@{
        version = 1
        state_path = $StatePath
        project_root = $script:ProjectRoot
        session_id = $SessionId
        created_at = (Get-Date).ToString("o")
        last_used_at = $null
        message_count = 0
        last_run_dir = $null
        last_request_id = $null
        last_exit_code = $null
        claude_path = $ClaudePath
        model = ""
        permission_mode = ""
        allowed_tools = ""
    }
}

function ConvertTo-HashtableCompat {
    param([object]$InputObject)

    if ($null -eq $InputObject) {
        return $null
    }

    if ($InputObject -is [System.Collections.IDictionary]) {
        $table = @{}
        foreach ($key in $InputObject.Keys) {
            $table[$key] = ConvertTo-HashtableCompat -InputObject $InputObject[$key]
        }
        return $table
    }

    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $items = New-Object System.Collections.Generic.List[object]
        foreach ($item in $InputObject) {
            $items.Add((ConvertTo-HashtableCompat -InputObject $item))
        }
        return ,$items.ToArray()
    }

    if ($InputObject -is [pscustomobject]) {
        $table = @{}
        foreach ($prop in $InputObject.PSObject.Properties) {
            $table[$prop.Name] = ConvertTo-HashtableCompat -InputObject $prop.Value
        }
        return $table
    }

    return $InputObject
}

function Read-BridgeState {
    param([string]$StatePath)
    if (-not (Test-Path $StatePath)) {
        return $null
    }
    $parsed = Get-Content $StatePath -Raw | ConvertFrom-Json
    return (ConvertTo-HashtableCompat -InputObject $parsed)
}

function Write-BridgeState {
    param(
        [hashtable]$State,
        [string]$StatePath
    )
    Ensure-ParentDirectory -Path $StatePath
    ($State | ConvertTo-Json -Depth 8) | Set-Content -Path $StatePath -Encoding UTF8
}

function Get-RequestPrompt {
    param(
        [string]$Prompt,
        [string]$PromptFile
    )
    if (-not [string]::IsNullOrWhiteSpace($Prompt)) {
        return $Prompt
    }
    if (-not [string]::IsNullOrWhiteSpace($PromptFile)) {
        if (-not (Test-Path $PromptFile)) {
            throw "Prompt file not found: $PromptFile"
        }
        return (Get-Content $PromptFile -Raw)
    }
    throw "Provide -Prompt or -PromptFile."
}

function Get-SystemPromptText {
    param([string]$SystemPromptFile)
    if ([string]::IsNullOrWhiteSpace($SystemPromptFile)) {
        return ""
    }
    if (-not (Test-Path $SystemPromptFile)) {
        throw "System prompt file not found: $SystemPromptFile"
    }
    return (Get-Content $SystemPromptFile -Raw)
}

function New-RunDirectory {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $runDir = Join-Path (Get-LogsRoot) "runs\$stamp"
    Ensure-Directory -Path $runDir
    return $runDir
}

function Get-ResponseText {
    param([string]$RawText)
    if ([string]::IsNullOrWhiteSpace($RawText)) {
        return ""
    }
    try {
        $parsed = $RawText | ConvertFrom-Json -ErrorAction Stop
        if ($parsed.result) {
            return [string]$parsed.result
        }
        if ($parsed.message -and $parsed.message.content) {
            $parts = @()
            foreach ($item in $parsed.message.content) {
                if ($item.text) {
                    $parts += [string]$item.text
                }
            }
            if ($parts.Count -gt 0) {
                return ($parts -join "`r`n")
            }
        }
        if ($parsed.content) {
            if ($parsed.content -is [string]) {
                return [string]$parsed.content
            }
            $parts = @()
            foreach ($item in $parsed.content) {
                if ($item.text) {
                    $parts += [string]$item.text
                }
            }
            if ($parts.Count -gt 0) {
                return ($parts -join "`r`n")
            }
        }
    }
    catch {
    }
    return $RawText.Trim()
}

function Build-ClaudeArguments {
    param(
        [hashtable]$State,
        [string]$PromptText,
        [string]$Model,
        [string]$PermissionMode,
        [string]$AllowedTools,
        [string]$SystemPromptText,
        [bool]$FirstMessage
    )
    $args = New-Object System.Collections.Generic.List[string]
    if ($FirstMessage) {
        $args.Add("--session-id")
        $args.Add($State.session_id)
    }
    else {
        $args.Add("--resume")
        $args.Add($State.session_id)
    }
    $args.Add("--print")
    $args.Add("--output-format")
    $args.Add("json")
    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $args.Add("--model")
        $args.Add($Model)
    }
    if (-not [string]::IsNullOrWhiteSpace($PermissionMode)) {
        $args.Add("--permission-mode")
        $args.Add($PermissionMode)
    }
    if (-not [string]::IsNullOrWhiteSpace($AllowedTools)) {
        $args.Add("--allowedTools")
        $args.Add($AllowedTools)
    }
    if (-not [string]::IsNullOrWhiteSpace($SystemPromptText)) {
        $args.Add("--append-system-prompt")
        $args.Add($SystemPromptText)
    }
    $args.Add($PromptText)
    return ,$args.ToArray()
}

function Invoke-ClaudeRequest {
    param(
        [hashtable]$State,
        [string]$PromptText,
        [string]$Model,
        [string]$PermissionMode,
        [string]$AllowedTools,
        [string]$SystemPromptText,
        [string]$RequestId,
        [switch]$DryRun,
        [switch]$ForceNewSession
    )

    $firstMessage = $ForceNewSession.IsPresent -or [string]::IsNullOrWhiteSpace([string]$State.session_id) -or [int]$State.message_count -eq 0
    if ($firstMessage -and [string]::IsNullOrWhiteSpace([string]$State.session_id)) {
        $State.session_id = [guid]::NewGuid().Guid
    }

    $runDir = New-RunDirectory
    $reqId = if ([string]::IsNullOrWhiteSpace($RequestId)) { Split-Path $runDir -Leaf } else { $RequestId }
    $promptPath = Join-Path $runDir "prompt.txt"
    $commandPath = Join-Path $runDir "command.txt"
    $rawPath = Join-Path $runDir "stdout.raw.txt"
    $responsePath = Join-Path $runDir "response.txt"
    $metaPath = Join-Path $runDir "result.json"

    $args = Build-ClaudeArguments -State $State -PromptText $PromptText -Model $Model -PermissionMode $PermissionMode -AllowedTools $AllowedTools -SystemPromptText $SystemPromptText -FirstMessage:$firstMessage

    $quotedArgs = $args | ForEach-Object {
        if ($_ -match '\s|"') {
            '"' + ($_ -replace '"', '\"') + '"'
        }
        else {
            $_
        }
    }
    $commandPreview = "$($State.claude_path) " + ($quotedArgs -join " ")

    $PromptText | Set-Content -Path $promptPath -Encoding UTF8
    $commandPreview | Set-Content -Path $commandPath -Encoding UTF8

    $exitCode = 0
    $rawText = ""
    if ($DryRun) {
        $rawText = "{`"dry_run`":true,`"result`":`"Dry run only. Command was not executed.`"}"
    }
    else {
        Push-Location $State.project_root
        try {
            $output = & $State.claude_path @args 2>&1
            $exitCode = $LASTEXITCODE
            $rawText = ($output | Out-String)
        }
        finally {
            Pop-Location
        }
    }

    $responseText = Get-ResponseText -RawText $rawText
    $rawText | Set-Content -Path $rawPath -Encoding UTF8
    $responseText | Set-Content -Path $responsePath -Encoding UTF8

    $State.last_used_at = (Get-Date).ToString("o")
    $State.last_run_dir = $runDir
    $State.last_request_id = $reqId
    $State.last_exit_code = $exitCode
    $State.model = $Model
    $State.permission_mode = $PermissionMode
    $State.allowed_tools = $AllowedTools
    if (-not $DryRun -and $exitCode -eq 0) {
        $State.message_count = [int]$State.message_count + 1
    }

    $result = [ordered]@{
        request_id = $reqId
        session_id = $State.session_id
        first_message = $firstMessage
        dry_run = [bool]$DryRun
        exit_code = $exitCode
        run_dir = $runDir
        raw_output_path = $rawPath
        response_path = $responsePath
        command_path = $commandPath
        model = $Model
        permission_mode = $PermissionMode
        allowed_tools = $AllowedTools
        response = $responseText
    }
    ($result | ConvertTo-Json -Depth 8) | Set-Content -Path $metaPath -Encoding UTF8
    return $result
}

function Show-State {
    param(
        [hashtable]$State,
        [string]$StatePath,
        [string]$QueueRoot
    )
    if ($null -eq $State) {
        Write-Host "No bridge state found."
        Write-Host "State path: $StatePath"
        Write-Host "Queue root: $QueueRoot"
        return
    }
    Write-Host "State path : $StatePath"
    Write-Host "Queue root : $QueueRoot"
    Write-Host "Project    : $($State.project_root)"
    Write-Host "Session ID : $($State.session_id)"
    Write-Host "Messages   : $($State.message_count)"
    Write-Host "Last run   : $($State.last_run_dir)"
    Write-Host "Last code  : $($State.last_exit_code)"
    Write-Host "Claude     : $($State.claude_path)"
    if ($State.model) {
        Write-Host "Model      : $($State.model)"
    }
    if ($State.permission_mode) {
        Write-Host "Perm mode  : $($State.permission_mode)"
    }
    if ($State.allowed_tools) {
        Write-Host "Tools      : $($State.allowed_tools)"
    }
}

function Get-QueuePaths {
    param([string]$QueueRoot)
    return [ordered]@{
        root = $QueueRoot
        inbox = Join-Path $QueueRoot "inbox"
        outbox = Join-Path $QueueRoot "outbox"
        archive = Join-Path $QueueRoot "archive"
        errors = Join-Path $QueueRoot "errors"
    }
}

function Ensure-QueuePaths {
    param([hashtable]$Paths)
    foreach ($key in @("root", "inbox", "outbox", "archive", "errors")) {
        Ensure-Directory -Path $Paths[$key]
    }
}

function Enqueue-BridgeRequest {
    param(
        [string]$PromptText,
        [string]$QueueRoot,
        [string]$RequestId,
        [string]$Model,
        [string]$PermissionMode,
        [string]$AllowedTools,
        [string]$SystemPromptFile
    )
    $paths = Get-QueuePaths -QueueRoot $QueueRoot
    Ensure-QueuePaths -Paths $paths
    $reqId = if ([string]::IsNullOrWhiteSpace($RequestId)) { "req_" + (Get-Date -Format "yyyyMMdd_HHmmss") } else { $RequestId }
    $payload = [ordered]@{
        request_id = $reqId
        created_at = (Get-Date).ToString("o")
        prompt = $PromptText
        model = $Model
        permission_mode = $PermissionMode
        allowed_tools = $AllowedTools
        system_prompt_file = $SystemPromptFile
    }
    $target = Join-Path $paths.inbox "$reqId.json"
    ($payload | ConvertTo-Json -Depth 6) | Set-Content -Path $target -Encoding UTF8
    return $target
}

function Process-QueueFile {
    param(
        [string]$RequestPath,
        [hashtable]$State,
        [string]$StatePath,
        [string]$QueueRoot,
        [switch]$DryRun
    )
    $paths = Get-QueuePaths -QueueRoot $QueueRoot
    $parsedRequest = Get-Content $RequestPath -Raw | ConvertFrom-Json
    $request = ConvertTo-HashtableCompat -InputObject $parsedRequest
    $promptText = [string]$request.prompt
    if ([string]::IsNullOrWhiteSpace($promptText)) {
        throw "Request file does not contain a prompt."
    }
    $systemPromptText = ""
    if ($request.system_prompt_file) {
        $systemPromptText = Get-SystemPromptText -SystemPromptFile ([string]$request.system_prompt_file)
    }
    $result = Invoke-ClaudeRequest -State $State -PromptText $promptText -Model ([string]$request.model) -PermissionMode ([string]$request.permission_mode) -AllowedTools ([string]$request.allowed_tools) -SystemPromptText $systemPromptText -RequestId ([string]$request.request_id) -DryRun:$DryRun
    Write-BridgeState -State $State -StatePath $StatePath

    $responsePath = Join-Path $paths.outbox "$($result.request_id).json"
    ($result | ConvertTo-Json -Depth 8) | Set-Content -Path $responsePath -Encoding UTF8
    Move-Item -Force -Path $RequestPath -Destination (Join-Path $paths.archive ([System.IO.Path]::GetFileName($RequestPath)))
    return $result
}

$repoRoot = Get-RepoRoot
$effectiveStatePath = Get-EffectiveStatePath -ExplicitPath $StatePath
$effectiveQueueRoot = Get-EffectiveQueueRoot -ExplicitPath $QueueRoot
$paths = Get-QueuePaths -QueueRoot $effectiveQueueRoot
$state = Read-BridgeState -StatePath $effectiveStatePath

switch ($Command) {
    "init" {
        $claudePath = Resolve-ClaudePath
        if ($null -eq $state -or $ForceNewSession) {
            $sid = if ([string]::IsNullOrWhiteSpace($SessionId)) { [guid]::NewGuid().Guid } else { $SessionId }
            $state = New-BridgeState -StatePath $effectiveStatePath -SessionId $sid -ClaudePath $claudePath
        }
        else {
            $state.claude_path = $claudePath
            if (-not [string]::IsNullOrWhiteSpace($SessionId)) {
                $state.session_id = $SessionId
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($Model)) {
            $state.model = $Model
        }
        if (-not [string]::IsNullOrWhiteSpace($PermissionMode)) {
            $state.permission_mode = $PermissionMode
        }
        if (-not [string]::IsNullOrWhiteSpace($AllowedTools)) {
            $state.allowed_tools = $AllowedTools
        }
        Write-BridgeState -State $state -StatePath $effectiveStatePath
        Show-State -State $state -StatePath $effectiveStatePath -QueueRoot $effectiveQueueRoot
        break
    }
    "status" {
        Show-State -State $state -StatePath $effectiveStatePath -QueueRoot $effectiveQueueRoot
        break
    }
    "reset" {
        if (Test-Path $effectiveStatePath) {
            Remove-Item -Force $effectiveStatePath
        }
        Write-Host "Bridge state cleared: $effectiveStatePath"
        break
    }
    "tail" {
        if ($null -eq $state -or [string]::IsNullOrWhiteSpace([string]$state.last_run_dir)) {
            throw "No prior run recorded."
        }
        $tailPath = Join-Path ([string]$state.last_run_dir) "response.txt"
        if (-not (Test-Path $tailPath)) {
            throw "Response file missing: $tailPath"
        }
        Get-Content $tailPath
        break
    }
    "send" {
        if ($null -eq $state -or $ForceNewSession) {
            $claudePath = Resolve-ClaudePath
            $sid = if ([string]::IsNullOrWhiteSpace($SessionId)) { [guid]::NewGuid().Guid } else { $SessionId }
            $state = New-BridgeState -StatePath $effectiveStatePath -SessionId $sid -ClaudePath $claudePath
        }
        elseif (-not $state.claude_path) {
            $state.claude_path = Resolve-ClaudePath
        }

        $promptText = Get-RequestPrompt -Prompt $Prompt -PromptFile $PromptFile
        $systemPromptText = Get-SystemPromptText -SystemPromptFile $SystemPromptFile
        $effectiveModel = if (-not [string]::IsNullOrWhiteSpace($Model)) { $Model } else { [string]$state.model }
        $effectivePermMode = if (-not [string]::IsNullOrWhiteSpace($PermissionMode)) { $PermissionMode } else { [string]$state.permission_mode }
        $effectiveTools = if (-not [string]::IsNullOrWhiteSpace($AllowedTools)) { $AllowedTools } else { [string]$state.allowed_tools }

        $result = Invoke-ClaudeRequest -State $state -PromptText $promptText -Model $effectiveModel -PermissionMode $effectivePermMode -AllowedTools $effectiveTools -SystemPromptText $systemPromptText -RequestId $RequestId -DryRun:$DryRun -ForceNewSession:$ForceNewSession
        Write-BridgeState -State $state -StatePath $effectiveStatePath

        Write-Host "Session ID : $($result.session_id)"
        Write-Host "Run dir    : $($result.run_dir)"
        Write-Host "Exit code  : $($result.exit_code)"
        Write-Host "Response   : $($result.response_path)"
        if ($DryRun) {
            Write-Host "Dry run only. Command preview:"
            Get-Content $result.command_path
        }
        break
    }
    "enqueue" {
        $promptText = Get-RequestPrompt -Prompt $Prompt -PromptFile $PromptFile
        $target = Enqueue-BridgeRequest -PromptText $promptText -QueueRoot $effectiveQueueRoot -RequestId $RequestId -Model $Model -PermissionMode $PermissionMode -AllowedTools $AllowedTools -SystemPromptFile $SystemPromptFile
        Write-Host "Enqueued: $target"
        break
    }
    "watch" {
        if ($null -eq $state) {
            $claudePath = Resolve-ClaudePath
            $sid = if ([string]::IsNullOrWhiteSpace($SessionId)) { [guid]::NewGuid().Guid } else { $SessionId }
            $state = New-BridgeState -StatePath $effectiveStatePath -SessionId $sid -ClaudePath $claudePath
            if (-not [string]::IsNullOrWhiteSpace($Model)) {
                $state.model = $Model
            }
            if (-not [string]::IsNullOrWhiteSpace($PermissionMode)) {
                $state.permission_mode = $PermissionMode
            }
            if (-not [string]::IsNullOrWhiteSpace($AllowedTools)) {
                $state.allowed_tools = $AllowedTools
            }
            Write-BridgeState -State $state -StatePath $effectiveStatePath
        }

        Ensure-QueuePaths -Paths $paths
        do {
            $processed = $false
            $requests = Get-ChildItem -Path $paths.inbox -Filter *.json -File | Sort-Object LastWriteTime
            foreach ($req in $requests) {
                try {
                    $result = Process-QueueFile -RequestPath $req.FullName -State $state -StatePath $effectiveStatePath -QueueRoot $effectiveQueueRoot -DryRun:$DryRun
                    Write-Host "Processed $($result.request_id) -> $($result.response_path)"
                }
                catch {
                    $errorPayload = [ordered]@{
                        request_file = $req.FullName
                        error = $_.Exception.Message
                        timestamp = (Get-Date).ToString("o")
                    }
                    ($errorPayload | ConvertTo-Json -Depth 5) | Set-Content -Path (Join-Path $paths.outbox ($req.BaseName + ".error.json")) -Encoding UTF8
                    Move-Item -Force -Path $req.FullName -Destination (Join-Path $paths.errors $req.Name)
                    Write-Warning "Failed processing $($req.Name): $($_.Exception.Message)"
                }
                $processed = $true
            }
            if ($Once) {
                break
            }
            if (-not $processed) {
                Start-Sleep -Seconds $PollSeconds
            }
        } while ($true)
        break
    }
}
