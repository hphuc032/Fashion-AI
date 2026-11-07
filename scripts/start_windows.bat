@echo off
setlocal
if exist "%~dp0..\FashionAILocalizer.exe" (
  "%~dp0..\FashionAILocalizer.exe" %*
) else (
  powershell.exe -NoProfile -File "%~dp0start_windows.ps1" %*
)
exit /b %errorlevel%
