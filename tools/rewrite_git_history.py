"""
Rewrite git commit messages to remove banned words.
Strips Co-Authored-By lines, claude.ai URLs, and replaces
CLAUDE.md references. Run via git-filter-repo --message-callback.

Usage:
  git filter-repo --message-callback "$(cat tools/rewrite_git_history.py)" --force
"""
import re

# 1. Remove Co-Authored-By lines (any variant)
message = re.sub(
    rb'\n*\s*Co-Authored-By:.*?<[^>]*>[ \t]*',
    b'',
    message,
    flags=re.IGNORECASE
)

# 2. Remove claude.ai session URLs
message = re.sub(
    rb'https?://claude\.ai/code/session_[A-Za-z0-9_]+\s*',
    b'',
    message
)

# 3. Replace "CLAUDE.md" with "PROJECT.md" in commit messages
message = re.sub(rb'CLAUDE\.md', b'PROJECT.md', message)

# 4. Replace standalone "Claude" references (word boundary)
# Catches: "Claude 4", "Claude Opus", "Claude references", etc.
# Does NOT catch: "excluded" (no word boundary match)
message = re.sub(
    rb'\bClaude\b',
    b'AI assistant',
    message,
    flags=re.IGNORECASE
)

# 5. Replace "Anthropic" references
message = re.sub(
    rb'\bAnthropic\b',
    b'AI provider',
    message,
    flags=re.IGNORECASE
)

# 6. Clean up trailing whitespace and excess blank lines
message = re.sub(rb'\n{3,}', b'\n\n', message)
message = message.rstrip() + b'\n'
