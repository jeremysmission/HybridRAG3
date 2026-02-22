# Maximizing Claude Code CLI Productivity

**Research Date**: 2026-02-21
**Sources**: Reddit (r/ClaudeAI), GitHub Issues/Discussions, Hacker News, Official Anthropic Docs, Developer Blogs, YouTube, X/Twitter, Stack Overflow, Substack

---

## Table of Contents

1. [Optimal CLAUDE.md Structure](#1-optimal-claudemd-structure)
2. [Writing Work Orders That Minimize Friction](#2-writing-work-orders-that-minimize-friction)
3. [Effective Use of the Task Tool and Subagents](#3-effective-use-of-the-task-tool-and-subagents)
4. [Compaction Strategies to Preserve Context](#4-compaction-strategies-to-preserve-context)
5. [Structuring Handover Documents](#5-structuring-handover-documents)
6. [Token Usage Optimization](#6-token-usage-optimization)
7. [Community Best Practices](#7-community-best-practices)
8. [Known Gotchas and Anti-Patterns](#8-known-gotchas-and-anti-patterns)

---

## 1. Optimal CLAUDE.md Structure

### What the Model Actually Pays Attention To

Frontier thinking LLMs can follow approximately 150-200 instructions with reasonable consistency. Claude Code's own system prompt already contains around 50 individual instructions, consuming nearly a third of the total instruction budget. As your CLAUDE.md grows, instruction-following quality degrades **uniformly** -- it does not simply ignore newer instructions, it begins to ignore all of them equally.

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

### Size Guidelines

- **Target**: 50-100 lines for the root CLAUDE.md
- **Hard ceiling**: Do not exceed 150 lines without using `@imports` for detailed sections
- **Professional monorepo ceiling**: Up to 13KB, could grow to 25KB with imports
- **Litmus test**: For each line, ask "Would removing this cause Claude to make mistakes?" If not, cut it

**Source**: [Writing a Good CLAUDE.md - HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)

### What to Include (High Signal)

| Section | Why It Matters |
|---------|---------------|
| **Build/test/lint commands** | Claude cannot guess non-standard commands |
| **Code style rules that differ from defaults** | Only deviations from what Claude already knows |
| **Testing instructions and preferred runners** | Which framework, how to run single tests |
| **Repository etiquette** | Branch naming, commit format, PR conventions |
| **Architecture decisions** | Project-specific patterns Claude cannot infer |
| **Developer environment quirks** | Required env vars, platform-specific issues |
| **Common gotchas or "Do Not Touch" areas** | Files/directories Claude must avoid |

### What to Exclude (Low Signal / Harmful)

| Exclusion | Reason |
|-----------|--------|
| **Standard language conventions** | Claude already knows these |
| **Code style as prose instructions** | Use a linter/formatter instead -- hooks are deterministic |
| **Detailed API documentation** | Link to docs; do not paste them |
| **Information that changes frequently** | It will become stale and misleading |
| **Long explanations or tutorials** | Wastes context budget every session |
| **File-by-file codebase descriptions** | Claude can read the code itself |
| **Self-evident practices ("write clean code")** | Zero informational value |

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

### Recommended Section Structure

```markdown
# Project Name

## Build & Test
- `npm run build` -- compile TypeScript
- `npm test -- --run path/to/test.ts` -- run single test

## Code Style
- ES modules (import/export), not CommonJS (require)
- Destructure imports when possible

## Architecture
- [Brief pointer to key patterns, not exhaustive descriptions]

## Workflow Rules
- Always typecheck after a series of code changes
- Never modify files under migrations/ directly

## Do Not Touch
- eval/*.json -- golden evaluation sets
- scripts/run_eval.py -- scoring logic
```

### [NOVEL FIND] Emphasis Words for Critical Rules

Emphasis words like "IMPORTANT", "CRITICAL", "YOU MUST", and "NEVER" can measurably improve adherence to specific rules. However, this only works when used **sparingly**. If everything is marked IMPORTANT, nothing is. Reserve emphasis for 2-3 truly critical constraints.

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices), [How to Write a Good CLAUDE.md - Builder.io](https://www.builder.io/blog/claude-md-guide)

### File Placement Hierarchy

Claude Code reads CLAUDE.md files in this order:

1. **Home folder** (`~/.claude/CLAUDE.md`) -- applies to all sessions
2. **Project root** (`./CLAUDE.md`) -- shared with team via git
3. **Parent directories** -- useful for monorepos
4. **Child directories** -- pulled in on demand when Claude works in that directory

Use `CLAUDE.local.md` (gitignored) for personal overrides that should not be shared.

### Using @imports for Progressive Disclosure

```markdown
# CLAUDE.md
See @README.md for project overview.
Git workflow: @docs/git-instructions.md
Personal overrides: @~/.claude/my-project-instructions.md
```

This keeps the root file short while making detailed context available on demand.

### [NOVEL FIND] CLAUDE.md as a Self-Improving System

Boris Cherny (Claude Code creator) recommends: after every correction, end with "Update your CLAUDE.md so you don't make that mistake again." The team iterates until Claude's mistake rate measurably drops. Treat CLAUDE.md like code -- review it when things go wrong, prune regularly.

**Source**: [10 Tips from Inside the Claude Code Team](https://paddo.dev/blog/claude-code-team-tips/), [Boris Cherny on Threads](https://www.threads.com/@boris_cherny/post/DUMZr4VElyb)

### [NOVEL FIND] Convert Instructions to Hooks When Possible

If a rule must be followed 100% of the time with zero exceptions, it should not be a CLAUDE.md instruction -- it should be a **hook**. CLAUDE.md instructions are advisory. Hooks are deterministic. Converting advisory rules to hooks both guarantees enforcement AND reduces the CLAUDE.md instruction count, improving adherence to remaining rules.

**Source**: [Automate Workflows with Hooks - Claude Code Docs](https://code.claude.com/docs/en/hooks-guide)

---

## 2. Writing Work Orders That Minimize Friction

### Permission Reduction: The 84% Improvement

Anthropic's sandboxing feature reduces permission prompts by 84% in internal usage. Run `/sandbox` to enable OS-level filesystem and network isolation.

**Source**: [Beyond Permission Prompts - Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-sandboxing)

### Permission Modes (Least to Most Autonomous)

| Mode | How to Activate | What It Does |
|------|----------------|--------------|
| **Standard** | Default | Asks for every sensitive operation |
| **acceptEdits** | Shift+Tab once | Auto-approves file edits, still asks for Bash |
| **Plan Mode** | Shift+Tab twice | Creates plan first, then executes after approval |
| **bypassPermissions** | `--dangerously-skip-permissions` | Skips ALL prompts (use in sandbox only) |

### Configuring settings.json for Zero-Friction Workflows

Pre-approve safe commands to eliminate repetitive approval:

```json
{
  "permissions": {
    "allow": [
      "Bash(npm run lint)",
      "Bash(npm run test *)",
      "Bash(python -m pytest *)",
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git add *)",
      "Bash(git commit *)"
    ],
    "deny": [
      "Read(**/.env)",
      "Read(**/.env.*)",
      "Read(**/secrets/**)",
      "Bash(rm -rf *)",
      "Bash(git push --force *)",
      "Bash(git reset --hard *)"
    ]
  }
}
```

Rules evaluate in order: deny first, then ask, then allow. The first match wins.

**Source**: [Configure Permissions - Claude Code Docs](https://code.claude.com/docs/en/permissions), [Claude Code Settings - Claude Code Docs](https://code.claude.com/docs/en/settings)

### Prompt Phrasing That Minimizes Back-and-forth

| Anti-pattern | Better Phrasing |
|-------------|-----------------|
| "improve this codebase" | "add input validation to the login function in auth.ts" |
| "fix the login bug" | "users report login fails after session timeout. check auth flow in src/auth/, especially token refresh. write a failing test, then fix it" |
| "add tests for foo.py" | "write a test for foo.py covering the edge case where user is logged out. avoid mocks." |
| "make the dashboard look better" | "[paste screenshot] implement this design. take a screenshot and compare to original. list differences and fix them" |

### The "Interview Me" Pattern

For complex features, have Claude interview you first:

```
I want to build [brief description]. Interview me in detail using the AskUserQuestion tool.
Ask about technical implementation, UI/UX, edge cases, concerns, and tradeoffs.
Don't ask obvious questions, dig into the hard parts I might not have considered.
Keep interviewing until we've covered everything, then write a complete spec to SPEC.md.
```

Then start a fresh session to execute the spec. The new session has clean context focused entirely on implementation.

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

### [NOVEL FIND] The "Grill Me" Pattern from Boris Cherny

Prompt: "Grill me on these changes and don't make a PR until I pass your test." This inverts the feedback loop -- Claude becomes the reviewer, forcing you to validate your own assumptions before committing.

After mediocre results: "Knowing everything you know now, scrap this and implement the elegant solution."

**Source**: [Boris Cherny on Threads](https://www.threads.com/@boris_cherny/post/DUMZr4VElyb)

### [NOVEL FIND] The Writer/Reviewer Pattern

Run two parallel Claude sessions:

| Session A (Writer) | Session B (Reviewer) |
|---|---|
| "Implement a rate limiter for our API endpoints" | |
| | "Review the rate limiter in @src/middleware/rateLimiter.ts. Look for edge cases, race conditions, consistency with existing patterns." |
| "Here's the review feedback: [Session B output]. Address these issues." | |

A fresh context improves code review quality since Claude will not be biased toward code it just wrote.

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

---

## 3. Effective Use of the Task Tool and Subagents

### Context Inheritance Model

Subagents start with **zero conversation context** by default. They inherit:
- Parent conversation's permissions (with additional restrictions)
- All the same tools as the main agent (except they cannot spawn sub-tasks)
- CLAUDE.md project context (from `.claude/agents/` definitions)
- MCP tools (if not explicitly restricted)

They do NOT inherit:
- Conversation history
- Files previously read
- Decisions or context from the main thread

There is an open feature request ([#16153](https://github.com/anthropics/claude-code/issues/16153)) for `fork_context: true` to enable full conversation inheritance.

**Source**: [Create Custom Subagents - Claude Code Docs](https://code.claude.com/docs/en/sub-agents), [Task Tool vs Subagents - iBuildWith.ai](https://www.ibuildwith.ai/blog/task-tool-vs-subagents-how-agents-work-in-claude-code/)

### When to Use Parallel vs Sequential

**Parallel dispatch** (ALL conditions must be met):
- 3+ unrelated tasks or independent domains
- No shared state between tasks
- Clear file boundaries with no overlap

**Sequential dispatch** (ANY condition triggers):
- Tasks have dependencies (B needs output from A)
- Shared files or state (merge conflict risk)
- Unclear scope

**Background dispatch**:
- Research or analysis tasks (not file modifications)
- Results that are not blocking your current work

### Subagent Definition Example

```markdown
# .claude/agents/security-reviewer.md
---
name: security-reviewer
description: Reviews code for security vulnerabilities
tools: Read, Grep, Glob, Bash
model: opus
---
You are a senior security engineer. Review code for:
- Injection vulnerabilities (SQL, XSS, command injection)
- Authentication and authorization flaws
- Secrets or credentials in code
- Insecure data handling

Provide specific line references and suggested fixes.
```

### Key Constraints

- **Subagents cannot spawn other subagents** -- Task(agent_type) has no effect in subagent definitions
- **Each subagent gets its own context window** -- this is a feature, not a limitation
- **Subagents report back summaries** -- keeping main context clean

### [NOVEL FIND] Subagents for Context Preservation

Anthropic's best practices guide explicitly recommends: "using subagents to verify details or investigate particular questions, especially early on in a conversation or task, tends to preserve context availability without much downside."

Translation: delegate research to subagents to keep your main context clean for implementation work. Every file Claude reads in your main session consumes context permanently until compaction.

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

### [NOVEL FIND] Using Lighter Models for Subagents

Run your main session on Opus for complex reasoning while subagents handle focused tasks on Sonnet. This cuts costs significantly without sacrificing quality on well-scoped subagent work. Specify the model in the agent definition frontmatter.

**Source**: [Claude Code Sub-Agents Best Practices](https://claudefa.st/blog/guide/agents/sub-agent-best-practices)

### Agent Teams (Swarms) -- Research Preview

As of February 2026, Claude Code supports **agent teams** -- multiple Claude instances working in parallel with coordination. Enable with:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

Key characteristics:
- One session acts as team lead, coordinating work
- Teammates work independently in their own context windows
- Uses git worktree isolation to prevent file conflicts
- Teammates communicate directly with each other (unlike subagents which only report to parent)
- You can interact with individual teammates directly
- Single-agent Claude uses 80-90% of context before reset; with teams, around 40%

Known limitations: no session resumption with in-process teammates, task status can lag, one team per session, no nested teams.

**Source**: [Orchestrate Teams - Claude Code Docs](https://code.claude.com/docs/en/agent-teams), [Claude Code Swarms - Addy Osmani](https://addyosmani.com/blog/claude-code-agent-teams/)

---

## 4. Compaction Strategies to Preserve Context

### How Auto-Compaction Works

When conversation approaches the context window limit, Claude Code:
1. Analyzes the conversation for key information
2. Creates a concise summary preserving code patterns, file states, and decisions
3. Replaces old messages with the summary
4. Continues with preserved context

### Context Window Breakdown (200K total)

| Component | Tokens | Percentage |
|-----------|--------|------------|
| System prompt | ~2,700 | 1.3% |
| System tools | ~16,800 | 8.4% |
| Custom agents | ~1,300 | 0.7% |
| Memory files (CLAUDE.md etc.) | ~7,400 | 3.7% |
| Skills | ~1,000 | 0.5% |
| Autocompact buffer | ~33,000 | 16.5% |
| **Usable for conversation** | **~137,800** | **~69%** |

The buffer was reduced from 45K to 33K tokens in early 2026, giving approximately 12K more usable space.

**Source**: [Claude Code Context Buffer](https://claudefa.st/blog/guide/mechanics/context-buffer-management)

### The CLAUDE_AUTOCOMPACT_PCT_OVERRIDE Variable

```bash
# Set in shell profile for persistence
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80

# Or in settings.json
{ "env": { "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80" } }
```

Setting it to 80 triggers compaction earlier than the default ~90-95% threshold. Earlier compaction preserves more context quality because the LLM has more room to think during the summarization step.

**Source**: [Ivor on X](https://x.com/madebyivor/status/1983808762948276580)

### What Gets Lost in Compaction

Compaction is a **one-way lossy transformation**. What typically gets lost:
- Specific variable names and exact error messages
- Nuanced decisions from early in the session
- Repository path context
- Skills context
- Agent team state

**Source**: [Claude Saves Tokens, Forgets Everything - Alexander Golev](https://golev.com/post/claude-saves-tokens-forgets-everything/)

### Strategy 1: Manual Compaction at Logical Breakpoints

Instead of letting auto-compact happen randomly, trigger `/compact` manually at strategic moments with preservation instructions:

```
/compact Focus on the API changes and the list of modified files
/compact Preserve the full test plan and all error messages encountered
/compact Only keep the names of the websites we reviewed
```

### Strategy 2: Plan Mode for Compaction Persistence

Plans and to-do items persist across compaction events because they are structured, named artifacts with clear boundaries and explicit state (pending/in progress/completed). The compaction algorithm treats them as higher-priority context.

Start sessions in Plan Mode and request a comprehensive to-do list at the outset. This creates an anchor that survives summarization.

**Source**: [Claude Code Compaction: Plan Mode Persistence](https://reading.torqsoftware.com/notes/software/ai-ml/agentic-coding/2026-01-11-claude-code-compaction-plan-mode-persistence/)

### Strategy 3: CLAUDE.md Compaction Instructions

Add instructions to CLAUDE.md that control what compaction preserves:

```markdown
When compacting, always preserve:
- The full list of modified files
- All test commands and their results
- Any error messages encountered
- The current task plan and status
```

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

### Strategy 4: External File Persistence

Maintain state in external files that survive compaction entirely:
- `TODO.md` -- current task list with status
- `DECISIONS.md` -- architectural decisions and rationale
- `ERRORS.md` -- encountered errors and solutions
- `HANDOFF.md` -- full session state for fresh pickup

### Strategy 5: Disable Unused MCP Servers

Before resorting to compaction, use `/context` to identify MCP servers consuming context space. Disabling unused servers can free significant space and potentially avoid compaction entirely.

### [NOVEL FIND] Disabling Auto-Compaction

There is no official documentation for disabling auto-compaction. Community-discovered methods:
- `/config` then toggle "Auto-compact" (per-session)
- `claude config set -g autoCompactEnabled false` (writes to `~/.claude.json`)
- Edit `~/.claude.json` directly
- `DISABLE_AUTO_COMPACT=true` environment variable

**Source**: [GitHub Issue #24589](https://github.com/anthropics/claude-code/issues/24589)

### [NOVEL FIND] Selective Rewind as Compaction Alternative

Use `Esc + Esc` or `/rewind`, select a message checkpoint, and choose **Summarize from here**. This condenses messages from that point forward while keeping earlier context intact -- much more surgical than full compaction.

**Source**: [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)

---

## 5. Structuring Handover Documents

### Why Handover Documents Matter

When a Claude Code session hits its maximum context window, the session effectively dies. Compaction can only compress so much. The only option is to start a fresh session and manually re-explain everything. A handover document captures essential context so a fresh instance picks up instantly.

A well-structured handoff turns a 10,000+ token knowledge transfer into a 1,000-2,000 token resume operation.

### The Simple Prompt (Works Immediately)

```
Put the rest of the plan in HANDOFF.md. Explain what you have tried,
what worked, what didn't work, so that the next agent with fresh context
is able to just load that file and nothing else to get started on this
task and finish it up.
```

Then start a fresh conversation: `claude "Read HANDOFF.md and continue the work described there."`

**Source**: [ykdojo on Threads](https://www.threads.com/@ykdojo/post/DTdoUtKkhOm)

### Recommended Handover Template

```markdown
# Handoff: [Task Title]
**Generated**: [Date]
**Branch**: [branch name]
**Status**: In Progress | Blocked | Review Ready

## Goal
[One-sentence description of what you are trying to accomplish]

## Completed
- [x] Task 1 -- brief description of what was done
- [x] Task 2

## Not Yet Done
- [ ] Remaining task 1
- [ ] Remaining task 2

## Failed Approaches (DO NOT REPEAT)
### Approach 1: [Name]
- What was tried: [specific details]
- Why it failed: [exact error message or behavior]
- Key learning: [what this ruled out]

## Key Decisions Made
- Decision 1: [choice] because [rationale]
- Decision 2: [choice] because [rationale]

## Important Context
- Constraint 1: [detail]
- Constraint 2: [detail]

## Files Modified
- `path/to/file1.py` -- [what changed and why]
- `path/to/file2.ts` -- [what changed and why]

## Next Steps (Start Here)
1. [Immediate next action with specific file paths]
2. [Following action]

## Verification
- Run `[specific test command]` -- expect [specific result]
- Check `[specific endpoint/file]` -- expect [specific behavior]
```

### Critical Elements in Handover Documents

1. **Failed approaches are mandatory** -- this is the most valuable section. "Tried X, it didn't work because Y" saves hours of repeated failure.

2. **Show code, don't describe** -- "Created a hook" is useless. Show the function signature so the next agent knows how to use it.

3. **Test steps need expected outcomes** -- not "verify it works" but "POST to /api/X, expect 200 with `{ status: 'ok' }`".

4. **Include actual error messages** -- "It threw an error" vs "TokenExpiredError at line 42" is a huge difference.

**Source**: [Claude Code Decoded: The Handoff Protocol - Black Dog Labs](https://blackdoglabs.io/blog/claude-code-decoded-handoff-protocol)

### Community Tools for Automated Handoff

| Tool | Description |
|------|-------------|
| [claude-code-handoff](https://github.com/Sonovore/claude-code-handoff) | `/handoff` command with auto-load on next session via hooks |
| [claude-handoff](https://github.com/willseltzer/claude-handoff) | Plugin marketplace handoff generator |
| [Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) | Full state management via ledgers; "compound, don't compact" philosophy |
| [claude-sessions](https://github.com/iannuttall/claude-sessions) | Session tracking with custom slash commands |
| `/wipe` command ([GitHub Gist](https://gist.github.com/GGPrompts/62bbf077596dc47d9f424276575007a1)) | Auto-generates handoff, clears context, resumes in fresh session |

### [NOVEL FIND] The "Smart Handoff" Timing

Trigger handoff generation at 70-80% context usage, BEFORE compaction happens. Once compaction fires, you have already lost precision. The handoff document should be generated from full-fidelity context.

**Source**: [Smart Handoff for Claude Code](https://blog.skinnyandbald.com/never-lose-your-flow-smart-handoff-for-claude-code/)

### [NOVEL FIND] Session Resume vs Handoff

`claude --continue` and `claude --resume` exist for resuming sessions, but they carry ALL the context baggage. Community consensus: handoff documents produce better results for complex work because the fresh session gets a clean, curated context rather than a bloated conversation history.

Use `/rename` to give sessions descriptive names ("oauth-migration", "debugging-memory-leak") for easier resume if needed.

**Source**: [Claude Code Session Management - Steve Kinney](https://stevekinney.com/courses/ai-development/claude-code-session-management)

---

## 6. Token Usage Optimization

### The Fundamental Cost Equation

Input tokens are not just your prompt -- they include your prompt PLUS entire conversation history, PLUS every file Claude read, PLUS command outputs, PLUS CLAUDE.md, PLUS system instructions, PLUS MCP tool definitions. All of it, every single turn. So when your session becomes a three-hour saga, you pay for the model to re-process the entire conversation before delivering each new response.

### Top Strategies Ranked by Impact

#### 1. Clear Between Tasks (50-70% savings alone)

```
/clear
```

Stale context wastes tokens on every subsequent message. Most developers report that `/clear` between tasks combined with a good CLAUDE.md file cuts token consumption by 50-70%.

#### 2. Model Selection Per Task

| Task Type | Recommended Model | Reason |
|-----------|------------------|--------|
| Simple edits, renames, log lines | Haiku | Fast, cheap |
| Standard implementation | Sonnet | Good balance |
| Complex reasoning, architecture | Opus | Best quality |
| Planning phase | opusplan | Opus for plan, Sonnet for execution |

OpusPlan achieves 10-20% Opus / 80-90% Sonnet distribution automatically.

#### 3. Proactive /compact Usage

Run `/compact` with specific preservation instructions BEFORE context fills naturally. This prevents context exhaustion and maintains consistent performance.

#### 4. Disable Unused MCP Servers

Each MCP server adds approximately 2,000 tokens to context before any operations. Use `/context` to see consumption, then disable what you do not need.

#### 5. Control Extended Thinking Budget

Extended thinking defaults to ~32K tokens (billed as expensive output tokens). For simple tasks, this is massive overkill. Set `MAX_THINKING_TOKENS` to reduce for straightforward work.

#### 6. Specific Prompts Over Vague Requests

Vague requests trigger broad file scanning. "Improve this codebase" causes Claude to read dozens of files. "Add input validation to the login function in auth.ts" lets Claude work with minimal reads.

### [NOVEL FIND] CLAUDE_CODE_MAX_OUTPUT_TOKENS

```bash
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
```

Doubles the default output token limit, preventing truncation when generating long outputs. The 200K context window is shared between input and output -- reserving 64K for output leaves roughly 136K for input.

**Important**: This does NOT control the compaction buffer. Setting it to 16000 shortens response length but does NOT give you more context before compaction triggers.

**Source**: [Debugging Claude Code - TurboAI.dev](https://www.turboai.dev/blog/debugging-claude-code-issues)

### [NOVEL FIND] Lazy Loading for MCP Tools (85% Context Reduction)

The `ENABLE_TOOL_SEARCH` environment variable (auto mode) enables MCP tool lazy loading optimization, reducing context token consumption from 55K to 8.7K tokens (85% reduction) while improving tool selection accuracy.

**Source**: [Claude Code Context Optimization - GitHub Gist](https://gist.github.com/johnlindquist/849b813e76039a908d962b2f0923dc9a)

### [NOVEL FIND] Skill Descriptions Context Budget

Skill descriptions consume context so Claude knows what is available. The budget scales dynamically at 2% of the context window, with a fallback of 16,000 characters. If you have many skills, run `/context` to check for warnings about excluded skills. Override with `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable.

For heavy skills that are rarely needed, set `disable-model-invocation: true` so they only load when explicitly called.

**Source**: [Slash Commands - Claude Code Docs](https://code.claude.com/docs/en/slash-commands)

### [NOVEL FIND] Prompt Caching Configuration

Claude Code automatically uses prompt caching to save up to 90% on repeated content. You can disable it with `DISABLE_PROMPT_CACHING` or configure model-specific settings. The global setting takes precedence over model-specific settings.

**Source**: [Model Configuration - Claude Code Docs](https://code.claude.com/docs/en/model-config)

### Monitoring Token Usage

**Custom Status Line** (built-in, no extra tools needed):

Run `/statusline` to have Claude generate a monitoring script. It receives JSON session data including `used_percentage`, `total_input_tokens`, `total_output_tokens`, `context_window_size`, and `current_usage` breakdown. Does not consume API tokens.

**Claude Code Usage Monitor** (external tool):

```bash
# Install and run
claude-monitor
```

Shows real-time cost, token usage, and message limits.

**Source**: [Status Line Configuration - Claude Code Docs](https://code.claude.com/docs/en/statusline)

### Cost Benchmarks (2026)

- Average: $6 per developer per day
- 90th percentile: Below $12 per day
- Subscription tiers: Pro $20/mo (5x) | Max 5x $100/mo | Max 20x $200/mo

---

## 7. Community Best Practices

### From Boris Cherny (Claude Code Creator)

**Source**: [10 Tips from Inside the Claude Code Team](https://paddo.dev/blog/claude-code-team-tips/), [How Boris Uses Claude Code](https://howborisusesclaudecode.com/)

1. **Parallelization via git worktrees is the #1 tip**: Spin up 3-5 worktrees, each running its own Claude session. This is the single biggest productivity unlock. Use `claude --worktree feature-auth` or aliases (za, zb, zc) to hop between them.

2. **Most sessions start in Plan Mode**: Go back and forth until you like the plan. Then switch to auto-accept edits and Claude usually one-shots execution.

3. **Verification is the most important thing**: "Probably the most important thing to get great results: give Claude a way to verify its work. If Claude has that feedback loop, it will 2-3x the quality of the final result."

4. **If you do something more than once a day, make it a skill**: Examples include `/techdebt` (find/kill duplicated code), context dump commands that sync Slack/GDrive/Asana/GitHub, analytics agents that write dbt models.

5. **Boris personally runs Opus 4.5 with thinking for all coding**, valuing quality and reliability over speed. Setup is "surprisingly vanilla."

6. **Use voice dictation for prompts**: fn x2 on macOS -- you speak 3x faster than you type.

### From ykdojo (45 Claude Code Tips)

**Source**: [ykdojo/claude-code-tips on GitHub](https://github.com/ykdojo/claude-code-tips)

1. **[NOVEL FIND] Use Gemini CLI as a fallback for web access**: Claude Code's WebFetch cannot access certain sites (like Reddit). Create a skill that tells Claude to use Gemini CLI as a fallback -- Gemini has broader web access.

2. **[NOVEL FIND] Running Claude Code in containers**: For research or risky experimentation, run Claude in a Docker container. If something goes wrong, it is contained. Especially useful for the Reddit research workflow where `--dangerously-skip-permissions` is needed.

3. **[NOVEL FIND] System prompt patching**: The author created a system for simplifying Claude Code's system prompt in the minified JavaScript bundle. When new versions come out, patches need updating. Claude Code itself can explore the minified JS, find variable mappings, and create new patch files.

4. **Turn off auto-compact for more control**: Use `/config` to disable auto-compact, then manage compaction manually at strategic breakpoints.

### From Reddit (r/ClaudeAI) and Community

1. **Add a "Mistakes to avoid" section to CLAUDE.md**: If Claude keeps making the same error, document it once and it stops.

2. **Use `--print` flag for scripts/CI**: Headless mode uses significantly fewer tokens than interactive sessions.

3. **Let Claude check its own work**: Prompt with "double check everything, every single claim in what you produced and at the end make a table of what you were able to verify."

4. **Start fresh conversations for best performance**: A new conversation always performs best because it does not carry previous context complexity.

5. **Have Claude generate draft PRs**: Create a draft PR, check content, then convert to real PR.

### Hooks for Workflow Automation

**Source**: [Automate Workflows with Hooks - Claude Code Docs](https://code.claude.com/docs/en/hooks-guide), [GitButler Hooks](https://blog.gitbutler.com/automate-your-ai-workflows-with-claude-code-hooks)

| Hook Event | Use Case | Example |
|-----------|----------|---------|
| **PreToolUse** | Block dangerous commands | Exit code 2 + stderr message for `rm -rf`, `git reset --hard` |
| **PostToolUse** | Auto-format after edits | Run Prettier/Black on every file Claude modifies |
| **PostToolUse** | Auto-run tests | Run pytest when source/test files change |
| **PostToolUse** | Auto-commit | Create small commits tracking agent work |
| **Notification** | Desktop alerts | Notify when Claude needs input so you can multitask |
| **SessionStart** | Context injection | Load handoff document or project state |

Hook exit codes: 0 = allow/ok, 2 = block (PreToolUse only, message to stderr), other non-zero = non-blocking error.

### [NOVEL FIND] GitButler Auto-Branch Hook

GitButler provides a hook that gives each Claude session a unique ID and auto-sorts simultaneous AI coding into separate branches. Run 3 Claude sessions at once and GitButler assigns each change to the correct branch automatically. When done, it commits all changes and writes a sophisticated commit message.

**Source**: [GitButler Hooks Blog](https://blog.gitbutler.com/automate-your-ai-workflows-with-claude-code-hooks)

### [NOVEL FIND] The /wipe Compound Command

A community-created slash command that:
1. Generates a concise handoff summary
2. Clears context automatically
3. Resumes with the handoff in a fresh session

All in one command, eliminating the manual handoff dance.

**Source**: [GitHub Gist - /wipe command](https://gist.github.com/GGPrompts/62bbf077596dc47d9f424276575007a1)

---

## 8. Known Gotchas and Anti-Patterns

### Critical Anti-Patterns

#### 1. The Kitchen Sink Session
Starting with one task, asking something unrelated, then going back. Context fills with irrelevant information.
**Fix**: `/clear` between unrelated tasks.

#### 2. Jumping Straight to Code Without Planning
Letting Claude start writing code immediately for complex changes. This "feels productive" but almost always creates downstream pain.
**Fix**: Use Plan Mode (Shift+Tab twice). Separate exploration from execution.

#### 3. Repeatedly Correcting the Same Mistake
Claude does something wrong, you correct it, still wrong, correct again. Context is now polluted with failed approaches and the model is anchored on the wrong solution.
**Fix**: After two failed corrections, `/clear` and write a better initial prompt incorporating what you learned. A clean session with a better prompt almost always outperforms a long session with accumulated corrections.

#### 4. Overloading CLAUDE.md
Too many instructions cause uniform degradation of instruction-following. If Claude keeps violating a rule despite it being in CLAUDE.md, the file is too long and the rule is getting lost.
**Fix**: Ruthlessly prune. Convert mandatory rules to hooks. Use `@imports` for detailed sections. Move situational knowledge to skills.

#### 5. The Trust-Then-Verify Gap
Claude produces plausible-looking code that does not handle edge cases.
**Fix**: Always provide verification (tests, scripts, screenshots). If you cannot verify it, do not ship it.

#### 6. The Infinite Exploration
Asking Claude to "investigate" something without scoping it. Claude reads hundreds of files, filling the context.
**Fix**: Scope investigations narrowly or use subagents so exploration does not consume main context.

### Platform-Specific Gotchas

#### Windows
- **UnicodeEncodeError**: Wrap stdout with `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')`
- **git safe.directory**: Needed for cloned repos on Windows
- **Path separators**: Claude sometimes generates Windows-style backslashes even when told to use forward slashes
- **PowerShell encoding**: UTF-8 BOM and CRLF line endings required for PowerShell files

#### Compilation
Claude will forget to compile before running tests when working with compiled languages. If you work with compiled languages interspersed with interpreted ones, add explicit compilation steps to your CLAUDE.md.

**Source**: [Claude Code Gotchas - DoltHub](https://www.dolthub.com/blog/2025-06-30-claude-code-gotchas/)

### Context Compaction Gotchas

- Claude does not know what files it was looking at after compaction and needs to re-read them
- It will make mistakes you specifically corrected earlier in the session
- If it gave up on an approach earlier, it may give up again
- However, sometimes compaction helps by restarting the thinking process when Claude was on the wrong track

**Source**: [Claude Code Gotchas - DoltHub](https://www.dolthub.com/blog/2025-06-30-claude-code-gotchas/)

### [NOVEL FIND] Permission Deny Bug

As of version 1.0.93, the deny permission system in `settings.json` was reported as **completely non-functional** in certain cases. All tested deny rules were ignored, allowing unrestricted access to files that should be blocked. This is a significant security concern.

**Workaround**: Use a **PreToolUse hook** instead of deny rules for critical security boundaries. Hooks intercept tool calls before execution and can block them with custom logic that is deterministically enforced.

**Source**: [GitHub Issue #6631](https://github.com/anthropics/claude-code/issues/6631), [GitHub Issue #6699](https://github.com/anthropics/claude-code/issues/6699)

### [NOVEL FIND] Behavioral Anti-Patterns from the Model Itself

- **No risk assessment**: Claude jumps to implementation, discovers problems mid-way, then patches reactively. Good engineers imagine failure first, then prevent it.
- **Overconfidence without calibration**: Says "the function returns X" with identical confidence whether it is certain or guessing.
- **Butterfly effect**: Misunderstands something early, builds an entire feature on faulty premises, nobody notices until five PRs deep.

**Mitigation**: Use Plan Mode to force exploration before implementation. Use subagents for independent review. Include explicit verification steps in every work order.

**Source**: [Claude Code Anti-Patterns Exposed - KDnuggets](https://ai-report.kdnuggets.com/p/claude-code-anti-patterns-exposed)

---

## Quick Reference: Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | Control auto-compaction trigger threshold (1-100) | ~90-95 |
| `DISABLE_AUTO_COMPACT` | Disable auto-compaction entirely | false |
| `MAX_THINKING_TOKENS` | Control extended thinking budget | ~32K |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Maximum response length | ~32K |
| `BASH_DEFAULT_TIMEOUT_MS` | Default bash command timeout | 120000 |
| `MAX_MCP_OUTPUT_TOKENS` | MCP response size limit | varies |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Enable agent teams/swarms | 0 (disabled) |
| `ENABLE_TOOL_SEARCH` | MCP tool lazy loading (85% context reduction) | varies |
| `DISABLE_PROMPT_CACHING` | Disable prompt caching | false |
| `CLAUDE_CODE_EFFORT_LEVEL` | Effort level: low, medium, high | high |
| `IS_SANDBOX` | Bypass security checks for VPS usage | false |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` | Override skill description context budget | 2% of window |
| `MCP_TIMEOUT` | MCP server connection timeout | varies |
| `MCP_TOOL_TIMEOUT` | MCP tool execution timeout | varies |

**Source**: [GitHub Issue #20244](https://github.com/anthropics/claude-code/issues/20244), [Debugging Claude Code - TurboAI.dev](https://www.turboai.dev/blog/debugging-claude-code-issues)

---

## Quick Reference: Essential Commands

| Command | Purpose |
|---------|---------|
| `/clear` | Reset context between tasks |
| `/compact [instructions]` | Manually compact with preservation guidance |
| `/context` | See what is consuming context (MCP, skills, etc.) |
| `/init` | Generate starter CLAUDE.md |
| `/hooks` | Configure automation hooks |
| `/sandbox` | Enable OS-level sandboxing |
| `/statusline` | Configure token usage monitoring |
| `/config` | Toggle auto-compact and other settings |
| `/rewind` or `Esc+Esc` | Restore previous checkpoint or selectively summarize |
| `/rename` | Name sessions for later resume |
| `Shift+Tab` | Cycle: Normal -> acceptEdits -> Plan Mode |
| `Ctrl+G` | Open plan in text editor for direct editing |
| `claude --continue` | Resume most recent session |
| `claude --resume` | Choose from recent sessions |
| `claude --worktree name` | Create isolated worktree session |
| `claude -p "prompt"` | Headless mode for scripts/CI |

---

## Quick Reference: Optimal Workflow

```
1. Start session
   - /clear if switching tasks
   - Shift+Tab twice (Plan Mode) for complex tasks
   - Scope the task narrowly in your prompt

2. Plan
   - Let Claude explore and plan
   - Ctrl+G to edit plan directly
   - Approve plan, switch to Normal Mode

3. Implement
   - Claude executes against plan
   - Shift+Tab once (acceptEdits) for faster flow
   - Delegate research to subagents to keep context clean

4. Verify
   - Always provide tests, screenshots, or expected outputs
   - Use subagents for independent review

5. At 70-80% context usage
   - Generate HANDOFF.md if task is incomplete
   - /compact with preservation instructions if continuing
   - /clear and restart with HANDOFF.md if context is cluttered

6. Commit
   - Let Claude write commit message and create PR
   - Use Writer/Reviewer pattern for quality
```

---

## Source Index

### Official Documentation
- [Best Practices - Claude Code Docs](https://code.claude.com/docs/en/best-practices)
- [Configure Permissions - Claude Code Docs](https://code.claude.com/docs/en/permissions)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
- [Automate Workflows with Hooks](https://code.claude.com/docs/en/hooks-guide)
- [Create Custom Subagents](https://code.claude.com/docs/en/sub-agents)
- [Slash Commands](https://code.claude.com/docs/en/slash-commands)
- [Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [Status Line Configuration](https://code.claude.com/docs/en/statusline)
- [Model Configuration](https://code.claude.com/docs/en/model-config)
- [Manage Costs](https://code.claude.com/docs/en/costs)
- [Compaction API](https://platform.claude.com/docs/en/build-with-claude/compaction)

### Creator Tips
- [Boris Cherny Tips on Threads](https://www.threads.com/@boris_cherny/post/DUMZr4VElyb)
- [10 Tips from Inside the Claude Code Team](https://paddo.dev/blog/claude-code-team-tips/)
- [How Boris Uses Claude Code](https://howborisusesclaudecode.com/)

### Community Resources
- [ykdojo/claude-code-tips (45 tips)](https://github.com/ykdojo/claude-code-tips)
- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [wshobson/commands (57 production-ready slash commands)](https://github.com/wshobson/commands)
- [claude-code-best-practice](https://github.com/shanraisshan/claude-code-best-practice)
- [Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3)

### Blogs and Guides
- [Writing a Good CLAUDE.md - HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [How I Use Every Claude Code Feature - Shrivu Shankar](https://blog.sshh.io/p/how-i-use-every-claude-code-feature)
- [Claude Code Gotchas - DoltHub](https://www.dolthub.com/blog/2025-06-30-claude-code-gotchas/)
- [Claude Saves Tokens, Forgets Everything](https://golev.com/post/claude-saves-tokens-forgets-everything/)
- [Beyond Permission Prompts - Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Claude Code Context Buffer Management](https://claudefa.st/blog/guide/mechanics/context-buffer-management)
- [Smart Handoff for Claude Code](https://blog.skinnyandbald.com/never-lose-your-flow-smart-handoff-for-claude-code/)
- [Claude Code Anti-Patterns Exposed - KDnuggets](https://ai-report.kdnuggets.com/p/claude-code-anti-patterns-exposed)
- [Claude Code Swarms - Addy Osmani](https://addyosmani.com/blog/claude-code-agent-teams/)

### GitHub Issues
- [Session Handoff Feature Request #11455](https://github.com/anthropics/claude-code/issues/11455)
- [Fork Context Feature Request #16153](https://github.com/anthropics/claude-code/issues/16153)
- [Undocumented Environment Variables #20244](https://github.com/anthropics/claude-code/issues/20244)
- [Disabling Auto-Compaction #24589](https://github.com/anthropics/claude-code/issues/24589)
- [Auto-Branch on Context Limit #25695](https://github.com/anthropics/claude-code/issues/25695)
- [Permission Deny Bug #6631](https://github.com/anthropics/claude-code/issues/6631)

### Tools
- [claude-code-handoff](https://github.com/Sonovore/claude-code-handoff)
- [Crystal - Parallel AI Sessions](https://github.com/stravu/crystal)
- [ccswitch - Multiple Sessions Without Conflicts](https://www.ksred.com/building-ccswitch-managing-multiple-claude-code-sessions-without-the-chaos/)
- [GitButler Hooks](https://blog.gitbutler.com/automate-your-ai-workflows-with-claude-code-hooks)
