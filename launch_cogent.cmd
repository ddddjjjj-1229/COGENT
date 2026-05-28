@echo off
setlocal

cd /d "%~dp0"

set "BACKEND_PY=%CD%\backend\.venv\Scripts\python.exe"
set "FRONTEND_PY=%CD%\frontend\.venv\Scripts\python.exe"
set "BACKEND_PORT=5018"
set "FRONTEND_PORT=8518"

if not exist "%BACKEND_PY%" (
  echo [COGENT] Missing backend environment: "%BACKEND_PY%"
  echo Create or restore backend\.venv before launching.
  pause
  exit /b 1
)

if not exist "%FRONTEND_PY%" (
  echo [COGENT] Missing frontend environment: "%FRONTEND_PY%"
  echo Create or restore frontend\.venv before launching.
  pause
  exit /b 1
)

echo [COGENT] Starting backend on http://127.0.0.1:%BACKEND_PORT%/
start "COGENT Backend" cmd /k ""%BACKEND_PY%" -m uvicorn main:app --app-dir "%CD%\backend" --port %BACKEND_PORT%"

echo [COGENT] Starting frontend on http://127.0.0.1:%FRONTEND_PORT%/
start "COGENT Frontend" cmd /k ""%FRONTEND_PY%" -m streamlit run "%CD%\frontend\main.py" --server.port %FRONTEND_PORT%"

timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:%FRONTEND_PORT%"

echo [COGENT] Launch requested. If the page does not open, wait a few seconds and refresh.
