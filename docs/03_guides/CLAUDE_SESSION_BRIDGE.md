# Claude Session Bridge

This bridge gives you a scriptable path into a saved Claude CLI project session without trying to scrape the interactive terminal UI.

It uses:
- `claude --print`
- `--session-id` for the first message
- `--resume <session_id>` for follow-up messages

That means you can keep one long-lived Claude session for a repo and drive it with simple batch files or a watched inbox folder.

Important:
- the Claude session should be rooted to the repo Claude is actually working in
- the bridge files do not need to live in that repo
- use `-ProjectRoot D:\JCoder` if Claude is working there and you want to avoid editing that repo

## Files

- [tools/claude_bridge.ps1](/D:/HybridRAG3/tools/claude_bridge.ps1)
- [tools/claude_bridge.bat](/D:/HybridRAG3/tools/claude_bridge.bat)
- [tools/claude_bridge_init.bat](/D:/HybridRAG3/tools/claude_bridge_init.bat)
- [tools/claude_bridge_send.bat](/D:/HybridRAG3/tools/claude_bridge_send.bat)
- [tools/claude_bridge_watch.bat](/D:/HybridRAG3/tools/claude_bridge_watch.bat)
- [tools/claude_bridge_status.bat](/D:/HybridRAG3/tools/claude_bridge_status.bat)

## What It Does

- Stores bridge state in `logs\claude_bridge\state.json`
- Stores each request/response run in `logs\claude_bridge\runs\...`
- Can watch a queue folder, process JSON requests, and emit JSON responses
- Supports `-DryRun` so you can validate the command path without making a live model call

## Default Paths

- State file: `logs\claude_bridge\<project_name>\state.json`
- Queue root: `%USERPROFILE%\.ai_handoff\claude_bridge`
- Inbox: `%USERPROFILE%\.ai_handoff\claude_bridge\inbox`
- Outbox: `%USERPROFILE%\.ai_handoff\claude_bridge\outbox`

## Fast Start

From the repo root in `cmd.exe`:

```bat
tools\claude_bridge_init.bat
tools\claude_bridge_status.bat
tools\claude_bridge_send.bat -Prompt "Read HANDOFF.md and summarize the current blockers." -DryRun
```

Target a different repo without copying bridge files there:

```bat
tools\claude_bridge_init.bat -ProjectRoot D:\JCoder
tools\claude_bridge_status.bat -ProjectRoot D:\JCoder
tools\claude_bridge_send.bat -ProjectRoot D:\JCoder -Prompt "Read HANDOFF.md and summarize the current blockers." -DryRun
```

If the dry run looks right, remove `-DryRun`:

```bat
tools\claude_bridge_send.bat -Prompt "Read HANDOFF.md and summarize the current blockers."
```

## Queue Mode

Start the watcher in one terminal:

```bat
tools\claude_bridge_watch.bat
```

Drop a request into the inbox from another terminal:

```bat
tools\claude_bridge.bat enqueue -Prompt "Review the latest patch and list the top 3 risks."
```

The watcher will:
- read `inbox\*.json`
- send the prompt into the saved Claude session
- write a response JSON file into `outbox\`
- archive the processed request

## Useful Commands

Initialize or replace the saved session id:

```bat
tools\claude_bridge_init.bat
tools\claude_bridge_init.bat -ForceNewSession
```

Show current bridge status:

```bat
tools\claude_bridge_status.bat
```

Send a prompt file:

```bat
tools\claude_bridge_send.bat -PromptFile C:\path\to\prompt.txt
```

Print the last response:

```bat
tools\claude_bridge.bat tail
```

Reset only the saved bridge state:

```bat
tools\claude_bridge.bat reset
```

## Recommended Usage Pattern

For a stable cross-agent loop:

1. Start one watcher:

```bat
tools\claude_bridge_watch.bat
```

2. Keep queue traffic short and explicit.

Good:
- one task per request
- point at exact files
- ask for structured answers

Bad:
- broad conversational prompts
- giant pasted logs without a question

3. Use a repo handoff file for long context, then send short prompts like:

```text
Read docs/HANDOFF.md and continue from the open items.
```

## Limitations

- This does not type into Claude's live TUI window.
- It drives the saved session through the headless CLI path instead.
- If Claude needs permissions for a tool call, your session settings still matter.
- For unattended automation, configure Claude permissions and hooks appropriately.

## Good Next Step

If you want this fully hands-off later, add a Claude hook or project settings profile so the bridged session has deterministic tool rules instead of pausing for prompts.
