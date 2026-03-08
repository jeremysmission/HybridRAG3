# JCoder Monitoring

This is a read-only oversight workflow for `D:\JCoder`.

It does not edit or write inside the JCoder repo.

It does three things:
- inspects `git status` and current diffs in `D:\JCoder`
- stores snapshots under `D:\HybridRAG3\logs\jcoder_monitor\...`
- can enqueue a review/self-check prompt into the saved Claude JCoder session through the bridge
- can enqueue a workflow-policy prompt to tighten Claude's sprint execution discipline

## Files

- [tools/jcoder_monitor.ps1](/D:/HybridRAG3/tools/jcoder_monitor.ps1)
- [tools/jcoder_monitor.bat](/D:/HybridRAG3/tools/jcoder_monitor.bat)
- [tools/claude_bridge.ps1](/D:/HybridRAG3/tools/claude_bridge.ps1)

## Fast Start

Show current JCoder repo state:

```bat
cd /d D:\HybridRAG3
tools\jcoder_monitor.bat status
```

Write a full read-only snapshot:

```bat
cd /d D:\HybridRAG3
tools\jcoder_monitor.bat snapshot
```

Ask Claude in JCoder to self-review his current uncommitted changes:

```bat
cd /d D:\HybridRAG3
tools\jcoder_monitor.bat nudge
```

That `nudge` command:
- snapshots the current `D:\JCoder` state
- builds a concise review prompt from the changed file list
- enqueues it into the Claude bridge inbox

Send the standard workflow policy:

```bat
cd /d D:\HybridRAG3
tools\jcoder_monitor.bat policy
```

## Typical Workflow

1. Keep the bridge watcher running:

```bat
cd /d D:\HybridRAG3
tools\claude_bridge_watch.bat -ProjectRoot D:\JCoder
```

2. Check JCoder status:

```bat
tools\jcoder_monitor.bat status
```

3. If Claude has a lot of uncommitted changes, ask for a self-review:

```bat
tools\jcoder_monitor.bat nudge
```

3a. If Claude starts drifting into too many background jobs or low-signal narration, re-send the workflow policy:

```bat
tools\jcoder_monitor.bat policy
```

4. Inspect Claude's reply in:

- `%USERPROFILE%\.ai_handoff\claude_bridge\outbox`
- [logs/claude_bridge/JCoder/runs](/D:/HybridRAG3/logs/claude_bridge/JCoder/runs)

## Custom Prompt

You can override the default nudge:

```bat
tools\jcoder_monitor.bat nudge -Prompt "Review the current JCoder changes for timeout bugs and path handling regressions. Do not edit yet."
```

## Snapshot Contents

Each snapshot folder contains:
- `summary.json`
- `status_short.txt`
- `diff_stat.txt`
- `diff_names.txt`
- `staged_names.txt`
- `untracked.txt`
- `diff.patch`
- `diff_staged.patch`

## Important Constraint

This tooling is for monitoring and prompting only.

It does not write into `D:\JCoder`, and it should stay that way while another agent is actively editing there.

## References

- `docs/03_guides/AUTOTUNE_CHEAT_SHEET.md` — definitive cheat sheet for the March 6–7 autotune winners (offline/online configs, pass rates, latencies, and log references). Include this in any GUI “refs” section so operators can hard-code the tuned metrics.
- `logs/tunelogs/autotune_runs.zip` — raw leaderboard/candidate artifacts for both modes; expand and inspect `*/scored/summary.json` or `*/candidate_config.json` if you need to troubleshoot a tune run.
