# ===========================================================================
# detect_bad_chars.ps1 -- Non-ASCII Character Detector
# ===========================================================================
#
# WHAT THIS DOES (PLAIN ENGLISH):
#   Scans your code files for characters that will cause syntax errors.
#   It does NOT modify anything -- it just REPORTS what it finds.
#   Think of it as a metal detector that beeps when it finds something.
#
# WHY YOU NEED THIS:
#   When you copy-paste code, invisible "bad" characters can sneak in.
#   They look identical to normal characters on screen, but Python and
#   PowerShell treat them as completely different. The most common ones
#   are curly/smart quotes (the #1 copy-paste villain).
#
# HOW TO RUN:
#   .\tools\detect_bad_chars.ps1                        # Scan current dir
#   .\tools\detect_bad_chars.ps1 -Path "myfile.py"      # Scan one file
#   .\tools\detect_bad_chars.ps1 -Path "D:\HybridRAG3"  # Scan a project
#
# OR use the rag command (after loading new_commands):
#   rag-detect-bad-chars
#
# WHAT IT REPORTS:
#   For each bad character found:
#     - Which file it is in
#     - What line and column number
#     - The Unicode code (a number that identifies the character)
#     - A description (e.g., "Left double smart quote")
#     - The fix command to run
#
# WHERE IT GOES IN YOUR PROJECT:
#   D:\HybridRAG3\tools\detect_bad_chars.ps1
# ===========================================================================


# ---------------------------------------------------------------------------
# PARAMETERS
# ---------------------------------------------------------------------------
# -Path: What to scan. Default "." means current directory.

param(
    [string]$Path = "."
)

$problemFiles = 0    # Counter: how many files had problems
$totalProblems = 0   # Counter: total bad characters found across all files


# ---------------------------------------------------------------------------
# KNOWN BAD CHARACTERS LOOKUP TABLE
# ---------------------------------------------------------------------------
# POWERSHELL CONCEPT - @{} (Hashtable):
#   A hashtable is like a dictionary. Each entry has a "key" (the Unicode
#   number) and a "value" (the human-readable description). When we find
#   a bad character, we look up its number here to get a description.

$badChars = @{
    8220  = "Left double smart quote (curly)"
    8221  = "Right double smart quote (curly)"
    8216  = "Left single smart quote (curly)"
    8217  = "Right single smart quote (curly)"
    8212  = "Em dash (extra long dash from Word)"
    8211  = "En dash (medium dash)"
    8230  = "Horizontal ellipsis (one char, not three dots)"
    160   = "Non-breaking space (looks like space, is not)"
    65279 = "UTF-8 BOM (invisible byte-order-mark at file start)"
}


# ---------------------------------------------------------------------------
# SCAN FUNCTION
# ---------------------------------------------------------------------------
# Reads a file character by character and flags anything with a Unicode
# code above 127 (all standard code characters are 0-127, called "ASCII").
# Anything above 127 is a non-ASCII character and is suspicious in code.

function Scan-FileChars {
    param([string]$FilePath)

    $content = [System.IO.File]::ReadAllText($FilePath)
    $chars = $content.ToCharArray()  # Split the text into individual characters
    $issues = @()   # Empty list to collect problems
    $lineNum = 1    # Track which line we are on
    $colNum = 0     # Track which column (character position) on the line

    # Go through every character in the file
    foreach ($char in $chars) {
        $colNum++

        # Newline character means we moved to the next line
        if ($char -eq "`n") {
            $lineNum++
            $colNum = 0
            continue   # Skip to next character
        }

        # [int]$char converts the character to its Unicode number.
        # Characters 0-127 are standard ASCII (safe for code).
        # Anything above 127 is non-ASCII (suspicious).
        $code = [int]$char
        if ($code -gt 127) {
            # Look up the description, or use "Unknown non-ASCII" as fallback
            if ($badChars.ContainsKey($code)) {
                $desc = $badChars[$code]
            } else {
                $desc = "Unknown non-ASCII character"
            }

            # Add this issue to our list
            # [PSCustomObject] creates a structured record with named fields
            $issues += [PSCustomObject]@{
                Line = $lineNum
                Col  = $colNum
                Char = $char
                Code = $code
                Desc = $desc
            }
        }
    }

    # Report findings for this file
    if ($issues.Count -gt 0) {
        $script:problemFiles++
        $script:totalProblems += $issues.Count
        Write-Host ""
        Write-Host "  [BAD] $FilePath -- $($issues.Count) problem(s)" -ForegroundColor Red

        # Show first 10 issues per file (to avoid flooding the screen)
        $shown = 0
        foreach ($issue in $issues) {
            if ($shown -ge 10) {
                Write-Host "        ... and $($issues.Count - 10) more" -ForegroundColor Yellow
                break
            }
            # The -f operator is PowerShell's string formatting.
            # {0} {1} etc. are placeholders filled by the values after -f
            Write-Host ("        Line {0}, Col {1}: U+{2:X4} ({3})" -f $issue.Line, $issue.Col, $issue.Code, $issue.Desc) -ForegroundColor Yellow
            $shown++
        }

        Write-Host "        FIX: Run  .\tools\fix_quotes.ps1 -Path `"$FilePath`"" -ForegroundColor Cyan
    }
}


# ---------------------------------------------------------------------------
# MAIN LOGIC
# ---------------------------------------------------------------------------

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Non-ASCII Character Detector" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (Test-Path $Path -PathType Leaf) {
    # Single file mode
    Write-Host "Scanning: $Path"
    Scan-FileChars -FilePath $Path

} elseif (Test-Path $Path -PathType Container) {
    # Directory mode -- scan all code files, skip junk folders
    $files = Get-ChildItem -Path $Path -Recurse -Include "*.py","*.ps1","*.yaml","*.yml" |
             Where-Object { $_.FullName -notmatch "\.venv|__pycache__|\.git|node_modules|\.bak" }

    Write-Host "Scanning $($files.Count) files in: $Path"

    foreach ($file in $files) {
        Scan-FileChars -FilePath $file.FullName
    }
} else {
    Write-Host "[ERROR] Path not found: $Path" -ForegroundColor Red
    exit 1
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($problemFiles -eq 0) {
    Write-Host "ALL CLEAN -- No bad characters found" -ForegroundColor Green
} else {
    Write-Host "FOUND $totalProblems problems in $problemFiles files" -ForegroundColor Red
    Write-Host "Run: .\tools\fix_quotes.ps1 to fix automatically" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor Cyan
