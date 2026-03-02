# CODE UPDATE VERIFICATION CHECKLIST

Run this after every push to catch sync gaps before they become work-machine surprises.

## After git push origin main (HybridRAG3)

- [ ] Commit hash matches what you expect (`git log --oneline -1`)

## After sync_to_educational.py

- [ ] Commit landed in Educational (`cd D:\HybridRAG3_Educational && git log --oneline -1`)
- [ ] Changed files appear in diff (`git diff HEAD~1 --name-only`)
- [ ] Grep for the critical fix keyword in Educational repo
  - Example: `grep -r "trust_env" src/` or `grep -r "nomic-embed-text" config/`
- [ ] Any NEW files? Check they aren't in a skipped directory
  - Skipped dirs: `05_security`, `.claude`, `output/`, `logs/`, `data/`
  - Full list: `SKIP_PATTERNS` in `tools/sync_to_educational.py`
- [ ] If a file is blocked and shouldn't be, move it out of the skipped directory

## After git push origin main (Educational)

- [ ] Remote push succeeded (no permission errors, no rejected refs)
- [ ] Spot-check one critical file on GitHub web UI if unsure

## Quick One-Liner Verification

```bash
cd D:\HybridRAG3_Educational
git diff HEAD~1 --stat
grep -r "THE_FIX_KEYWORD" src/ config/ tools/
```

Replace THE_FIX_KEYWORD with whatever the session's critical change was
(e.g. trust_env, nomic-embed-text, canonicalize, etc.)

## Known Skip Patterns That Block Code

These directories are excluded from Educational by design:

| Directory | Reason |
|-----------|--------|
| `docs/05_security/` | Audit docs, waiver sheets, git rules (private) |
| `.claude/` | Session data (private) |
| `output/` | Test reports, generated files |
| `logs/` | Runtime logs |
| `data/` | Indexed data |

If a critical doc lands in one of these, either move it or add an exception
to `tools/sync_to_educational.py` SKIP_PATTERNS.
