@echo off
setlocal

cd /d "%~dp0\.."

set "BACKEND_PY=%CD%\backend\.venv\Scripts\python.exe"
set "BACKEND_PORT=5018"

if not exist "%BACKEND_PY%" (
  echo [COGENT] Missing backend environment: "%BACKEND_PY%"
  exit /b 1
)

echo [COGENT] Backend starting on http://127.0.0.1:%BACKEND_PORT%/
"%BACKEND_PY%" -m uvicorn main:app --app-dir "%CD%\backend" --port %BACKEND_PORT%
