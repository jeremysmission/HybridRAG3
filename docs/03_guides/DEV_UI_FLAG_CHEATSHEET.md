# Development UI Flag Cheat Sheet

Use this to control whether Development-only controls are visible in the GUI.

## What This Flag Does

- `HYBRIDRAG_DEV_UI=1`: Show Development-only UI controls
- `HYBRIDRAG_DEV_UI=0`: Hide Development-only UI controls (production-style view)

## PowerShell (Current Session Only)

Set Dev UI ON:

```powershell
$env:HYBRIDRAG_DEV_UI="1"
```

Set Dev UI OFF:

```powershell
$env:HYBRIDRAG_DEV_UI="0"
```

Check current value:

```powershell
echo $env:HYBRIDRAG_DEV_UI
```

Note: Session-only values reset when you close PowerShell.

## PowerShell (Persist Across Reboots)

Set persistent Dev UI ON:

```powershell
setx HYBRIDRAG_DEV_UI "1"
```

Set persistent Dev UI OFF:

```powershell
setx HYBRIDRAG_DEV_UI "0"
```

After using `setx`, close and reopen PowerShell before launching the app.

## Recommended Workflow

1. During active bug fixing/tuning: set `HYBRIDRAG_DEV_UI=1`
2. Before demo/production run: set `HYBRIDRAG_DEV_UI=0`
3. Relaunch GUI after switching

## Quick Launch Example

```powershell
$env:HYBRIDRAG_DEV_UI="1"
.\start_gui.bat
```

