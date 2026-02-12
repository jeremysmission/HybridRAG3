# HybridRAG Upstream API Path/Auth Diagnostic
# Copy/paste into PowerShell. Only change $BaseHost.
# Outputs:
#  - .\api_diag_report.txt
#  - .\api_diag_results.json

$ErrorActionPreference = "Continue"

# ✅ CHANGE THIS ONE LINE ONLY
$BaseHost = "https://aiml-aoai-api.gcl.mycompany.com"

# Optional (only used for Azure-style probes; can leave blank)
$AzureDeployment = $env:HYBRIDRAG_AZURE_DEPLOYMENT
$AzureApiVersion = $env:HYBRIDRAG_AZURE_API_VERSION
if (-not $AzureApiVersion) { $AzureApiVersion = "2024-02-01" }

# Token discovery: uses env if present; otherwise will prompt once.
$Token = $env:HYBRIDRAG_API_KEY
if (-not $Token) { $Token = $env:OPENAI_API_KEY }
if (-not $Token) { $Token = $env:AZURE_OPENAI_API_KEY }
if (-not $Token) {
  Write-Host "`nNo token found in env (HYBRIDRAG_API_KEY / OPENAI_API_KEY / AZURE_OPENAI_API_KEY)."
  $Token = Read-Host "Paste token now (or press Enter to run unauth-only probes)"
}

function Normalize-Base([string]$b) {
  $b = $b.Trim()
  if ($b.EndsWith("/")) { $b = $b.Substring(0, $b.Length-1) }
  return $b
}

$BaseHost = Normalize-Base $BaseHost

# Candidate paths (models + chat)
$ModelPaths = @(
  "/v1/models",
  "/openai/v1/models",
  "/aoai/v1/models",
  "/api/v1/models",
  "/api/openai/v1/models",
  "/api/aoai/v1/models",
  "/openai/models",
  "/models"
)

$ChatPaths = @(
  "/v1/chat/completions",
  "/openai/v1/chat/completions",
  "/aoai/v1/chat/completions",
  "/api/openai/v1/chat/completions",
  "/api/aoai/v1/chat/completions",
  "/chat/completions",
  "/openai/chat/completions"
)

# Azure-style chat patterns (only meaningful if deployment known)
$AzureChatPaths = @()
if ($AzureDeployment) {
  $AzureChatPaths += "/openai/deployments/$AzureDeployment/chat/completions?api-version=$AzureApiVersion"
  $AzureChatPaths += "/aoai/deployments/$AzureDeployment/chat/completions?api-version=$AzureApiVersion"
  $AzureChatPaths += "/api/openai/deployments/$AzureDeployment/chat/completions?api-version=$AzureApiVersion"
}

# Auth strategies to try (if token present)
$AuthStrategies = @(
  @{ name="no_auth"; headers=@{} }
)

if ($Token) {
  $AuthStrategies += @{ name="bearer"; headers=@{ "Authorization"="Bearer $Token" } }
  $AuthStrategies += @{ name="api_key"; headers=@{ "api-key"="$Token" } }
  $AuthStrategies += @{ name="subscription_key"; headers=@{ "Ocp-Apim-Subscription-Key"="$Token" } }
}

function Invoke-Probe {
  param(
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers,
    [string]$BodyJson
  )

  $result = [ordered]@{
    method = $Method
    url = $Url
    status = $null
    statusText = $null
    activityId = $null
    snippet = $null
    ok = $false
    error = $null
  }

  try {
    $hdrs = @{}
    foreach ($k in $Headers.Keys) { $hdrs[$k] = $Headers[$k] }
    if (-not $hdrs.ContainsKey("Accept")) { $hdrs["Accept"] = "application/json" }

    $resp = $null
    if ($BodyJson) {
      if (-not $hdrs.ContainsKey("Content-Type")) { $hdrs["Content-Type"] = "application/json" }
      $resp = Invoke-WebRequest -Method $Method -Uri $Url -Headers $hdrs -Body $BodyJson -UseBasicParsing -TimeoutSec 20
    } else {
      $resp = Invoke-WebRequest -Method $Method -Uri $Url -Headers $hdrs -UseBasicParsing -TimeoutSec 20
    }

    $result.status = [int]$resp.StatusCode
    $result.statusText = $resp.StatusDescription
    $txt = $resp.Content
    if ($txt) {
      if ($txt.Length -gt 400) { $txt = $txt.Substring(0,400) + "..." }
      $result.snippet = $txt
      # try to extract activityId (common in gateways)
      if ($txt -match "(?i)activityId[^A-Za-z0-9\-]*([A-Za-z0-9\-]{8,})") { $result.activityId = $Matches[1] }
    }
    $result.ok = ($result.status -ge 200 -and $result.status -lt 300)
  }
  catch {
    $ex = $_.Exception
    $result.error = $ex.Message

    try {
      $r = $ex.Response
      if ($r) {
        $result.status = [int]$r.StatusCode
        $result.statusText = $r.StatusDescription
        $stream = $r.GetResponseStream()
        if ($stream) {
          $reader = New-Object System.IO.StreamReader($stream)
          $txt = $reader.ReadToEnd()
          if ($txt) {
            if ($txt.Length -gt 400) { $txt = $txt.Substring(0,400) + "..." }
            $result.snippet = $txt
            if ($txt -match "(?i)activityId[^A-Za-z0-9\-]*([A-Za-z0-9\-]{8,})") { $result.activityId = $Matches[1] }
          }
        }
      }
    } catch {}
  }

  return [pscustomobject]$result
}

$Results = New-Object System.Collections.Generic.List[object]

Write-Host "`n=== HybridRAG API Diagnostic ==="
Write-Host "BaseHost: $BaseHost"
Write-Host ("Token present: " + [bool]$Token)
if ($AzureDeployment) {
  Write-Host "AzureDeployment (from env): $AzureDeployment"
  Write-Host "AzureApiVersion: $AzureApiVersion"
}

# Minimal POST body for chat probes (OpenAI-ish)
$ChatBody = @{
  model="gpt-4o-mini"
  messages=@(@{role="user"; content="OK"})
  max_tokens=5
} | ConvertTo-Json -Depth 6

# Run probes
foreach ($auth in $AuthStrategies) {
  $authName = $auth.name
  $hdrs = $auth.headers

  Write-Host "`n-- Auth strategy: $authName --"

  # Models: GET
  foreach ($p in $ModelPaths) {
    $url = "$BaseHost$p"
    $Results.Add((Invoke-Probe -Method "GET" -Url $url -Headers $hdrs -BodyJson $null)) | Out-Null
  }

  # Chat: OPTIONS then POST (OPTIONS often works even when POST blocked)
  foreach ($p in $ChatPaths) {
    $url = "$BaseHost$p"
    $Results.Add((Invoke-Probe -Method "OPTIONS" -Url $url -Headers $hdrs -BodyJson $null)) | Out-Null
    $Results.Add((Invoke-Probe -Method "POST" -Url $url -Headers $hdrs -BodyJson $ChatBody)) | Out-Null
  }

  # Azure-style chat: POST
  foreach ($p in $AzureChatPaths) {
    $url = "$BaseHost$p"
    $Results.Add((Invoke-Probe -Method "POST" -Url $url -Headers $hdrs -BodyJson $ChatBody)) | Out-Null
  }
}

# Summarize “best candidates”
function Score-Status([int]$s) {
  if ($s -ge 200 -and $s -lt 300) { return 100 }
  if ($s -eq 401 -or $s -eq 403) { return 90 }   # route exists; auth needed/wrong
  if ($s -eq 429) { return 80 }
  if ($s -eq 400 -or $s -eq 415) { return 70 }   # route exists; body/ctype mismatch
  if ($s -eq 404) { return 10 }
  if ($s -ge 500 -and $s -lt 600) { return 40 }  # gateway error; still informative
  return 20
}

$Ranked = $Results | Where-Object { $_.status -ne $null } |
  Select-Object method, url, status, statusText, activityId, snippet, error,
    @{n="score"; e={ Score-Status $_.status }} |
  Sort-Object score -Descending, status -Ascending

$Top = $Ranked | Select-Object -First 25

# Write outputs
$txtPath = Join-Path (Get-Location) "api_diag_report.txt"
$jsonPath = Join-Path (Get-Location) "api_diag_results.json"

$report = New-Object System.Text.StringBuilder
$null = $report.AppendLine("=== HybridRAG API Diagnostic Report ===")
$null = $report.AppendLine("Timestamp: " + (Get-Date).ToString("s"))
$null = $report.AppendLine("BaseHost: $BaseHost")
$null = $report.AppendLine("Token present: " + [bool]$Token)
$null = $report.AppendLine("AzureDeployment: " + ($AzureDeployment ? $AzureDeployment : "<none>"))
$null = $report.AppendLine("AzureApiVersion: " + $AzureApiVersion)
$null = $report.AppendLine("")
$null = $report.AppendLine("Top candidate endpoints (highest likelihood first):")
$null = $report.AppendLine("--------------------------------------------------")

foreach ($r in $Top) {
  $null = $report.AppendLine(("{0} {1}  =>  {2} {3}" -f $r.method, $r.url, $r.status, $r.statusText))
  if ($r.activityId) { $null = $report.AppendLine("  activityId: " + $r.activityId) }
  if ($r.snippet) { $null = $report.AppendLine("  snippet: " + ($r.snippet -replace "\s+"," ").Trim()) }
  if ($r.error) { $null = $report.AppendLine("  error: " + $r.error) }
  $null = $report.AppendLine("")
}

# Next move logic
$best = $Ranked | Select-Object -First 1
$null = $report.AppendLine("=== Next Move (auto guidance) ===")

if (-not $best) {
  $null = $report.AppendLine("No HTTP responses captured. This suggests DNS/TLS/proxy prevented any connection.")
  $null = $report.AppendLine("Next: test in browser from service machine and check corporate proxy / TLS inspection.")
} else {
  $null = $report.AppendLine(("Best signal: {0} {1} => {2} {3}" -f $best.method, $best.url, $best.status, $best.statusText))

  if ($best.status -ge 200 -and $best.status -lt 300) {
    $null = $report.AppendLine("✅ You have a working route with the tested auth scheme.")
    $null = $report.AppendLine("Next: configure your RAG to use this PATH (not hardcoded /v1/chat/completions).")
  }
  elseif ($best.status -eq 401 -or $best.status -eq 403) {
    $null = $report.AppendLine("✅ Route likely exists. Auth is missing or incorrect for this gateway.")
    $null = $report.AppendLine("Next: ensure RAG uses the same header style that produced 401/403 here (Bearer vs api-key vs subscription-key).")
  }
  elseif ($best.status -eq 404) {
    $null = $report.AppendLine("❌ 404 means your RAG is calling a path that does not exist on this host.")
    $null = $report.AppendLine("Next: pick a path from the 'Top candidate endpoints' that returned 401/403/400/500 instead of 404.")
  }
  elseif ($best.status -ge 500 -and $best.status -lt 600) {
    $null = $report.AppendLine("⚠️ 5xx from gateway (ActivityId often present). Route may exist but gateway is rejecting/throwing without auth or due to backend config.")
    $null = $report.AppendLine("Next: try the same URL with the correct auth header; if still 5xx, hand ActivityId to your gateway team.")
  } else {
    $null = $report.AppendLine("Signal suggests the route exists but request shape or headers are wrong.")
    $null = $report.AppendLine("Next: use the best-scoring chat endpoint and align your client with its requirements.")
  }

  $null = $report.AppendLine("")
  $null = $report.AppendLine("Practical tip:")
  $null = $report.AppendLine("- Store ONLY the base host in your config/credential store (e.g. https://aiml-aoai-api.gcl.mycompany.com).")
  $null = $report.AppendLine("- Then configure a separate chat path (gateway prefix) instead of hardcoding /v1/chat/completions.")
}

$report.ToString() | Out-File -FilePath $txtPath -Encoding UTF8

# Full JSON dump
$Results | ConvertTo-Json -Depth 6 | Out-File -FilePath $jsonPath -Encoding UTF8

Write-Host "`nDONE."
Write-Host "Report: $txtPath"
Write-Host "JSON  : $jsonPath"
Write-Host "`nOpen api_diag_report.txt and paste the 'Top candidate endpoints' section back to me."
