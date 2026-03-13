# HybridRAG3 Shared Deployment Security And Recovery Guide

**Created:** 2026-03-13 05:12 America/Denver  
**Purpose:** operator-facing security baseline and recovery procedure for the workstation-hosted shared deployment path.

## Scope

This guide covers the shared FastAPI and browser deployment path added in Sprints 6 through 12:

- shared token auth
- browser session cookies
- trusted proxy identity forwarding
- Admin role gating
- conversation-history encryption at rest
- auth/security activity review
- operator recovery after secret exposure or suspicious access activity

It does not claim that the main document index SQLite DB is application-encrypted at rest. The current at-rest protection implemented in Sprint 12 applies to the shared conversation-history DB when `HYBRIDRAG_HISTORY_ENCRYPTION_KEY` is configured.

## Current Security Controls

### Shared auth boundary

- `HYBRIDRAG_API_AUTH_TOKEN`
  - shared API and browser-login token
- `HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS`
  - previous shared token accepted during cutover
- `HYBRIDRAG_API_AUTH_LABEL`
  - actor label attached to shared-token access

### Browser session boundary

- `HYBRIDRAG_BROWSER_SESSION_SECRET`
  - primary browser-session signing secret
- `HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS`
  - previous browser-session secret accepted during rotation
- `HYBRIDRAG_BROWSER_SESSION_INVALID_BEFORE`
  - hard cutoff for invalidating existing browser sessions without waiting for TTL expiry

### Trusted proxy boundary

- `HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS=1`
  - enables proxy identity mode
- `HYBRIDRAG_TRUSTED_PROXY_HOSTS`
  - explicit proxy host allowlist
- `HYBRIDRAG_PROXY_USER_HEADERS`
  - accepted forwarded identity headers
- `HYBRIDRAG_PROXY_IDENTITY_SECRET`
  - shared proxy proof secret
- `HYBRIDRAG_PROXY_IDENTITY_SECRET_PREVIOUS`
  - previous proxy proof secret accepted during rotation

### Admin access boundary

- shared-auth Admin routes now require `actor_role=admin`
- configure that through:
  - `HYBRIDRAG_ROLE_MAP`
  - `HYBRIDRAG_ROLE_TAGS`
- non-admin access attempts against Admin routes are denied and recorded in the security activity feed

### Conversation-history at-rest protection

- `HYBRIDRAG_HISTORY_ENCRYPTION_KEY`
  - primary conversation-history encryption key
- `HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS`
  - previous key accepted during rotation
- the history DB lives beside the configured main DB and is surfaced in Admin runtime safety
- when the key is configured:
  - history rows are encrypted at rest
  - previous-key rows remain readable during rotation
  - store startup opportunistically rewraps old or previous-key rows to the current key
  - SQLite `secure_delete` is enabled on app-managed history connections

## Startup Checklist

Before opening the shared deployment to users:

1. Set `HYBRIDRAG_API_AUTH_TOKEN`.
2. Set `HYBRIDRAG_ROLE_MAP` so the operator account or shared label maps to `admin`.
3. Set `HYBRIDRAG_ROLE_TAGS` so `admin=*`.
4. Set `HYBRIDRAG_BROWSER_SESSION_SECRET`.
5. Set `HYBRIDRAG_HISTORY_ENCRYPTION_KEY` if shared history should be protected at rest.
6. If using a reverse proxy, set the trusted-proxy env vars and proof secret together.
7. Open `/admin/data` and verify:
   - `runtime_safety`
   - `security_activity`
   - `storage_protection`

## Rotation Procedure

### Shared token rotation

1. Put the new token in `HYBRIDRAG_API_AUTH_TOKEN`.
2. Move the old token into `HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS`.
3. Verify `/auth/context` and `/admin/data` still work for expected clients.
4. Remove the previous token after the cutover window closes.

### Browser session rotation

1. Put the new secret in `HYBRIDRAG_BROWSER_SESSION_SECRET`.
2. Move the old secret into `HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS`.
3. If existing sessions must be force-expired, set `HYBRIDRAG_BROWSER_SESSION_INVALID_BEFORE` to the current UNIX timestamp or ISO timestamp.
4. Confirm Admin runtime safety shows session rotation and the invalid-before cutoff.

### Proxy proof rotation

1. Put the new secret in `HYBRIDRAG_PROXY_IDENTITY_SECRET`.
2. Move the old secret into `HYBRIDRAG_PROXY_IDENTITY_SECRET_PREVIOUS`.
3. Confirm the proxy host allowlist is still correct.
4. Review `security_activity` for `proxy_identity_rejected` events during cutover.

### History-key rotation

1. Put the new key in `HYBRIDRAG_HISTORY_ENCRYPTION_KEY`.
2. Move the old key into `HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS`.
3. Restart the server or recreate the history store so rewrap can run.
4. Verify existing threads still open.
5. After the rewrap window, remove the previous key.

## Incident Playbooks

### Shared token exposed

1. Rotate `HYBRIDRAG_API_AUTH_TOKEN` immediately.
2. Keep the old token in `..._PREVIOUS` only long enough for an orderly cutover.
3. Review `security_activity` for:
   - `invalid_login`
   - `unauthorized_request`
   - unusual host spread
4. If browser sessions may also be compromised, rotate browser-session secrets and set `HYBRIDRAG_BROWSER_SESSION_INVALID_BEFORE`.

### Non-admin actor probing Admin routes

1. Open `/admin/data`.
2. Review `security_activity.entries` for `admin_access_denied`.
3. Confirm the actor, host, and path are expected.
4. If unexpected, review:
   - `HYBRIDRAG_ROLE_MAP`
   - proxy identity configuration
   - shared token distribution
5. Rotate shared auth secrets if the actor or host cannot be explained.

### Browser login brute-force or repeated sign-in failures

1. Review `security_activity` for `invalid_login` and `login_rate_limited`.
2. Confirm whether the listed hosts are expected operators.
3. If not expected, rotate the shared token and browser-session secret.
4. Keep the login rate limit enabled; do not widen it until the source is understood.

### History key lost or wrong

1. If the history DB is encrypted and the active key is missing, prior encrypted threads are unreadable.
2. Restore `HYBRIDRAG_HISTORY_ENCRYPTION_KEY` or `..._PREVIOUS` from secure operator records.
3. If neither key is recoverable, treat existing encrypted history as unrecoverable and start a new history DB after archiving the old file.

## Backup And Recovery Notes

### Minimum shared-deployment backup set

- configured main SQLite DB
- conversation-history DB
- relevant `logs/`
- current env/secret inventory stored in the approved secure location

### Recommended recovery sequence

1. Stop active indexing or wait for it to finish.
2. Capture `/admin/data` for the last known-good runtime snapshot.
3. Back up the main DB and the history DB together.
4. Restore the same history key used for the encrypted history file before reopening saved threads.
5. Reopen `/admin/data` and confirm:
   - runtime safety looks correct
   - storage protection is healthy
   - security activity is not accumulating new denied events unexpectedly

## Verification Surfaces

Use these runtime surfaces after any security change:

- `/auth/context`
- `/dashboard/data`
- `/admin/data`

Focus on:

- `runtime_safety`
- `security_activity`
- `storage_protection`
- `alerts`

## Boundaries Still Not Claimed

- The main document index SQLite DB is still protected primarily by OS file permissions, not app-managed encryption.
- The shared deployment remains workstation-hosted, not a hardened multi-node service.
- Whole-system backup/restore drill evidence belongs to Sprint 13.
