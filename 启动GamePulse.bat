@echo off
chcp 65001 >nul
title GamePulse Launcher
setlocal

set "GAMEPULSE_ROOT=%~dp0"
if "%GAMEPULSE_ROOT:~-1%"=="\" set "GAMEPULSE_ROOT=%GAMEPULSE_ROOT:~0,-1%"
set "VENV_DIR=%GAMEPULSE_ROOT%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "HOST=127.0.0.1"
set "PORT=8000"
set "FRONTEND_URL=http://127.0.0.1:8000/frontend/"

if not exist "%GAMEPULSE_ROOT%\main.py" (
  echo [ERROR] Cannot find GamePulse backend entry: %GAMEPULSE_ROOT%\main.py
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [INFO] Creating project virtual environment...
  py -3 -m venv "%VENV_DIR%" >nul 2>nul
  if errorlevel 1 (
    python -m venv "%VENV_DIR%"
  )
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment. Install Python 3 and retry.
    pause
    exit /b 1
  )
  echo [INFO] Installing backend requirements. This may take several minutes...
  "%PYTHON_EXE%" -m pip install --upgrade pip
  if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
  )
  "%PYTHON_EXE%" -m pip install -r "%GAMEPULSE_ROOT%\requirements_backend.txt"
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check network access and requirements_backend.txt.
    pause
    exit /b 1
  )
)

"%PYTHON_EXE%" -m pip check >nul 2>nul
if errorlevel 1 (
  echo [INFO] Repairing or installing missing backend dependencies...
  "%PYTHON_EXE%" -m pip install -r "%GAMEPULSE_ROOT%\requirements_backend.txt"
  if errorlevel 1 (
    echo [ERROR] Dependency repair failed. Check network access and requirements_backend.txt.
    pause
    exit /b 1
  )
)

cd /d "%GAMEPULSE_ROOT%"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "GAMEPULSE_ROOT=%GAMEPULSE_ROOT%"

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if %errorlevel%==0 (
  echo [INFO] Service already running on %HOST%:%PORT%.
  echo [INFO] Opening GamePulse page: %FRONTEND_URL%
  start "" "%FRONTEND_URL%"
  echo.
  echo If the page is not fresh, refresh the browser manually.
  pause
  exit /b 0
)

echo [INFO] Starting GamePulse backend...
echo [INFO] Project root: %GAMEPULSE_ROOT%
echo [INFO] Frontend URL: %FRONTEND_URL%
echo.
echo Keep this window open. Closing it will stop the backend service.
echo.

start "" cmd /c "timeout /t 3 /nobreak ^>nul ^& start "" "%FRONTEND_URL%""
"%PYTHON_EXE%" -m uvicorn main:app --host %HOST% --port %PORT%

echo.
echo [INFO] GamePulse backend stopped.
pause
endlocal
