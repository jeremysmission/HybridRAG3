# Install Script Bug Findings and Resolution

Date: 2026-02-25
Affected files: `tools/setup_work.ps1`, `tools/setup_home.ps1`, `INSTALL.bat`

---

## Bug 1: BOM Encoding Breaks Python Consumers (Session 18)

**Symptom**: Python parsers (YAML, pip config) fail to read config files written by setup scripts. Error messages reference unexpected bytes at start of file.

**Root Cause**: PowerShell 5.1's `Set-Content -Encoding UTF8` and `Out-File -Encoding UTF8` write a UTF-8 BOM (Byte Order Mark, 3 bytes: `EF BB BF`). BOM is correct for `.ps1` files but breaks Python parsers for `.yaml`, `.ini`, `.cfg`, `.toml`, `.json` files.

**How Discovered**: Manual testing on work laptop. Python's YAML parser refused to load `default_config.yaml`. Hex inspection revealed BOM bytes.

**Fix**: Use `[System.IO.File]::WriteAllText()` for any file consumed by Python. `Set-Content -Encoding UTF8` is only used for `.ps1` files (which benefit from BOM). project config updated to scope the BOM rule to `.ps1` files only.

**Prevention**: Test group 7 ("Cross-Runtime BOM Safety") in `tests/virtual_test_setup_scripts.py` now validates:
- All Python-consumed files use `WriteAllText` (no BOM)
- YAML config does not use `Set-Content`
- pip.ini does not use `Out-File`

---

## Bug 2: Comma Operator Precedence Crashes `$headerLines` (Session 19)

**Symptom**: `Cannot convert the "System.Object[]" value of type "System.Object[]" to type "System.Int32"` at `$headerLines = @(` in step 7 of `setup_work.ps1`.

**Root Cause**: PowerShell's comma operator (`,`) has **higher precedence** than the multiplication operator (`*`). In the expression `"=" * 70, "next string"`, PowerShell parses this as `"=" * (70, "next string")` -- trying to multiply a string by an Object array.

This is documented behavior per the [PowerShell Operator Precedence table](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_operator_precedence):
- Comma operator: rank 7
- Multiplication: rank 10

This is NOT a PS 5.1 vs PS 7 difference -- the precedence is identical in both.

**How Discovered**: User ran INSTALL.bat on work laptop, reported error message. Confirmed by reproducing in PowerShell: `@("=" * 70, "hello")` throws the same error, while `@(("=" * 70), "hello")` succeeds.

**Fix**: Wrap all `"=" * N` expressions in parentheses: `("=" * 70)`. Three instances in `setup_work.ps1` lines 568, 570, 581.

**Prevention**: Test group 8 ("PS 5.1 Gotcha Patterns") in `tests/virtual_test_setup_scripts.py` now scans for the regex pattern `"..." * N,` (unparenthesized string multiplication followed by comma) and fails if found.

---

## Bug 3: pip stderr WARNING Crashes Script in PS 5.1 (Session 19)

**Symptom**: Step 5 (pip upgrade) crashes with `NativeCommandError` when pip outputs a WARNING about invalid metadata. Script shows "Setup encountered an issue" banner and exits.

**Root Cause**: PowerShell 5.1 converts ALL native command stderr output to `ErrorRecord` objects. With `$ErrorActionPreference = 'Stop'` (set at top of script), these ErrorRecords become **terminating errors** that crash the script immediately -- before `$LASTEXITCODE` can be checked. Even harmless pip WARNINGs (like "Skipping ... due to invalid metadata entry 'name'") trigger this.

PowerShell 7 fixed this behavior (native command stderr no longer creates ErrorRecords by default), but the work/education laptops run PS 5.1.

**How Discovered**: User ran INSTALL.bat on personal computer with a test directory. pip outputted a WARNING about corrupted `pip-24.0.dist-info`, which PS 5.1 converted to a terminating error.

**Fix**: Set `$ErrorActionPreference = 'Continue'` at the start of Phase 2 (automated setup). Phase 2 pip/python calls already have their own error handling via `$LASTEXITCODE` checks and `while (-not $stepDone)` recovery loops. Cmdlets inside `try/catch` blocks now have explicit `-ErrorAction Stop` so they still throw when needed.

Applied to both `setup_work.ps1` and `setup_home.ps1`.

**Prevention**: Test group 8 ("PS 5.1 Gotcha Patterns") validates:
- `$ErrorActionPreference = 'Continue'` is set in Phase 2
- Cmdlets inside `try/catch` blocks have explicit `-ErrorAction Stop`

---

## Bug 4: Python Version Reference (Session 19)

**Symptom**: Error message in `setup_work.ps1` says "Request Python 3.11 or 3.12" but the work machine runs Python 3.12. `INSTALL.bat` says "Python 3.10 or newer".

**Root Cause**: Stale text from when the project supported Python 3.11. The education repo should recommend Python 3.12.

**Fix**: Updated `setup_work.ps1` line 223 to say "Python 3.12". Updated `INSTALL.bat` line 87 to say "Python 3.12 or newer". The detection loop still accepts 3.10-3.12 (for backwards compatibility) but the user-facing message recommends 3.12.

---

## Bug 5: Silent Step Failures -- No Recovery (Session 19)

**Symptom**: Steps 4 (venv), 9/10 (config/template), 11 (API creds), and 13 (diagnostics) in `setup_work.ps1` either `exit 1` on failure or fail silently. Same gaps in `setup_home.ps1` steps 4, 7, 8, 10. Step 6 (home packages) had retry but no drill-down.

**Root Cause**: Recovery loops `[R/S/X]` were added to some steps but not all. Inconsistent error handling across the script.

**Fix**: Added `Request-Recovery` with `[R/S/X]` (or `[R/D/S/X]` for drill-down) to every step that can fail:

| Script | Step | Before | After |
|--------|------|--------|-------|
| setup_work.ps1 | 4 (venv) | `exit 1` | Recovery loop [R/S/X] |
| setup_work.ps1 | 9 (config YAML) | Silent | try/catch + [R/S/X] |
| setup_work.ps1 | 10 (template) | Silent | try/catch + [R/S/X] |
| setup_work.ps1 | 11 (API creds) | No error check | $LASTEXITCODE + [R/S/X] |
| setup_work.ps1 | 13 (diagnostics) | Straight through | [R/D/S/X] drill-down |
| setup_home.ps1 | 4 (venv) | `exit 1` | Recovery loop [R/S/X] |
| setup_home.ps1 | 6 (packages) | Retry only | Added [D] drill-down |
| setup_home.ps1 | 7 (config YAML) | Silent | try/catch + [R/S/X] |
| setup_home.ps1 | 8 (start script) | Silent | try/catch + [R/S/X] |
| setup_home.ps1 | 10 (diagnostics) | Straight through | [R/D/S/X] drill-down |

---

## Prevention: Tooling Added

### 1. Virtual Test Pattern Checks (Python, zero dependencies)

`tests/virtual_test_setup_scripts.py` test group 8 ("PS 5.1 Gotcha Patterns"):
- Scans for unparenthesized `"string" * N,` patterns (comma precedence bug)
- Validates `$ErrorActionPreference = 'Continue'` in Phase 2 (stderr-as-error)
- Validates cmdlets in try/catch have `-ErrorAction Stop` (error propagation)

Run: `python tests/virtual_test_setup_scripts.py`

### 2. PSScriptAnalyzer (PowerShell module, optional)

`PSScriptAnalyzerSettings.psd1` in project root configures rules. Install and run:

```powershell
Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser
Invoke-ScriptAnalyzer -Path tools/setup_work.ps1 -Settings PSScriptAnalyzerSettings.psd1
Invoke-ScriptAnalyzer -Path tools/setup_home.ps1 -Settings PSScriptAnalyzerSettings.psd1
```

PSScriptAnalyzer catches: unused variables, assignment to automatic variables (`$Host`), empty catch blocks, security issues, missing mandatory parameters.

PSScriptAnalyzer does NOT catch: runtime type conversion errors (the comma precedence bug), BOM encoding issues, or stderr-as-error quirks. Those require the pattern-based Python tests above.

### 3. PowerShell Built-in Syntax Check (zero install)

```powershell
$errors = $null; $tokens = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    'tools\setup_work.ps1', [ref]$tokens, [ref]$errors)
$errors | ForEach-Object { "LINE $($_.Extent.StartLineNumber): $($_.Message)" }
```

### Summary: What Catches What

| Bug Class | Virtual Test | PSScriptAnalyzer | PS Parser |
|-----------|:---:|:---:|:---:|
| Comma precedence (`"=" * N,`) | Yes | No | No |
| BOM on Python files | Yes | No | No |
| ErrorActionPreference in Phase 2 | Yes | No | No |
| -ErrorAction Stop in try/catch | Yes | No | No |
| Syntax errors (missing braces) | No | Yes | Yes |
| Unused variables | No | Yes | No |
| Assignment to $Host/$Error | No | Yes | No |
| Empty catch blocks | No | Yes | No |
| Security (plaintext passwords) | No | Yes | No |
