# Claude Code settings.json -- Full Specification

**Research date:** 2026-02-21
**Claude Code version context:** v2.1.x (current stable as of Feb 2026)
**Researcher:** Claude Opus 4.6 (automated multi-source sweep)

---

## Table of Contents

1. [Full Documented Schema](#1-full-documented-schema)
2. [Complete List of Valid Tool Permission Names](#2-complete-list-of-valid-tool-permission-names)
3. [Subagent (Task Tool) Settings Inheritance](#3-subagent-task-tool-settings-inheritance)
4. [Settings File Locations and Precedence](#4-settings-file-locations-and-precedence)
5. [Known Issues and Bugs (v2.1.x)](#5-known-issues-and-bugs-v21x)
6. [Verifying Settings Are Loaded Correctly](#6-verifying-settings-are-loaded-correctly)
7. [Eliminating Permission Prompts Entirely](#7-eliminating-permission-prompts-entirely)
8. [allowedTools vs permissions Format](#8-allowedtools-vs-permissions-format)
9. [Environment Variables Reference](#9-environment-variables-reference)
10. [Trail of Bits Security-Hardened Template](#10-trail-of-bits-security-hardened-template)
11. [Hooks System (Permission Extension)](#11-hooks-system-permission-extension)
12. [Sources](#12-sources)

---

## 1. Full Documented Schema

The official JSON Schema is available at `https://json.schemastore.org/claude-code-settings.json`. Add it to your settings file for IDE autocomplete:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json"
}
```

**Note:** Anthropic has NOT published an official schema themselves. The SchemaStore version is community-maintained and may lag behind. Multiple GitHub issues (#11795, #2783, #7438) track this gap.

### Complete Property Reference

| Key | Type | Default | Scope | Description |
|-----|------|---------|-------|-------------|
| `$schema` | string | -- | All | JSON Schema URL for IDE autocomplete/validation |
| `apiKeyHelper` | string | -- | User/Managed | Shell script path executed in `/bin/sh` that outputs auth value (sent as `X-Api-Key` and `Authorization: Bearer` headers) |
| `awsAuthRefresh` | string | -- | User/Managed | Shell script that modifies `.aws` directory (e.g., `"aws sso login --profile myprofile"`) |
| `awsCredentialExport` | string | -- | User/Managed | Shell script outputting JSON with AWS credentials |
| `cleanupPeriodDays` | number | 30 | All | Sessions inactive longer than this are deleted at startup. 0 = immediate deletion |
| `companyAnnouncements` | string[] | -- | Managed | Messages displayed to users at startup (cycled randomly if multiple) |
| `env` | object | -- | All | Key-value pairs of environment variables applied to every session |
| `model` | string | -- | All | Override default model (e.g., `"claude-sonnet-4-6"`) |
| `availableModels` | string[] | -- | Managed | Restrict which models users can select (e.g., `["sonnet", "haiku"]`) |
| `language` | string | -- | All | Preferred response language (e.g., `"japanese"`, `"spanish"`) |
| `outputStyle` | string | -- | All | Output style adjustment (e.g., `"Explanatory"`) |
| `alwaysThinkingEnabled` | boolean | false | All | Enable extended thinking by default for all sessions |
| `showTurnDuration` | boolean | true | All | Show turn duration messages after responses |
| `autoUpdatesChannel` | string | `"latest"` | User | Release channel: `"stable"` (1-week delay, skip regressions) or `"latest"` |
| `cleanupPeriodDays` | number | 30 | All | Session history retention in days |
| `forceLoginMethod` | string | -- | Managed | Restrict login to `"claudeai"` or `"console"` |
| `forceLoginOrgUUID` | string | -- | Managed | UUID of organization to auto-select during login |
| `respectGitignore` | boolean | true | All | Whether `@` file picker respects `.gitignore` patterns |
| `plansDirectory` | string | `"~/.claude/plans"` | All | Directory for plan files |
| `prefersReducedMotion` | boolean | false | User | Reduce/disable UI animations (spinners, shimmer, flash) |
| `terminalProgressBarEnabled` | boolean | true | User | Enable terminal progress bar in supported terminals |
| `teammateMode` | string | `"auto"` | All | Agent team display: `"auto"`, `"in-process"`, or `"tmux"` |

### Attribution Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `attribution.commit` | string | (includes Co-Authored-By trailer) | Git commit attribution. Empty string `""` hides it |
| `attribution.pr` | string | (includes Generated with Claude Code link) | Pull request attribution. Empty string `""` hides it |
| `includeCoAuthoredBy` | boolean | true | **DEPRECATED** -- Use `attribution` object instead |

### Permissions Object

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `permissions.allow` | string[] | `[]` | Permission rules to auto-allow tool use |
| `permissions.ask` | string[] | `[]` | Permission rules that prompt for confirmation |
| `permissions.deny` | string[] | `[]` | Permission rules that block tool use (highest priority) |
| `permissions.additionalDirectories` | string[] | `[]` | Extra working directories Claude can access |
| `permissions.defaultMode` | string | `"default"` | Permission mode: `"default"`, `"acceptEdits"`, `"plan"`, `"dontAsk"`, `"bypassPermissions"` |
| `permissions.disableBypassPermissionsMode` | string | -- | Set to `"disable"` to prevent bypass mode activation |

### Sandbox Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sandbox.enabled` | boolean | false | Enable bash sandboxing (macOS, Linux, WSL2) |
| `sandbox.autoAllowBashIfSandboxed` | boolean | true | Auto-approve bash when sandboxed |
| `sandbox.excludedCommands` | string[] | `[]` | Commands that bypass the sandbox |
| `sandbox.allowUnsandboxedCommands` | boolean | true | Allow `dangerouslyDisableSandbox` parameter |
| `sandbox.enableWeakerNestedSandbox` | boolean | false | Weaker sandbox for unprivileged Docker (Linux/WSL2 only) |
| `sandbox.network.allowUnixSockets` | string[] | `[]` | Unix socket paths accessible in sandbox |
| `sandbox.network.allowAllUnixSockets` | boolean | false | Allow all Unix socket connections |
| `sandbox.network.allowLocalBinding` | boolean | false | Allow localhost port binding (macOS only) |
| `sandbox.network.allowedDomains` | string[] | `[]` | Domains allowed for outbound traffic (supports wildcards) |
| `sandbox.network.httpProxyPort` | number | -- | HTTP proxy port |
| `sandbox.network.socksProxyPort` | number | -- | SOCKS5 proxy port |
| `sandbox.ignoreViolations` | object | -- | Maps command patterns to filesystem paths to ignore violations |

### MCP Server Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enableAllProjectMcpServers` | boolean | false | Auto-approve all MCP servers in project `.mcp.json` |
| `enabledMcpjsonServers` | string[] | -- | Specific MCP servers from `.mcp.json` to approve |
| `disabledMcpjsonServers` | string[] | -- | Specific MCP servers from `.mcp.json` to reject |
| `allowedMcpServers` | object[] | -- | **(Managed only)** Allowlist of MCP servers |
| `deniedMcpServers` | object[] | -- | **(Managed only)** Denylist of MCP servers |

### Hooks Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `hooks` | object | -- | Custom commands at lifecycle events (see Section 11) |
| `disableAllHooks` | boolean | false | Disable all hooks and custom status line |
| `allowManagedHooksOnly` | boolean | false | **(Managed only)** Only allow managed/SDK hooks |

### Plugin Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabledPlugins` | object | -- | Plugin enable/disable map: `{"name@marketplace": true/false}` |
| `extraKnownMarketplaces` | object | -- | Additional marketplace sources |
| `strictKnownMarketplaces` | object[] | -- | **(Managed only)** Restrict plugin marketplace sources |

### UI/UX Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `statusLine` | object | -- | Custom status line: `{"type": "command", "command": "~/.claude/statusline.sh"}` |
| `fileSuggestion.type` | string | -- | File suggestion type: `"command"` |
| `fileSuggestion.command` | string | -- | Script for `@` file autocomplete (receives JSON stdin with `query` field) |
| `spinnerTipsEnabled` | boolean | true | Show tips in spinner while Claude works |
| `spinnerTipsOverride.excludeDefault` | boolean | false | If true, show only custom tips |
| `spinnerTipsOverride.tips` | string[] | -- | Custom tip strings |
| `spinnerVerbs.mode` | string | -- | `"replace"` (custom only) or `"append"` (add to defaults) |
| `spinnerVerbs.verbs` | string[] | -- | Custom action verbs for spinner |

### [NOVEL FIND] Undocumented/Semi-Documented Properties

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `skipDangerousModePermissionPrompt` | boolean | false | Auto-written when user accepts bypass mode warning. Suppresses the one-time safety warning on subsequent launches. **Not documented** in official settings reference. Removing it re-shows the warning. (GitHub Issue #26233, filed 2026-02-16) |
| `otelHeadersHelper` | string | -- | Script to generate dynamic OpenTelemetry headers. Mentioned in official docs but not widely documented |
| `allowManagedPermissionRulesOnly` | boolean | false | **(Managed only)** Blocks ALL user/project permission rules |

---

## 2. Complete List of Valid Tool Permission Names

These are the exact string values accepted in `permissions.allow`, `permissions.deny`, and `permissions.ask` arrays.

### Built-in Tools (Core)

| Tool Name | Category | Requires Permission | Supports Specifier Pattern |
|-----------|----------|--------------------|----|
| `Bash` | Execute | Yes | `Bash(command pattern)` |
| `Read` | Read-only | No (by default) | `Read(filepath pattern)` |
| `Write` | Modify | Yes | `Write(filepath pattern)` |
| `Edit` | Modify | Yes | `Edit(filepath pattern)` |
| `MultiEdit` | Modify | Yes | `Edit(filepath pattern)` (inherits from Edit) |
| `Glob` | Read-only | No | -- |
| `Grep` | Read-only | No | -- |
| `LS` | Read-only | No | -- |
| `Task` | Sub-agent | No | `Task(AgentName)` |
| `WebFetch` | Network | Yes | `WebFetch(domain:hostname)` |
| `WebSearch` | Network | Yes | -- (no specifier) |
| `NotebookRead` | Read-only | No | -- |
| `NotebookEdit` | Modify | Yes | -- |
| `TodoRead` | Read-only | No | -- |
| `TodoWrite` | Utility | No | -- |
| `Skill` | Execute | Yes | -- |

### Built-in Tools (Internal/Advanced)

| Tool Name | Description |
|-----------|-------------|
| `BashOutput` | Get output from running bash process |
| `KillShell` | Kill a running shell process |
| `ExitPlanMode` | Exit plan mode |
| `EnterPlanMode` | Enter plan mode |
| `SlashCommand` | Execute slash commands |
| `AgentOutputTool` | Agent output handling |

### MCP Tools (Dynamic)

MCP tools follow the naming convention `mcp__<server-name>__<tool-name>`:

| Pattern | Effect |
|---------|--------|
| `mcp__puppeteer` | All tools from the puppeteer server |
| `mcp__puppeteer__*` | Wildcard: all tools from puppeteer server |
| `mcp__puppeteer__puppeteer_navigate` | Specific tool from puppeteer server |
| `mcp__plugin_<plugin>_<server>__<tool>` | Plugin-provided MCP tool |

**[NOVEL FIND]** One community source warns that `mcp__github__*` wildcard syntax may NOT work in settings.json permission arrays. The safer approach is `mcp__github` (without wildcard) to approve all tools from a server. However, the official docs do show wildcard syntax as valid.

### Specifier Pattern Syntax

| Tool | Pattern | Example | Matches |
|------|---------|---------|---------|
| Bash | `Bash(command *)` | `Bash(git *)` | Any command starting with "git " |
| Bash | `Bash(* flag)` | `Bash(* --version)` | Any command ending with " --version" |
| Bash | `Bash(cmd * middle *)` | `Bash(git * main)` | e.g., `git checkout main` |
| Read/Edit | Absolute path | `Read(//Users/alice/secrets/**)` | Absolute filesystem path (double `/`) |
| Read/Edit | Home-relative | `Read(~/Documents/*.pdf)` | Relative to user home |
| Read/Edit | Settings-relative | `Edit(/src/**/*.ts)` | Relative to settings file location |
| Read/Edit | CWD-relative | `Read(*.env)` or `Read(./*.env)` | Relative to current directory |
| WebFetch | Domain filter | `WebFetch(domain:example.com)` | Requests to that domain |
| Task | Agent name | `Task(Explore)` | Specific subagent |

**Critical notes on Bash patterns:**
- The space before `*` matters: `Bash(ls *)` matches `ls -la` but NOT `lsof`; `Bash(ls*)` matches both
- Shell operators (`&&`, `||`, `;`, `|`, `>`, `$()`, backticks) break wildcard matching and trigger explicit approval
- The legacy `:*` suffix syntax (e.g., `Bash(git log:*)`) is **deprecated** -- use `Bash(git log *)` instead
- `Bash(*)` is equivalent to bare `Bash` and matches all commands

**Critical notes on Read/Edit patterns:**
- `*` matches files in a single directory; `**` matches recursively across directories
- `/path` is NOT an absolute path -- it is relative to the settings file. Use `//path` for true absolute paths
- Patterns follow gitignore specification

---

## 3. Subagent (Task Tool) Settings Inheritance

### How It Should Work (per documentation)

Each subagent runs in its own context window with a custom system prompt, specific tool access, and independent permissions. Subagents inherit the permission context from the main conversation but can override the mode via `permissionMode`.

### How It Actually Works (bugs and all)

**There are at least 5 open GitHub issues documenting broken subagent permission inheritance:**

1. **Issue #10906** -- Built-in Plan agent ignores parent `settings.json` permissions and repeatedly prompts for pre-approved tools.

2. **Issue #18950** -- Skills/subagents do NOT inherit user-level permissions from `~/.claude/settings.json`. All bash commands require permission prompts within a skill, even though the same commands are auto-approved in the main conversation.

3. **Issue #5465** -- Task subagents fail to inherit permissions in MCP server mode (both WSL and native Windows). Permission prompts appear that cannot be answered through the MCP interface.

4. **Issue #25526** -- Subagents cannot use Bash despite parent `Bash(*)` allow rule. This means subagents become write-only and cannot self-verify their work (run tests, lint).

5. **[NOVEL FIND] Issue #25000** -- Sub-agents BYPASS permission deny rules and per-command approval. This is a **security risk**: if Bash is denied in `settings.local.json`, sub-agents should also be denied, but they are not.

### bypassPermissions and Subagents

**[NOVEL FIND]** When the parent agent uses `bypassPermissions` mode, ALL subagents unconditionally inherit this mode and it CANNOT be overridden (Issue #20264). This is a privilege escalation risk -- third-party subagents, plugins, or skills that spawn subagents automatically gain bypass privileges without explicit user consent.

### Directory Traversal for Subagent Config

**Issue #26489** documents that skills, agents, and commands directories do NOT traverse parent directories the way `CLAUDE.md` does. A Claude Code session opened at `/src/my-app` picks up `/src/.claude/CLAUDE.md` and `/src/.claude/settings.json` correctly, but looks for skills only in `/src/my-app/.claude/skills/` (which may not exist), falling back to `~/.claude/skills/` (global). Intermediate directories are skipped.

### Built-in Subagent Tool Access

Different built-in subagents have different tool access restrictions:

| Agent | Available Tools |
|-------|----------------|
| general-purpose | ALL tools |
| Explore | Glob, Grep, Read, Bash |
| statusline-setup | Read, Edit |
| output-style-setup | Read, Write, Edit, Glob, Grep |

---

## 4. Settings File Locations and Precedence

### File Locations

| Scope | File Path | Shared with Team | Who It Affects |
|-------|-----------|-----------------|----------------|
| **Managed** (macOS) | `/Library/Application Support/ClaudeCode/managed-settings.json` | IT-deployed | All users on machine |
| **Managed** (Linux/WSL) | `/etc/claude-code/managed-settings.json` | IT-deployed | All users on machine |
| **Managed** (Windows) | `C:\Program Files\ClaudeCode\managed-settings.json` | IT-deployed | All users on machine |
| **User (global)** | `~/.claude/settings.json` | No | You, all projects |
| **Project (shared)** | `.claude/settings.json` | Yes (git) | All collaborators |
| **Project (local)** | `.claude/settings.local.json` | No (gitignored) | You, this repo only |
| **Legacy** | `~/.claude.json` | No | You, all projects |

**[NOVEL FIND]** The Windows managed settings path was changed in v2.1.2 from `C:\ProgramData\ClaudeCode\` to `C:\Program Files\ClaudeCode\` for better integration with system-wide installations.

### Precedence Order (Highest to Lowest)

1. **Managed settings** (`managed-settings.json` or server-managed) -- Cannot be overridden by any lower level
2. **Command line arguments** -- Session-only overrides (e.g., `--permission-mode`, `--allowedTools`)
3. **Project local settings** (`.claude/settings.local.json`) -- Personal project overrides, auto-gitignored
4. **Project shared settings** (`.claude/settings.json`) -- Team-wide, version controlled
5. **User/global settings** (`~/.claude/settings.json`) -- Personal defaults across all projects
6. **Legacy settings** (`~/.claude.json`) -- Lowest priority, fully supported

### How Merging Works

Settings don't simply replace each other -- they **merge**:

- If user settings allow `Bash(git status)` and project settings allow `Bash(npm run lint)`, **both** rules apply
- Permission arrays (`allow`, `deny`, `ask`) are concatenated across levels
- If the same key has different values at different scopes, the higher-priority scope wins for that specific key
- **Deny always wins** over allow at the same level: rules are evaluated deny -> ask -> allow, first match wins

### [NOVEL FIND] Known Merge Bug

**Issue #19487** -- Project `settings.local.json` OVERWRITES global settings instead of deep merging. When a project-level `.claude/settings.local.json` exists, it completely replaces the global `~/.claude/settings.local.json` rather than performing a deep merge. This causes global settings (like `statusLine`) to be ignored even when they are not defined in the project file.

**Issue #17017** -- Project-level permissions replace global permissions instead of merging. Same root cause.

### Other Configuration Files

| Feature | User | Project | Local |
|---------|------|---------|-------|
| Settings | `~/.claude/settings.json` | `.claude/settings.json` | `.claude/settings.local.json` |
| Subagents | `~/.claude/agents/` | `.claude/agents/` | -- |
| MCP servers | `~/.claude.json` | `.mcp.json` | -- |
| Memory (CLAUDE.md) | `~/.claude/CLAUDE.md` | `CLAUDE.md` or `.claude/CLAUDE.md` | `CLAUDE.local.md` |
| Skills | `~/.claude/skills/` | `.claude/skills/` | -- |
| Commands (deprecated) | `~/.claude/commands/` | `.claude/commands/` | -- |
| Plans | `~/.claude/plans/` | -- | -- |

---

## 5. Known Issues and Bugs (v2.1.x)

### Permission System Bugs

| Issue | Description | Status |
|-------|-------------|--------|
| **#27139** | Broad wildcard permissions in `settings.local.json` not respected. `Edit` in allow list still prompts "Allow Claude to Edit formatter.rs?" | Open (2026-02-17) |
| **#18160** | Global `settings.json` allow permissions ignored. `Bash(ls *)` does not match `ls -la ~/.claude/` | Open |
| **#16735** | "Yes, and don't ask again" option doesn't persist to `settings.json`. The `permissions.allow` array remains empty | Open |
| **#15921** | VSCode Extension: `settings.local.json` permissions NOT respected for Bash/Write/Edit. Only Read-type tools (Read, Glob, Grep) work. Even `bypassPermissions` mode still prompts | Open |
| **#13340** | Global/local `settings.json` allow permissions are not respected by Claude Code | Open |
| **#25909** | "Always allow" on multiline bash commands creates invalid permission patterns that corrupt settings | Fixed (recent) |

### Merge/Precedence Bugs

| Issue | Description | Status |
|-------|-------------|--------|
| **#19487** | Project `settings.local.json` overwrites global settings instead of deep merging | Open |
| **#17017** | Project-level permissions replace global permissions instead of merging | Open |

### Subagent Bugs

| Issue | Description | Status |
|-------|-------------|--------|
| **#10906** | Plan agent ignores parent `settings.json` permissions | Open |
| **#18950** | Skills/subagents don't inherit user-level permissions | Open |
| **#25526** | Subagents cannot use Bash despite parent `Bash(*)` allow rule | Open |
| **#25000** | Sub-agents bypass permission deny rules (security risk) | Open |
| **#5465** | Task subagents fail to inherit permissions in MCP server mode | Open |

### Documentation Gaps

| Issue | Description | Status |
|-------|-------------|--------|
| **#26233** | `skipDangerousModePermissionPrompt` missing from settings reference | Open (2026-02-16) |
| **#11795** | No official JSON Schema linked from documentation | Open |
| **#7438** | SchemaStore JSON schema out of sync with actual settings | Open |
| **#6544** | Not all environment variables documented on settings page | Open |

### Security Issues

| Issue | Description | Status |
|-------|-------------|--------|
| **#2720** | Permissions configuration bypass in local settings enforcement | Reported June 2025 |
| **#20493** | Security page missing warning about `bypassPermissions` + `allowUnsandboxedCommands` defeating sandbox | Open |
| **#13106** | Sensitive tokens stored in `settings.local.json` not gitignored by default (credential leak risk) | Open |
| **#10230** | Claude Code creates `~/.config/git/ignore` without user permission (modifies global git config) | Open |

### Other Platform Issues

| Issue | Description |
|-------|-------------|
| **#25503** | `--dangerously-skip-permissions` flag should bypass permission mode dialog without requiring persisted `skipDangerousModePermissionPrompt` setting |
| **#12604** | VSCode Extension: `allow: [*]` and `defaultMode: bypassPermissions` not working |
| **#26074** | `alwaysThinkingEnabled: true` not enabling thinking mode on Bedrock and Vertex providers |

---

## 6. Verifying Settings Are Loaded Correctly

### Primary Methods

```bash
# View all active settings for current project
claude config list

# View global settings only
claude config list --global

# Enable verbose/debug output
claude --verbose --debug

# Debug MCP servers specifically
claude --mcp-debug

# Health check
claude /doctor

# Check current permissions interactively
# (inside a Claude Code session)
/permissions

# Check system status
/status
```

### Setting Config Values via CLI

```bash
# Set a global config key
claude config set --global apiKeyHelper ~/.claude/key_helper.sh

# Set project-level config
claude config set timeout 30

# Reset all configuration
claude config reset

# Clear cache
claude --clear-cache
```

### [NOVEL FIND] IDE Schema Validation

The VSCode extension includes an internal schema reference (`.claude-code-settings.schema.json`) that automatically validates:
- `**/.claude/settings.json`
- `**/.claude/settings.local.json`
- `**/ClaudeCode/managed-settings.json`
- `**/claude-code/managed-settings.json`

You can also manually add schema validation in `.vscode/settings.json`:

```json
{
  "json.schemas": [
    {
      "url": "https://json.schemastore.org/claude-code-settings.json",
      "fileMatch": [
        "**/.claude/settings.json",
        "**/.claude/settings.local.json"
      ]
    }
  ]
}
```

### Verifying Environment Variables

If you set `ANTHROPIC_MODEL` both as a shell export AND inside `settings.json`'s `env` object, the shell environment variable takes precedence. The `env` object in settings applies at Claude Code startup, but pre-existing shell variables are not overwritten.

---

## 7. Eliminating Permission Prompts Entirely

There are multiple approaches, from most targeted to most aggressive:

### Approach 1: Granular Allow Rules (Recommended)

Add specific tool patterns to `permissions.allow` in your settings file:

```json
{
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(npm run *)",
      "Bash(python *)",
      "Edit",
      "Write",
      "MultiEdit",
      "WebFetch",
      "WebSearch",
      "NotebookEdit"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(sudo *)",
      "Read(./.env)",
      "Read(./.env.*)"
    ]
  }
}
```

### Approach 2: CLAUDE.md Permissions Section

Add a permissions section to your CLAUDE.md file:

```markdown
# Permissions
You have full permission to read, write, edit, create, and delete files.
You may run any bash, python, git commands without asking for confirmation.
```

**Important:** CLAUDE.md is instruction-level, NOT enforcement-level. It tells Claude it CAN do things, but does not bypass the tool permission system. Claude will still be prompted for tools not in the `allow` list. CLAUDE.md is useful for reducing unnecessary "should I?" questions, not for bypassing the security layer.

### Approach 3: Accept Edits Mode

```json
{
  "permissions": {
    "defaultMode": "acceptEdits"
  }
}
```

Automatically accepts file edit permissions for the session. Bash commands still require approval.

### Approach 4: Don't Ask Mode

```json
{
  "permissions": {
    "defaultMode": "dontAsk"
  }
}
```

Auto-denies tools unless pre-approved via `/permissions` or `permissions.allow` rules. The opposite of bypass -- it is more restrictive, not less.

### Approach 5: CLI Flag (Per-Session)

```bash
# Allow specific tools for one session
claude --allowedTools Edit Write "Bash(git *)"

# Full bypass for one session
claude --dangerously-skip-permissions "Fix all lint errors"

# Equivalent to above
claude --permission-mode bypassPermissions "Fix all lint errors"

# Non-interactive mode with bypass (for CI/CD)
claude -p "Generate boilerplate" --dangerously-skip-permissions --output-format stream-json
```

### Approach 6: Bypass Permissions Mode (YOLO Mode)

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions"
  }
}
```

Skips ALL permission prompts. Only for isolated environments (containers, VMs). First launch shows a one-time warning dialog; accepting it writes `skipDangerousModePermissionPrompt: true` to user settings.

**To suppress the warning dialog permanently:**

```json
{
  "skipDangerousModePermissionPrompt": true,
  "permissions": {
    "defaultMode": "bypassPermissions"
  }
}
```

### Approach 7: Permission Hooks (Recommended for Production)

Starting with Claude Code v2.0, hooks are the recommended approach for auto-approval control instead of `--dangerously-skip-permissions`. Hooks provide deterministic, programmatic control:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 validate_command.py \"$TOOL_INPUT\"",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

Exit code 0 = approve, exit code 2 = block. Hooks can also return JSON with `{"decision": "approve"}` or `{"decision": "block", "reason": "..."}`.

### [NOVEL FIND] Approach 8: Sandbox + Bypass (Trail of Bits Method)

Trail of Bits recommends running with `--dangerously-skip-permissions` BUT with sandboxing enabled and hooks blocking destructive operations. Their reasoning: permission prompts provide minimal security against prompt injection attacks, while programmatic controls (hooks + sandbox) are more reliable at scale.

### [NOVEL FIND] Unofficial Environment Variables (Do NOT Rely On)

Some users have tried environment variables like `CLAUDE_CODE_BYPASS_ALL_PERMISSIONS=1`, `CLAUDE_CODE_SUPPRESS_UI_PROMPTS=1`, and `ANTHROPIC_DISABLE_SAFETY_CHECKS=1`. These are **NOT officially supported** and do not reliably bypass permissions. The `--dangerously-skip-permissions` flag is the only supported mechanism.

### Approach 9: --disallowedTools for Partial Restrictions in YOLO Mode

```bash
claude --dangerously-skip-permissions --disallowedTools "Bash(rm *)" "Write(.env)"
```

`--disallowedTools` works correctly in bypass mode to exclude specific tools. Note: `--allowedTools` may be ignored in bypass mode (documented bug).

---

## 8. allowedTools vs permissions Format

### The Two Formats

Claude Code has two configuration formats for tool permissions, reflecting the evolution of the product:

#### Legacy Format: `allowedTools` (top-level array)

```json
{
  "allowedTools": [
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash(git *)",
    "Bash(npm run *)",
    "Glob",
    "Grep",
    "LS",
    "Task",
    "WebFetch",
    "WebSearch"
  ]
}
```

Found in `~/.claude.json` and older configurations. This format is **still fully supported** and sometimes provides more consistent behavior, particularly for MCP server configurations.

#### Current Format: `permissions` object with `allow`/`deny`/`ask`

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Bash(git *)"
    ],
    "deny": [
      "Read(./.env)",
      "Bash(curl *)"
    ],
    "ask": [
      "Bash(npm *)"
    ]
  }
}
```

Found in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, and `managed-settings.json`. This is the **recommended modern format** and the only format that supports `deny` and `ask` rules.

### What Is Deprecated

| Feature | Status | Replacement |
|---------|--------|-------------|
| `:*` suffix syntax | **Deprecated** | Use ` *` (space-asterisk) instead |
| `allowedTools` top-level array | **Supported but legacy** | Use `permissions.allow` array |
| `~/.claude.json` file | **Supported but legacy** | Use `~/.claude/settings.json` |
| `includeCoAuthoredBy` | **Deprecated** | Use `attribution.commit` and `attribution.pr` |

### Recommendation

Use the `permissions` object format in `~/.claude/settings.json` for new configurations. Keep `~/.claude.json` as a fallback if you experience inconsistencies with the newer format, particularly for MCP configurations.

### Rule Evaluation Order

Within any single settings file:
1. **Deny** rules checked first -- if matched, tool use is blocked
2. **Ask** rules checked second -- if matched, user is prompted
3. **Allow** rules checked last -- if matched, tool use proceeds silently
4. If no rule matches, default behavior applies (depends on `defaultMode`)

Content-level rules override tool-level rules. For example: `allow: ["Bash"], ask: ["Bash(rm *)"]` means Bash is generally allowed, but `rm` commands require confirmation.

---

## 9. Environment Variables Reference

These can be set in your shell profile or in the `env` field of `settings.json`.

### Authentication & API

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for authentication |
| `ANTHROPIC_BASE_URL` | Custom API endpoint (for gateways/proxies) |
| `ANTHROPIC_AUTH_TOKEN` | Authorization token for custom endpoints |
| `ANTHROPIC_CUSTOM_HEADERS` | Extra HTTP headers for API requests |
| `ANTHROPIC_BEDROCK_BASE_URL` | AWS Bedrock-specific gateway URL |
| `ANTHROPIC_VERTEX_BASE_URL` | Google Vertex-specific gateway URL |
| `ANTHROPIC_VERTEX_PROJECT_ID` | GCP project ID for Vertex AI |
| `ANTHROPIC_LOG` | Debug logging level (e.g., `debug`) |

### Model Selection

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_MODEL` | Override the default model |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Controls the "sonnet" model alias |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Controls the "opus" and "opusplan" model aliases |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Controls the "haiku" model alias (replaces deprecated `ANTHROPIC_SMALL_FAST_MODEL`) |
| `CLAUDE_CODE_EFFORT_LEVEL` | Reasoning depth: `low`, `medium`, `high` (default) |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output token limit (e.g., 8192) |
| `MAX_THINKING_TOKENS` | Max thinking tokens (e.g., 31999) |

### Feature Flags

| Variable | Description |
|----------|-------------|
| `DISABLE_TELEMETRY` | Disable telemetry (`1` to disable) |
| `DISABLE_ERROR_REPORTING` | Disable Sentry error reporting |
| `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY` | Disable feedback surveys |
| `CLAUDE_CODE_ENABLE_TELEMETRY` | Enable OpenTelemetry (overrides DISABLE_TELEMETRY) |
| `DISABLE_NON_ESSENTIAL_MODEL_CALLS` | Reduce unnecessary model calls |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` | Disable experimental beta features |
| `DISABLE_INTERLEAVED_THINKING` | Opt-out of interleaved thinking UI |
| `DISABLE_PROMPT_CACHING` | Disable prompt caching (Bedrock/Vertex) |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Enable experimental agent teams feature |
| `ENABLE_LSP_TOOL` | Enable Language Server Protocol tool (`1` to enable) |

### Network & Proxy

| Variable | Description |
|----------|-------------|
| `HTTPS_PROXY` | HTTPS proxy URL for corporate networks |
| `HTTP_PROXY` | HTTP proxy URL |

### Platform

| Variable | Description |
|----------|-------------|
| `AWS_REGION` | AWS region for Bedrock |
| `CLOUD_ML_REGION` | GCP region for Vertex AI |
| `CLAUDE_CODE_USE_BEDROCK` | Connect to AWS Bedrock |
| `CLAUDE_CODE_AUTO_CONNECT_IDE` | Disable automatic IDE connection |
| `CLAUDE_CODE_SHELL_PREFIX` | Wrap shell commands |
| `CLAUDE_CODE_GIT_BASH_PATH` | Git Bash path (Windows-specific) |

### [NOVEL FIND] Undocumented/Partially Documented Variables

Many environment variables are undocumented. GitHub Issue #6544 requests a full audit. The `env` section of `settings.json` is the recommended place to set these persistently rather than in shell profiles.

---

## 10. Trail of Bits Security-Hardened Template

Trail of Bits (security auditing firm) published an open-source opinionated `settings.json` at [trailofbits/claude-code-config](https://github.com/trailofbits/claude-code-config). Key design decisions:

### Their `settings.json` Template

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "cleanupPeriodDays": 365,
  "env": {
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "enableAllProjectMcpServers": false,
  "alwaysThinkingEnabled": true,
  "permissions": {
    "deny": [
      "Bash(rm -rf *)", "Bash(rm -fr *)", "Bash(sudo *)",
      "Bash(mkfs *)", "Bash(dd *)",
      "Bash(curl *|bash*)", "Bash(wget *|bash*)",
      "Bash(git push --force*)", "Bash(git push *--force*)",
      "Bash(git reset --hard*)",
      "Edit(~/.bashrc)", "Edit(~/.zshrc)",
      "Edit(~/.ssh/**)", "Read(~/.ssh/**)",
      "Read(~/.gnupg/**)", "Read(~/.aws/**)",
      "Read(~/.azure/**)", "Read(~/.config/gh/**)",
      "Read(~/.git-credentials)", "Read(~/.docker/config.json)",
      "Read(~/.kube/**)", "Read(~/.npmrc)",
      "Read(~/.npm/**)", "Read(~/.pypirc)",
      "Read(~/.gem/credentials)",
      "Read(~/Library/Keychains/**)",
      "Read(~/Library/Application Support/**/metamask*/**)",
      "Read(~/Library/Application Support/**/electrum*/**)",
      "Read(~/Library/Application Support/**/exodus*/**)",
      "Read(~/Library/Application Support/**/phantom*/**)",
      "Read(~/Library/Application Support/**/solflare*/**)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "CMD=$(jq -r '.tool_input.command'); if echo \"$CMD\" | grep -qE 'rm[[:space:]]+-[^[:space:]]*r[^[:space:]]*f'; then echo 'BLOCKED: Use trash instead of rm -rf' >&2; exit 2; fi"
          },
          {
            "type": "command",
            "command": "CMD=$(jq -r '.tool_input.command'); if echo \"$CMD\" | grep -qE 'git[[:space:]]+push.*(main|master)'; then echo 'BLOCKED: Use feature branches, not direct push to main' >&2; exit 2; fi"
          }
        ]
      }
    ]
  },
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.sh"
  }
}
```

### [NOVEL FIND] Key Design Insight from Trail of Bits

Trail of Bits operates in `--dangerously-skip-permissions` mode ("claude-yolo") as their **recommended production mode**. Their reasoning:

1. Permission prompts provide minimal security against prompt injection attacks
2. Hooks provide better, deterministic control than prompts
3. Sandbox provides OS-level enforcement that prompts cannot
4. Without sandbox, bypass mode exposes your system to unrestricted access
5. With sandbox + hooks, bypass mode is MORE secure than manual prompt approval (humans get fatigued and approve everything anyway)

For full isolation, they recommend running in a devcontainer where the agent has no access to host filesystem, SSH keys, cloud credentials, or anything outside the container.

---

## 11. Hooks System (Permission Extension)

Hooks run code at specific points in Claude Code's lifecycle. They provide **deterministic** control (guaranteed to execute, unlike prompt-based rules in CLAUDE.md).

### Available Hook Events

| Event | When It Fires |
|-------|--------------|
| `PreToolUse` | Before Claude executes a tool action |
| `PostToolUse` | After Claude executes a tool action |
| `PostToolUseFailure` | On tool errors |
| `PermissionRequest` | When user would see a permission dialog |
| `SessionStart` | At session start |
| `SessionEnd` | At session end |
| `Stop` | When the agent finishes |
| `SubagentStart` | When a sub-agent spawns |
| `SubagentStop` | When a sub-agent finishes |
| `UserPromptSubmit` | When user submits a prompt |
| `PreCompact` | Before conversation compaction |
| `Notification` | On system notifications |
| `TeammateIdle` | When a teammate agent is idle |
| `TaskCompleted` | When a task completes |
| `Setup` | During setup |

### Hook Handler Types

1. **Command hooks** -- Run shell commands as child processes. Receive JSON on stdin with session ID, transcript path, working directory, tool name, and input parameters.

2. **Prompt hooks** -- Send a text prompt to a fast Claude model (Haiku by default) for single-turn semantic evaluation. Use `$ARGUMENTS` placeholder for input JSON.

3. **Agent hooks** -- Spawn a sub-agent with access to tools (Read, Grep, Glob) for multi-turn codebase verification. Heaviest handler type.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success -- action proceeds |
| 2 | Blocking error -- action is PREVENTED, stderr becomes error message |
| Other | Non-blocking error, stderr shown in verbose mode |

### JSON Decision Control

Hooks can return structured JSON for fine-grained control:

```json
{
  "decision": "approve",
  "reason": "Command is safe",
  "continue": true,
  "updatedInput": { "command": "modified command" }
}
```

Valid `decision` values: `approve`, `block`, `allow`, `deny`.

### [NOVEL FIND] Input Modification (v2.0.10+)

PreToolUse hooks can modify tool inputs before execution. Instead of blocking and forcing retries, hooks intercept, modify the JSON input, and let execution proceed with corrected parameters. This enables transparent sandboxing, automatic security enforcement, and team convention adherence.

---

## 12. Sources

### Official Documentation
- [Claude Code Settings Reference](https://code.claude.com/docs/en/settings) -- Primary settings documentation
- [Configure Permissions](https://code.claude.com/docs/en/permissions) -- Permission system documentation
- [Model Configuration](https://code.claude.com/docs/en/model-config) -- Model and environment variable docs
- [Hooks Guide](https://code.claude.com/docs/en/hooks-guide) -- Official hooks documentation
- [Subagents Documentation](https://code.claude.com/docs/en/sub-agents) -- Subagent configuration

### GitHub Issues (anthropics/claude-code)
- [#26233](https://github.com/anthropics/claude-code/issues/26233) -- `skipDangerousModePermissionPrompt` missing from docs
- [#11795](https://github.com/anthropics/claude-code/issues/11795) -- Request for official JSON Schema link
- [#7438](https://github.com/anthropics/claude-code/issues/7438) -- SchemaStore schema out of sync
- [#2783](https://github.com/anthropics/claude-code/issues/2783) -- Request for TypeScript types or JSON Schema
- [#10906](https://github.com/anthropics/claude-code/issues/10906) -- Plan agent ignores parent permissions
- [#18950](https://github.com/anthropics/claude-code/issues/18950) -- Skills/subagents don't inherit user-level permissions
- [#5465](https://github.com/anthropics/claude-code/issues/5465) -- Task subagents fail in MCP server mode
- [#25526](https://github.com/anthropics/claude-code/issues/25526) -- Subagents can't use Bash despite parent allow rule
- [#25000](https://github.com/anthropics/claude-code/issues/25000) -- Sub-agents bypass deny rules (security risk)
- [#20264](https://github.com/anthropics/claude-code/issues/20264) -- bypassPermissions unconditionally inherited by subagents
- [#26489](https://github.com/anthropics/claude-code/issues/26489) -- Skills/agents don't traverse parent directories
- [#27139](https://github.com/anthropics/claude-code/issues/27139) -- Wildcard permissions not respected
- [#18160](https://github.com/anthropics/claude-code/issues/18160) -- Global allow permissions ignored
- [#16735](https://github.com/anthropics/claude-code/issues/16735) -- "Don't ask again" doesn't persist
- [#15921](https://github.com/anthropics/claude-code/issues/15921) -- VSCode extension ignores settings.local.json
- [#19487](https://github.com/anthropics/claude-code/issues/19487) -- Local settings overwrite global instead of merging
- [#17017](https://github.com/anthropics/claude-code/issues/17017) -- Project permissions replace global instead of merging
- [#25503](https://github.com/anthropics/claude-code/issues/25503) -- --dangerously-skip-permissions should bypass dialog
- [#12604](https://github.com/anthropics/claude-code/issues/12604) -- VSCode extension bypass mode not working
- [#13106](https://github.com/anthropics/claude-code/issues/13106) -- Sensitive tokens in settings.local.json not gitignored
- [#10230](https://github.com/anthropics/claude-code/issues/10230) -- Claude creates ~/.config/git/ignore without permission
- [#2720](https://github.com/anthropics/claude-code/issues/2720) -- Permissions configuration bypass
- [#20493](https://github.com/anthropics/claude-code/issues/20493) -- Missing warning about bypass + unsandboxed defeating sandbox
- [#6544](https://github.com/anthropics/claude-code/issues/6544) -- Not all environment variables documented
- [#25909](https://github.com/anthropics/claude-code/issues/25909) -- Multiline bash creates invalid permission patterns
- [#26074](https://github.com/anthropics/claude-code/issues/26074) -- alwaysThinkingEnabled not working on Bedrock/Vertex
- [#1202](https://github.com/anthropics/claude-code/issues/1202) -- Documentation error on settings.json location
- [#889](https://github.com/anthropics/claude-code/issues/889) -- Request for global allowedTools specification
- [#1498](https://github.com/anthropics/claude-code/issues/1498) -- --dangerously-skip-permissions still asks for permissions
- [#5886](https://github.com/anthropics/claude-code/issues/5886) -- Settings validation passes invalid types
- [#16402](https://github.com/anthropics/claude-code/issues/16402) -- MCP server enablement not supported in settings.local.json
- [#2014](https://github.com/anthropics/claude-code/issues/2014) -- settings.local.json does not work
- [#944](https://github.com/anthropics/claude-code/issues/944) -- Claude edits .gitignore
- [#25966](https://github.com/anthropics/claude-code/issues/25966) -- Request for permanent auto-approval of read-only MCP tools

### Community Guides and References
- [Trail of Bits claude-code-config](https://github.com/trailofbits/claude-code-config) -- Security-hardened settings template
- [Trail of Bits settings.json](https://github.com/trailofbits/claude-code-config/blob/main/settings.json) -- Actual settings file
- [SchemaStore JSON Schema](https://json.schemastore.org/claude-code-settings.json) -- Community-maintained JSON Schema
- [Community-generated schema gist](https://gist.github.com/xdannyrobertsx/0a395c59b1ef09508e52522289bd5bf6) -- Detailed schema definition
- [ClaudeLog Configuration Guide](https://claudelog.com/configuration/) -- Community documentation hub
- [eesel.ai settings.json guide](https://www.eesel.ai/blog/settings-json-claude-code) -- Developer guide (2025)
- [eesel.ai permissions guide](https://www.eesel.ai/blog/claude-code-permissions) -- Complete permissions guide
- [claudefa.st Settings Reference](https://claudefa.st/blog/guide/settings-reference) -- Complete config guide
- [Shipyard CLI Cheatsheet](https://shipyard.build/blog/claude-code-cheat-sheet/) -- Commands and config reference
- [Instructa allowedTools guide](https://www.instructa.ai/blog/claude-code/how-to-use-allowed-tools-in-claude-code) -- AllowedTools tutorial
- [managed-settings.com](https://managed-settings.com/) -- Managed settings guide
- [DevHints cheatsheet](https://devhints.io/claude-code) -- Quick reference
- [Medium: Naqeeb ali Shamsi](https://naqeebali-shamsi.medium.com/the-complete-guide-to-setting-global-instructions-for-claude-code-cli-cec8407c99a0) -- Global instructions guide
- [Medium: Claude Code Internals Part 8](https://kotrotsos.medium.com/claude-code-internals-part-8-the-permission-system-624bd7bb66b7) -- Permission system deep dive
- [SFEIR Institute Troubleshooting](https://institute.sfeir.com/en/claude-code/claude-code-permissions-and-security/troubleshooting/) -- Permissions troubleshooting
- [Pete Freitag: Understanding Permissions](https://www.petefreitag.com/blog/claude-code-permissions/) -- Security settings overview
- [DeepWiki: settings.json Reference](https://deepwiki.com/trailofbits/claude-code-config/2.1-settings.json) -- Trail of Bits settings analysis
- [Korny's Blog: Better Permissions](https://blog.korny.info/2025/10/10/better-claude-code-permissions) -- Permission hook patterns
- [DataCamp: Hooks Tutorial](https://www.datacamp.com/tutorial/claude-code-hooks) -- Practical hooks guide
- [CAIO: Claude Code Settings Guide 2026](https://www.thecaio.ai/blog/claude-code-settings-guide) -- Settings configuration guide
- [Claude Code tools system prompt gist](https://gist.github.com/wong2/e0f34aac66caf890a332f7b6f9e2ba8f) -- Internal tool definitions
- [Internal tools implementation gist](https://gist.github.com/bgauryy/0cdb9aa337d01ae5bd0c803943aa36bd) -- Tool implementation details
- [vtrivedy: Built-in Tools Reference](https://www.vtrivedy.com/posts/claudecode-tools-reference) -- Comprehensive tools listing

### Hacker News Discussions
- [Claude Code 2.0](https://news.ycombinator.com/item?id=45416228) -- Release discussion
- [Getting good results from Claude Code](https://news.ycombinator.com/item?id=44836879) -- Usage tips
- [How Do You Actually Use Claude Code Effectively?](https://news.ycombinator.com/item?id=44362244) -- Community best practices
- [Claude Code's new hidden feature: Swarms](https://news.ycombinator.com/item?id=46743908) -- Agent teams feature

### Security References
- [The Register: Claude Code ignores ignore rules](https://www.theregister.com/2026/01/28/claude_code_ai_secrets_files/) -- Security coverage
- [Medium: Hardening Claude Code](https://medium.com/@emergentcap/hardening-claude-code-a-security-review-framework-and-the-prompt-that-does-it-for-you-c546831f2cec) -- Security review framework
- [ksred.com: Safe Usage Guide](https://www.ksred.com/claude-code-dangerously-skip-permissions-when-to-use-it-and-when-you-absolutely-shouldnt/) -- --dangerously-skip-permissions guide
- [Agent SDK Permissions](https://platform.claude.com/docs/en/agent-sdk/permissions) -- SDK-level permission docs
- [Agent SDK Issue #115](https://github.com/anthropics/claude-agent-sdk-typescript/issues/115) -- allowedTools doesn't restrict built-in tools (security issue)

---

## Summary of NOVEL FIND Items

1. **`skipDangerousModePermissionPrompt`** -- Undocumented boolean auto-written to user settings when accepting bypass mode warning. Not in official settings reference (Issue #26233, filed 2026-02-16).

2. **Subagent deny rule bypass** -- Sub-agents bypass parent `deny` rules from `settings.local.json`, creating a security hole (Issue #25000).

3. **bypassPermissions unconditional inheritance** -- ALL subagents inherit bypass mode with no override possible, creating privilege escalation risk (Issue #20264).

4. **Windows managed settings path change** -- Changed in v2.1.2 from `C:\ProgramData\ClaudeCode\` to `C:\Program Files\ClaudeCode\`.

5. **Settings merge bug** -- Project `settings.local.json` overwrites global settings entirely instead of deep merging (Issue #19487).

6. **MCP wildcard inconsistency** -- Community reports suggest `mcp__github__*` wildcards may not work in settings.json permission arrays despite being shown in official docs.

7. **Trail of Bits YOLO recommendation** -- A security auditing firm recommends `--dangerously-skip-permissions` as production mode, relying on sandbox + hooks instead of permission prompts.

8. **PreToolUse input modification** -- Since v2.0.10, hooks can transparently modify tool inputs before execution, enabling automatic parameter correction without blocking and retrying.

9. **Unofficial environment variables** -- `CLAUDE_CODE_BYPASS_ALL_PERMISSIONS`, `CLAUDE_CODE_SUPPRESS_UI_PROMPTS`, `ANTHROPIC_DISABLE_SAFETY_CHECKS` exist but are NOT officially supported or reliable.

10. **VSCode extension limitations** -- The extension does NOT fully respect `settings.local.json` for Bash/Write/Edit operations, even with `bypassPermissions` mode enabled (Issue #15921).
