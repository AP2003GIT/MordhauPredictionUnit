@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% neq 0 (
  echo Mordhau Prediction Unit failed to start. Check the message above.
) else (
  echo Mordhau Prediction Unit is running.
  echo Dashboard: http://127.0.0.1:5173/
)
echo.
pause
exit /b %EXIT_CODE%

