# Multi-Agent Handoff Protocol

## Shared Handoff Directory
C:\Users\jerem\.ai_handoff\

## Files
- claude_to_codex.md -- Claude Code writes findings/context for Codex
- ai_handoff.md -- Codex writes findings/context for Claude Code

## Protocol
1. Before starting work, check the handoff dir for messages from the other agent
2. After completing work, write your findings to your outbound file
3. Include: timestamp, session ID, what you changed, test results, open items
4. LimitlessApp V2 ingests both for institutional memory

## Rules
- Never delete the other agent's file -- only read it
- Append or overwrite your own file only
- Keep files under 200 lines (same as MEMORY.md limit)
