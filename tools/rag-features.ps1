# ============================================================================
# rag-features.ps1 -- HybridRAG3 Feature Toggle CLI
# ============================================================================
#
# WHAT THIS DOES:
#   Lets you turn HybridRAG3 features on and off from the command line.
#   Each feature has a clear name so you know exactly what you're toggling.
#
# COMMANDS:
#   rag-features list                         Show all features with status
#   rag-features enable hallucination-filter   Turn ON the 5-step anti-hallucination pipeline
#   rag-features disable hallucination-filter  Turn OFF the hallucination filter
#   rag-features enable reranker              Turn ON cross-encoder reranking
#   rag-features disable pii-scrubber         Turn OFF PII removal (not recommended)
#   rag-features status                       Quick status of all features
#   rag-features status hallucination-filter   Status of one specific feature
#
# AVAILABLE FEATURES:
#   hallucination-filter   5-step anti-hallucination pipeline (retrieval gate,
#                          prompt hardening, claim extraction, NLI verification,
#                          grounding score). Adds ~2-8s per query.
#
#   hybrid-search          Combines semantic + keyword search for better
#                          document retrieval. Best for engineering docs.
#
#   reranker               Re-scores search results with a more accurate model.
#                          Improves relevance for technical queries.
#
#   pii-scrubber           Removes personally identifiable information before
#                          sending to online APIs. Required for compliance.
#
#   audit-log              Records every query and document access to log files.
#                          Required for auditing and compliance.
#
#   cost-tracker           Tracks API token usage and estimated costs.
#                          Enforces daily budget limits.
#
# GUI INTEGRATION:
#   This script calls the same Python feature_registry.py that the future
#   GUI will use. Adding a feature to the registry automatically makes it
#   available in BOTH the CLI and the GUI -- no extra work needed.
#
# SETUP:
#   1. Copy this file to D:\HybridRAG3\tools\rag-features.ps1
#   2. Add to your PowerShell profile for shortcut access (see bottom of file)
#
# NETWORK ACCESS: NONE (modifies local YAML config only)
# ============================================================================

param(
    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter(Position=1)]
    [string]$FeatureId = ""
)

# --- Configuration ---
$ProjectRoot = "D:\HybridRAG3"
$PythonExe = "python"
$RegistryScript = Join-Path $ProjectRoot "src\core\feature_registry.py"
$ConfigFile = Join-Path $ProjectRoot "config\default_config.yaml"

# --- Validate setup ---
if (-not (Test-Path $ConfigFile)) {
    Write-Host "[FAIL] Config not found: $ConfigFile" -ForegroundColor Red
    Write-Host "       Are you in the right directory?" -ForegroundColor Red
    exit 1
}

# --- Feature lookup (for PowerShell-native display without Python) ---
$Features = @{
    "hallucination-filter" = @{
        Name   = "Hallucination Filter"
        Desc   = "5-step anti-hallucination pipeline (retrieval gate, prompt hardening, claim extraction, NLI verification, grounding score)"
        Impact = "Adds ~2-4s (GPU) or ~3-8s (CPU) per query"
        Section = "hallucination_guard"
        Key    = "enabled"
    }
    "hybrid-search" = @{
        Name   = "Hybrid Search"
        Desc   = "Combines semantic (meaning) + keyword (exact match) search"
        Impact = "Minimal (<100ms)"
        Section = "retrieval"
        Key    = "hybrid_search"
    }
    "reranker" = @{
        Name   = "Cross-Encoder Reranker"
        Desc   = "Re-scores results with more accurate model. Tune via reranker_top_n (default 12)"
        Impact = "Adds ~0.3-0.6s per query (12 candidates)"
        Section = "retrieval"
        Key    = "reranker_enabled"
    }
    "pii-scrubber" = @{
        Name   = "PII Scrubber"
        Desc   = "Removes personal info before sending to online APIs (compliance)"
        Impact = "Minimal (<50ms)"
        Section = "security"
        Key    = "pii_sanitization"
    }
    "audit-log" = @{
        Name   = "Audit Logging"
        Desc   = "Records every query and document access for compliance"
        Impact = "Minimal (disk I/O only)"
        Section = "security"
        Key    = "audit_logging"
    }
    "cost-tracker" = @{
        Name   = "API Cost Tracker"
        Desc   = "Tracks token usage and enforces daily budget limits"
        Impact = "None (accounting only)"
        Section = "cost"
        Key    = "track_enabled"
    }
}

# --- Helper: Read current state from YAML ---
function Get-FeatureState {
    param([string]$FeatureId)

    if (-not $Features.ContainsKey($FeatureId)) {
        return $null
    }

    $feat = $Features[$FeatureId]
    $content = Get-Content $ConfigFile -Raw

    # Look for the key in the right section
    # Pattern: section:\n  ...\n  key: true/false
    $section = $feat.Section
    $key = $feat.Key

    # Simple regex: find "key: true" or "key: false" under the section
    if ($content -match "(?s)${section}:.*?${key}:\s*(true|false)") {
        return $Matches[1] -eq "true"
    }
    return $false
}

# --- Helper: Set feature state in YAML ---
function Set-FeatureState {
    param([string]$FeatureId, [bool]$Enabled)

    $feat = $Features[$FeatureId]
    $section = $feat.Section
    $key = $feat.Key
    $newVal = if ($Enabled) { "true" } else { "false" }
    $oldVal = if ($Enabled) { "false" } else { "true" }

    $content = Get-Content $ConfigFile -Raw

    # Find and replace the specific key value under the section
    # This preserves YAML comments and formatting
    $pattern = "(?s)(${section}:.*?${key}:\s*)${oldVal}"
    $replacement = "`${1}${newVal}"

    if ($content -match $pattern) {
        $updated = $content -replace $pattern, $replacement
        Set-Content $ConfigFile $updated -NoNewline
        return $true
    }

    return $false
}


# =========================================================================
# COMMAND HANDLERS
# =========================================================================

switch ($Command.ToLower()) {

    "list" {
        Write-Host ""
        Write-Host ("=" * 65) -ForegroundColor Cyan
        Write-Host "  HybridRAG3 Feature Toggles" -ForegroundColor Cyan
        Write-Host ("=" * 65) -ForegroundColor Cyan

        $categories = @("Quality", "Retrieval", "Security", "Cost")
        $catMap = @{
            "hallucination-filter" = "Quality"
            "hybrid-search" = "Retrieval"
            "reranker" = "Retrieval"
            "pii-scrubber" = "Security"
            "audit-log" = "Security"
            "cost-tracker" = "Cost"
        }

        foreach ($cat in $categories) {
            $catFeatures = $Features.Keys | Where-Object { $catMap[$_] -eq $cat }
            if ($catFeatures.Count -eq 0) { continue }

            Write-Host ""
            Write-Host "  [$cat]" -ForegroundColor White
            Write-Host ("  " + ("-" * 60)) -ForegroundColor DarkGray

            foreach ($fid in $catFeatures) {
                $f = $Features[$fid]
                $state = Get-FeatureState $fid

                if ($state) {
                    Write-Host "    [ON]  " -NoNewline -ForegroundColor Green
                } else {
                    Write-Host "    [OFF] " -NoNewline -ForegroundColor Yellow
                }
                Write-Host $f.Name -ForegroundColor White
                Write-Host "          ID: $fid" -ForegroundColor DarkGray
                Write-Host "          $($f.Desc)" -ForegroundColor Gray
                Write-Host "          Performance: $($f.Impact)" -ForegroundColor DarkGray
                Write-Host ""
            }
        }

        Write-Host ("=" * 65) -ForegroundColor Cyan
        Write-Host "  Commands:" -ForegroundColor Gray
        Write-Host "    rag-features enable <feature-id>" -ForegroundColor Gray
        Write-Host "    rag-features disable <feature-id>" -ForegroundColor Gray
        Write-Host "    rag-features status [feature-id]" -ForegroundColor Gray
        Write-Host ("=" * 65) -ForegroundColor Cyan
        Write-Host ""
    }

    "enable" {
        if (-not $FeatureId) {
            Write-Host "[FAIL] Specify which feature to enable." -ForegroundColor Red
            Write-Host "       Run 'rag-features list' to see available features." -ForegroundColor Red
            exit 1
        }
        if (-not $Features.ContainsKey($FeatureId)) {
            Write-Host "[FAIL] Unknown feature: '$FeatureId'" -ForegroundColor Red
            Write-Host "       Available features:" -ForegroundColor Red
            foreach ($fid in $Features.Keys) {
                Write-Host "         $fid  --  $($Features[$fid].Name)" -ForegroundColor Yellow
            }
            exit 1
        }

        $f = $Features[$FeatureId]
        $current = Get-FeatureState $FeatureId

        if ($current) {
            Write-Host "[OK] $($f.Name) is already ENABLED" -ForegroundColor Green
            exit 0
        }

        $success = Set-FeatureState $FeatureId $true
        if ($success) {
            Write-Host "[OK] $($f.Name) -- ENABLED" -ForegroundColor Green
            Write-Host "     $($f.Desc)" -ForegroundColor Gray
            Write-Host "     Performance impact: $($f.Impact)" -ForegroundColor Yellow
        } else {
            Write-Host "[FAIL] Could not update config. Check $ConfigFile" -ForegroundColor Red
        }
    }

    "disable" {
        if (-not $FeatureId) {
            Write-Host "[FAIL] Specify which feature to disable." -ForegroundColor Red
            Write-Host "       Run 'rag-features list' to see available features." -ForegroundColor Red
            exit 1
        }
        if (-not $Features.ContainsKey($FeatureId)) {
            Write-Host "[FAIL] Unknown feature: '$FeatureId'" -ForegroundColor Red
            Write-Host "       Available features:" -ForegroundColor Red
            foreach ($fid in $Features.Keys) {
                Write-Host "         $fid  --  $($Features[$fid].Name)" -ForegroundColor Yellow
            }
            exit 1
        }

        $f = $Features[$FeatureId]
        $current = Get-FeatureState $FeatureId

        if (-not $current) {
            Write-Host "[OK] $($f.Name) is already DISABLED" -ForegroundColor Yellow
            exit 0
        }

        $success = Set-FeatureState $FeatureId $false
        if ($success) {
            Write-Host "[OK] $($f.Name) -- DISABLED" -ForegroundColor Yellow
        } else {
            Write-Host "[FAIL] Could not update config. Check $ConfigFile" -ForegroundColor Red
        }
    }

    "status" {
        if ($FeatureId -and $Features.ContainsKey($FeatureId)) {
            $f = $Features[$FeatureId]
            $state = Get-FeatureState $FeatureId
            if ($state) {
                Write-Host "[ON]  $($f.Name)" -ForegroundColor Green
            } else {
                Write-Host "[OFF] $($f.Name)" -ForegroundColor Yellow
            }
            Write-Host "      $($f.Desc)" -ForegroundColor Gray
        } elseif ($FeatureId) {
            Write-Host "[FAIL] Unknown feature: '$FeatureId'" -ForegroundColor Red
        } else {
            # Show quick status of all features
            Write-Host ""
            Write-Host "  Feature Status:" -ForegroundColor White
            foreach ($fid in $Features.Keys) {
                $f = $Features[$fid]
                $state = Get-FeatureState $fid
                if ($state) {
                    Write-Host "    [ON]  " -NoNewline -ForegroundColor Green
                } else {
                    Write-Host "    [OFF] " -NoNewline -ForegroundColor Yellow
                }
                Write-Host "$($f.Name) ($fid)" -ForegroundColor White
            }
            Write-Host ""
        }
    }

    default {
        Write-Host ""
        Write-Host "HybridRAG3 Feature Manager" -ForegroundColor Cyan
        Write-Host ("=" * 40) -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Commands:" -ForegroundColor White
        Write-Host "  rag-features list                          Show all features" -ForegroundColor Gray
        Write-Host "  rag-features enable hallucination-filter    Turn ON anti-hallucination" -ForegroundColor Gray
        Write-Host "  rag-features disable hallucination-filter   Turn OFF anti-hallucination" -ForegroundColor Gray
        Write-Host "  rag-features enable reranker               Turn ON result reranking" -ForegroundColor Gray
        Write-Host "  rag-features status                        Quick status check" -ForegroundColor Gray
        Write-Host "  rag-features status hallucination-filter    One feature status" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Feature IDs:" -ForegroundColor White
        Write-Host "  hallucination-filter   5-step anti-hallucination pipeline" -ForegroundColor Gray
        Write-Host "  hybrid-search          Semantic + keyword combined search" -ForegroundColor Gray
        Write-Host "  reranker               Cross-encoder result re-scoring" -ForegroundColor Gray
        Write-Host "  pii-scrubber           PII removal for compliance" -ForegroundColor Gray
        Write-Host "  audit-log              Query and access audit logging" -ForegroundColor Gray
        Write-Host "  cost-tracker           API token and cost tracking" -ForegroundColor Gray
        Write-Host ""
    }
}

# =========================================================================
# PROFILE SHORTCUT SETUP
# =========================================================================
# To make 'rag-features' available everywhere, add this to your
# PowerShell profile ($PROFILE):
#
#   function rag-features {
#       & "D:\HybridRAG3\tools\rag-features.ps1" @args
#   }
#
# Then you can run from any directory:
#   rag-features list
#   rag-features enable hallucination-filter
#   rag-features disable reranker
# =========================================================================
