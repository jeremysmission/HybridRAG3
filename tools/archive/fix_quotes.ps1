# ===========================================================================
# fix_quotes.ps1 -- Smart Quote and Bad Character Fixer
# ===========================================================================
#
# WHAT THIS DOES (PLAIN ENGLISH):
#   Scans your code files looking for "bad" characters that snuck in
#   from copy-pasting, and replaces them with correct ones. Think of it
#   as a spell-checker for invisible character corruption.
#
# THE CHARACTERS IT FIXES:
#   - Curly double quotes    -> straight double quotes
#   - Curly single quotes    -> straight single quotes (apostrophes)
#   - Em dash (long dash)    -> two hyphens
#   - En dash (medium dash)  -> one hyphen
#   - Ellipsis character     -> three dots
#   - Non-breaking space     -> normal space
#   - UTF-8 BOM in .py files -> removed
#
# SAFETY: Creates a .bak backup of every file BEFORE modifying it.
#         If something goes wrong, rename .bak back to original.
#
# HOW TO RUN:
#   .\tools\fix_quotes.ps1                        # Fix all files in current dir
#   .\tools\fix_quotes.ps1 -Path "myfile.py"      # Fix one specific file
#   .\tools\fix_quotes.ps1 -Path "D:\HybridRAG3"  # Fix all files in a project
#
# OR use the rag command (after loading new_commands):
#   rag-fix-quotes
#
# WHERE IT GOES IN YOUR PROJECT:
#   D:\HybridRAG3\tools\fix_quotes.ps1
# ===========================================================================


# ---------------------------------------------------------------------------
# PARAMETERS
# ---------------------------------------------------------------------------
# POWERSHELL CONCEPT - param():
#   Defines inputs this script accepts from the command line.
#   -Path tells it what to scan. Default "." means current directory.
#   [string] means the input must be text.

param(
    [string]$Path = "."
)

# Counters for the summary report at the end
$fixCount = 0    # How many files had problems and were fixed
$fileCount = 0   # How many files we scanned total


# ---------------------------------------------------------------------------
# THE FIX FUNCTION
# ---------------------------------------------------------------------------
# POWERSHELL CONCEPT - function:
#   A reusable block of code with a name. We define it once, then
#   call it for each file. Avoids writing the same logic repeatedly.
#
# WHAT IT DOES FOR EACH FILE:
#   1. Reads the entire file into memory
#   2. Runs -replace operations to swap bad chars for good ones
#   3. Compares result with original to see if anything changed
#   4. If changed: backs up original, writes fixed version
#   5. Uses correct encoding (.py = UTF-8 no BOM, .ps1 = UTF-8 with BOM)

function Fix-FileQuotes {
    param([string]$FilePath)

    # Read using .NET (not Get-Content) to avoid PowerShell encoding quirks
    $content = [System.IO.File]::ReadAllText($FilePath)
    $original = $content  # Save original for comparison

    # ----- THE REPLACEMENTS -----
    # POWERSHELL CONCEPT - -replace:
    #   Uses "regex" (regular expression) patterns. Square brackets [XY]
    #   mean "match character X or character Y." \uXXXX is a Unicode
    #   character code -- a number that identifies a specific character.

    # Replace curly DOUBLE quotes with straight double quotes
    # \u201C = left curly double quote (tilts left)
    # \u201D = right curly double quote (tilts right)
    $content = $content -replace "[\u201C\u201D]", '"'

    # Replace curly SINGLE quotes with straight apostrophes
    # \u2018 = left curly single quote (like a tiny 6)
    # \u2019 = right curly single quote (like a tiny 9)
    $content = $content -replace "[\u2018\u2019]", "'"

    # Replace em dash with two hyphens (Word loves inserting em dashes)
    $content = $content -replace "\u2014", "--"

    # Replace en dash with regular hyphen
    $content = $content -replace "\u2013", "-"

    # Replace the ellipsis CHARACTER with three actual dots
    # (one Unicode character that looks like ... but is not three dots)
    $content = $content -replace "\u2026", "..."

    # Replace non-breaking space with normal space
    # (web pages use these; they look like spaces but are not)
    $content = $content -replace "\u00A0", " "

    # SPECIAL: Remove BOM from Python files
    # BOM = Byte Order Mark = invisible char at start of file (code 65279)
    # Windows adds this when saving as "UTF-8". Python can choke on it.
    if ($FilePath -match "\.py$") {
        if ($content.Length -gt 0 -and [int]$content[0] -eq 65279) {
            $content = $content.Substring(1)  # Remove first character (the BOM)
            Write-Host "  [FIX] Removed BOM from: $FilePath" -ForegroundColor Yellow
        }
    }

    # ----- DID ANYTHING CHANGE? -----
    # -ne means "not equal". If content differs from original, we fixed something.
    if ($content -ne $original) {
        # Create backup (adding .bak to filename)
        $backupPath = $FilePath + ".bak"
        [System.IO.File]::Copy($FilePath, $backupPath, $true)  # $true = overwrite

        # Write fixed content with correct encoding
        if ($FilePath -match "\.ps1$") {
            # PowerShell files: UTF-8 WITH BOM (PS 5.1 needs the BOM)
            $utf8Bom = New-Object System.Text.UTF8Encoding($true)
            [System.IO.File]::WriteAllText($FilePath, $content, $utf8Bom)
        } else {
            # Python and other files: UTF-8 WITHOUT BOM
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($FilePath, $content, $utf8NoBom)
        }

        $script:fixCount++  # $script: reaches the counter outside this function
        Write-Host "  [FIXED] $FilePath (backup: .bak)" -ForegroundColor Green
    } else {
        Write-Host "  [CLEAN] $FilePath" -ForegroundColor Gray
    }
}


# ---------------------------------------------------------------------------
# MAIN LOGIC -- Decide what to scan based on -Path parameter
# ---------------------------------------------------------------------------

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Smart Quote and Bad Character Fixer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (Test-Path $Path -PathType Leaf) {
    # -PathType Leaf means "this is a single file" (not a folder)
    Write-Host "Scanning single file: $Path"
    Fix-FileQuotes -FilePath $Path
    $fileCount = 1

} elseif (Test-Path $Path -PathType Container) {
    # -PathType Container means "this is a folder"
    Write-Host "Scanning directory: $Path"

    # Get-ChildItem = "list files". -Recurse = "go into subfolders too."
    # -Include = "only these file types." Where-Object filters out junk folders.
    $files = Get-ChildItem -Path $Path -Recurse -Include "*.py","*.ps1","*.yaml","*.yml","*.json" |
             Where-Object { $_.FullName -notmatch "\.venv|__pycache__|\.git|node_modules|\.bak" }

    Write-Host "Found $($files.Count) files to check"
    Write-Host ""

    foreach ($file in $files) {
        Fix-FileQuotes -FilePath $file.FullName
        $fileCount++
    }
} else {
    Write-Host "[ERROR] Path not found: $Path" -ForegroundColor Red
    exit 1
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RESULTS: Scanned $fileCount files, fixed $fixCount" -ForegroundColor Cyan
if ($fixCount -gt 0) {
    Write-Host "Backups created with .bak extension" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan

