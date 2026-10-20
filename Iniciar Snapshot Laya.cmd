@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if defined SNAPSHOT_LAYA_PYTHON (
  "%SNAPSHOT_LAYA_PYTHON%" launch.py
) else (
  if exist "%USERPROFILE%\Documents\Codex\Laya\.venv\Scripts\python.exe" (
    "%USERPROFILE%\Documents\Codex\Laya\.venv\Scripts\python.exe" launch.py
  ) else (
    python launch.py
  )
)
if errorlevel 1 pause
