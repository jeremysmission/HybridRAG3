# Recommended PowerShell Analyzer Tools

**Date:** 2026-02-25
**Purpose:** Catch PS 5.1 bugs at design time before they reach runtime

## Why This Exists

Setup scripts (`setup_work.ps1`, `setup_home.ps1`) run on PowerShell 5.1 on
Windows machines with no control over the PS version. We have hit recurring
bugs that slip through Python-based virtual tests and pytest:

| Bug Pattern | Example | Impact |
|-------------|---------|--------|
| Expression parsing in `@()` | `"=" * 70` inside array literal | PS 5.1 type coercion crash |
| Native command stderr | pip WARNING + `$ErrorActionPreference='Stop'` | NativeCommandError terminates script |
| UTF-8 BOM injection | `Set-Content -Encoding UTF8` on .yaml/.ini | Python parsers choke on BOM bytes |
| Pipeline exit code loss | `& pip install ... \| Out-String` | `$LASTEXITCODE` clobbered by pipeline cmdlet |
| Variable scoping | Reading parent-scope `$var` without declaration | Silent wrong values |

**None of these are caught by text-pattern tests.** They require AST-level
static analysis or runtime integration tests.

---

## Tool Stack (Ranked by Priority)

### 1. PSScriptAnalyzer 1.24.0 -- Static Linter

The official Microsoft linter. Uses PowerShell AST parsing to find bugs
before runtime. 68 built-in rules plus support for custom rules.

**Install:**
```powershell
Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser
```

**Run against our scripts:**
```powershell
Invoke-ScriptAnalyzer -Path ./tools -Recurse -Settings ./PSScriptAnalyzerSettings.psd1
```

**Key built-in rules for our use case:**

| Rule | What It Catches |
|------|----------------|
| `PSUseCompatibleSyntax` | Syntax that fails on PS 5.1 (ternary, null coalescing, etc.) |
| `PSUseCompatibleCmdlets` | Cmdlets that do not exist on PS 5.1 |
| `PSUseCompatibleTypes` | .NET types unavailable on target platform |
| `PSAvoidAssignmentToAutomaticVariable` | Accidental overwrites of `$_`, `$Error`, etc. |
| `PSUseDeclaredVarsMoreThanAssignments` | Unused variable declarations (partial scoping help) |

**What it CANNOT catch (requires custom rules or Pester):**
- BOM injection from Set-Content (built-in rule wants BOM -- opposite of our need)
- `$ErrorActionPreference` interaction with native command stderr
- `$LASTEXITCODE` clobbered by pipeline
- Expression evaluation inside `@()` array literals

**Links:**
- Repository: https://github.com/PowerShell/PSScriptAnalyzer
- Rules list: https://learn.microsoft.com/en-us/powershell/utility-modules/psscriptanalyzer/rules/readme

---

### 2. Custom PSScriptAnalyzer Rules -- Our Specific Bug Patterns

PSScriptAnalyzer supports custom rules as `.psm1` modules. Each rule
walks the PowerShell AST and returns diagnostic records. This is the
**highest-value investment** because it catches our exact recurring bugs.

**Location:** `tools/lint/HybridRAG3Rules.psm1`

**Run with custom rules:**
```powershell
Invoke-ScriptAnalyzer -Path ./tools/setup_work.ps1 `
    -Settings ./PSScriptAnalyzerSettings.psd1 `
    -CustomRulePath ./tools/lint/HybridRAG3Rules.psm1
```

#### Rule A: String multiplication inside @() arrays

Catches `"=" * 70` inside `@()` where PS 5.1 can misinterpret the `*`
operator as applying to the array rather than the string.

**Pattern detected:**
```powershell
# BAD -- PS 5.1 may interpret this as array multiplication
$lines = @(
    "=" * 70,
    "Header"
)

# GOOD -- parentheses force expression evaluation first
$lines = @(
    ("=" * 70),
    "Header"
)
```

**AST approach:** Walk `ArrayLiteralAst` nodes, check each element for
`BinaryExpressionAst` with `Multiply` operator.

#### Rule B: BOM-dangerous encoding on non-.ps1 files

Catches `Set-Content` or `Out-File` with `-Encoding UTF8` which adds BOM
in PS 5.1. Files consumed by Python (.yaml, .ini, .cfg, .toml, .json)
must use `[System.IO.File]::WriteAllText()` instead.

**Pattern detected:**
```powershell
# BAD -- adds BOM in PS 5.1, breaks Python YAML/INI parsers
Set-Content -Path $configPath -Value $content -Encoding UTF8

# GOOD -- no BOM
[System.IO.File]::WriteAllText($configPath, $content)
```

**AST approach:** Walk `CommandAst` nodes where command name is
`Set-Content` or `Out-File` and a parameter named `Encoding` is present.

**Note:** `Set-Content -Encoding UTF8` is correct for `.ps1` files (they
need BOM for PS 5.1 to recognize UTF-8). The rule should flag it as a
warning so the developer confirms the target file type.

#### Rule C: Native command piped directly to cmdlet

Catches patterns where `$LASTEXITCODE` gets clobbered because a native
command (pip, python, git, ollama) is piped to a PowerShell cmdlet.

**Pattern detected:**
```powershell
# BAD -- pipeline cmdlet overwrites $LASTEXITCODE
& pip install pyyaml | Out-String
if ($LASTEXITCODE -ne 0) { ... }  # UNRELIABLE

# GOOD -- capture to variable first
$output = & pip install pyyaml 2>&1
$exitCode = $LASTEXITCODE
```

**AST approach:** Walk `PipelineAst` nodes with >1 element where the first
element is a known native executable name.

#### Rule D: $ErrorActionPreference='Stop' with native commands

Warns when a script sets `$ErrorActionPreference = 'Stop'` globally and
also calls native executables. In PS 5.1, stderr from native commands
becomes a terminating `NativeCommandError`.

**Pattern detected:**
```powershell
# DANGEROUS in PS 5.1 -- pip WARNING on stderr terminates script
$ErrorActionPreference = 'Stop'
& pip install --upgrade pip 2>&1

# SAFE -- switch to Continue before native calls
$ErrorActionPreference = 'Continue'
& pip install --upgrade pip 2>&1
$exitCode = $LASTEXITCODE
```

**AST approach:** Find `AssignmentStatementAst` where left side is
`ErrorActionPreference` and right side contains `'Stop'`, then check if
any `CommandAst` in the same scope calls a known native executable.

---

### 3. Pester 5.7.1 -- PowerShell Unit/Integration Testing

The standard test framework for PowerShell. Catches runtime behavior that
static analysis cannot detect.

**Install:**
```powershell
# Remove built-in Pester 3.x first (run as Admin on Windows 10):
$module = "C:\Program Files\WindowsPowerShell\Modules\Pester"
& takeown /F $module /A /R
& icacls $module /reset
& icacls $module /grant "*S-1-5-32-544:F" /inheritance:d /T
Remove-Item -Path $module -Recurse -Force -ErrorAction SilentlyContinue

# Install Pester 5:
Install-Module -Name Pester -Force -Scope CurrentUser -SkipPublisherCheck
```

**Example tests for our bug patterns:**

```powershell
Describe 'BOM Safety' {
    It 'WriteAllText produces no BOM on .yaml files' {
        $testFile = Join-Path $TestDrive 'test.yaml'
        [System.IO.File]::WriteAllText($testFile, "key: value")
        $bytes = [System.IO.File]::ReadAllBytes($testFile)
        ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) |
            Should -BeFalse
    }

    It 'Set-Content adds BOM in PS 5.1 (proving the bug exists)' {
        $testFile = Join-Path $TestDrive 'test_bom.yaml'
        Set-Content -Path $testFile -Value "key: value" -Encoding UTF8
        $bytes = [System.IO.File]::ReadAllBytes($testFile)
        if ($PSVersionTable.PSVersion.Major -le 5) {
            ($bytes[0] -eq 0xEF) | Should -BeTrue
        }
    }
}

Describe 'Array Expression Safety' {
    It 'String multiplication in @() with parens produces string' {
        $result = @(("=" * 5), "header")
        $result[0] | Should -BeOfType [string]
        $result[0].Length | Should -Be 5
    }
}

Describe 'Native Command Error Handling' {
    It 'pip warnings do not throw with ErrorActionPreference Continue' {
        $ErrorActionPreference = 'Continue'
        { & pip --version 2>&1 | Out-Null } | Should -Not -Throw
    }
}
```

**Run:**
```powershell
Invoke-Pester -Path ./tests/*.Tests.ps1 -Output Detailed
```

**Links:**
- Documentation: https://pester.dev/
- Repository: https://github.com/pester/Pester

---

### 4. VS Code PowerShell Extension -- Real-Time Feedback

Bundles PSScriptAnalyzer and runs it as you type. Custom rules show as
squiggly underlines in the editor.

**Configuration** (add to `.vscode/settings.json`):
```json
{
    "powershell.scriptAnalysis.enable": true,
    "powershell.scriptAnalysis.settingsPath": "./PSScriptAnalyzerSettings.psd1"
}
```

This gives immediate visual feedback when a developer writes a dangerous
pattern, before they even save the file.

---

### 5. Pre-Commit Hook -- Gate Before Every Commit

Runs PSScriptAnalyzer on staged `.ps1` files and blocks the commit if
any warnings are found.

**File:** `.git/hooks/pre-commit`

```bash
#!/bin/sh
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
    Import-Module PSScriptAnalyzer -ErrorAction Stop
    \$files = git diff --cached --name-only --diff-filter=ACM |
        Where-Object { \$_ -match '\.ps1\$' }
    if (-not \$files) { exit 0 }
    \$errors = @()
    foreach (\$f in \$files) {
        \$r = Invoke-ScriptAnalyzer -Path \$f \`
            -Settings ./PSScriptAnalyzerSettings.psd1 \`
            -CustomRulePath ./tools/lint/HybridRAG3Rules.psm1 \`
            -Severity Error,Warning
        \$errors += \$r
    }
    if (\$errors.Count -gt 0) {
        Write-Host 'PSScriptAnalyzer blocked commit:' -ForegroundColor Red
        foreach (\$e in \$errors) {
            Write-Host \"  \$(\$e.ScriptName):\$(\$e.Line) [\$(\$e.RuleName)] \$(\$e.Message)\" -ForegroundColor Yellow
        }
        exit 1
    }
    Write-Host '[OK] PSScriptAnalyzer: all staged .ps1 files clean' -ForegroundColor Green
    exit 0
"
```

---

### 6. Native Module (Optional) -- Runtime Exit Code Safety

Provides `iee` (Invoke-Executable with Error) which properly handles
native command exit codes and stderr routing.

**Install:**
```powershell
Install-Module -Name Native -Scope CurrentUser
```

**Usage:**
```powershell
# Instead of: & pip install pyyaml
# Use:
iee pip install pyyaml  # throws on non-zero exit code
```

**Relevance:** Directly solves `$LASTEXITCODE` clobbering (bug 6) and
partially helps with stderr handling (bug 2). Trade-off is adding a
module dependency to setup scripts that are designed to run on bare
machines.

**Link:** https://github.com/mklement0/Native

---

## Project Configuration File

**File:** `PSScriptAnalyzerSettings.psd1` (project root)

```powershell
@{
    Severity            = @('Error', 'Warning', 'Information')
    IncludeDefaultRules = $true
    CustomRulePath      = @('./tools/lint/HybridRAG3Rules.psm1')

    ExcludeRules = @(
        'PSAvoidUsingWriteHost'
        'PSUseShouldProcessForStateChangingFunctions'
    )

    Rules = @{
        PSUseCompatibleSyntax = @{
            Enable         = $true
            TargetVersions = @('5.1', '7.4')
        }
        PSUseCompatibleCmdlets = @{
            Enable        = $true
            Compatibility = @('desktop-5.1.14393.206-windows')
        }
    }
}
```

---

## Coverage Matrix

| Bug Pattern | PSScriptAnalyzer Built-in | Custom Rule | Pester Test | Pre-Commit |
|-------------|:------------------------:|:-----------:|:-----------:|:----------:|
| `"=" * 70` in `@()` | -- | Rule A | Yes | Yes |
| stderr + `$ErrorActionPreference='Stop'` | -- | Rule D (warns) | Yes | Yes |
| BOM from Set-Content | Wrong direction | Rule B | Yes | Yes |
| `$LASTEXITCODE` clobbered | -- | Rule C | Yes | Yes |
| Variable scoping | Partial | -- | Yes | Partial |
| PS 5.1 syntax compat | Yes | -- | -- | Yes |

---

## What No Tool Can Catch

These require manual review or Pester integration tests:

- **Host-dependent stderr behavior** -- whether stderr becomes a terminating
  error depends on the PS host (console vs ISE vs remoting), not the script
- **Dynamic type coercion** -- runtime values flowing through pipelines can
  trigger Object[] to Int32 conversion that static analysis cannot predict
- **Complex expression precedence** -- subtle parsing differences between
  PS 5.1 and 7.x in edge cases beyond what compatibility rules cover

For these gaps, Pester integration tests that actually execute the code
paths on PS 5.1 are the only safeguard.

---

## Implementation Order

1. **Install PSScriptAnalyzer** and run against existing scripts (30 min)
2. **Create custom rules module** at `tools/lint/HybridRAG3Rules.psm1` (1-2 hrs)
3. **Add PSScriptAnalyzerSettings.psd1** to project root (5 min)
4. **Add pre-commit hook** to block commits with PS lint failures (15 min)
5. **Write Pester tests** for BOM safety, exit codes, stderr handling (1-2 hrs)
6. **Add VS Code settings** for real-time feedback during editing (5 min)
