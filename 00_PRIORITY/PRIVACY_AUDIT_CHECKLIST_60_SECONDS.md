# Privacy Audit Checklist (60 Seconds)

## GitHub visibility
1. GitHub -> each repo -> `Settings` -> `General` -> confirm `Private`.
2. Check forks: repo page -> `Insights` -> `Network` (no unintended public forks).
3. Check profile tab for `Public repositories` count (should match intent).

## Account security
1. `Settings` -> `Password and authentication` -> `2FA` enabled.
2. `Settings` -> `Developer settings` -> `Personal access tokens`:
- Revoke old/unused tokens.
- Use separate token per device.
3. `Settings` -> `Sessions`:
- Sign out unknown devices.

## Data exposure checks
1. Repo -> `Actions` logs: confirm no secrets printed.
2. Repo -> `Security` -> `Secret scanning` alerts.
3. Search in repo for risky terms:
```powershell
rg -n "api[_-]?key|secret|token|password|Co-Authored-By|noreply@anthropic|SCIF|ITAR|CUI"
```

## If anything is exposed
1. Rotate affected credentials immediately.
2. Remove/replace exposed content.
3. If needed, rewrite git history and force push.
