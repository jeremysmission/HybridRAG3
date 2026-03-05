# === NON-PROGRAMMER GUIDE ===
# Purpose: Supports the psscriptanalyzersettings workflow in this repository.
# How to follow: Each key/value pair controls script analysis or formatting behavior.
# Inputs: Values defined in this settings file.
# Outputs: Affects how tools validate PowerShell scripts.
# ============================
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        'PSAvoidUsingWriteHost',
        'PSAvoidTrailingWhitespace',
        'PSUseApprovedVerbs',
        'PSProvideCommentHelp',
        'PSAvoidUsingPositionalParameters',
        'PSUseSingularNouns'
    )
}
