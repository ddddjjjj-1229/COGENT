@echo off
setlocal

cd /d "%~dp0\.."

set "FRONTEND_PY=%CD%\frontend\.venv\Scripts\python.exe"
set "FRONTEND_PORT=8518"

if not exist "%FRONTEND_PY%" (
  echo [COGENT] Missing frontend environment: "%FRONTEND_PY%"
  exit /b 1
)

echo [COGENT] Frontend starting on http://127.0.0.1:%FRONTEND_PORT%/
"%FRONTEND_PY%" -m streamlit run "%CD%\frontend\main.py" --server.port %FRONTEND_PORT%
