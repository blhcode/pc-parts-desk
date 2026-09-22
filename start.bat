@echo off
REM PC Parts Desk — Windows launcher (calls PowerShell)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 pause
