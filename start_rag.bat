@echo off
REM ============================================================================
REM HybridRAG v3 — Quick Launcher (start_rag.bat)
REM ============================================================================
REM Double-click this file to start HybridRAG.
REM Handles ExecutionPolicy bypass and dot-sourcing automatically.
REM This file MUST live in the HybridRAG3 root folder.
REM ============================================================================

REM "%~dp0" = the folder this .bat file is in (handles spaces in path)
cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -NoExit -Command "cd '%~dp0'; . .\start_hybridrag.ps1"
