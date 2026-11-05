@echo off
setlocal
rem One-time setup: patch Turbodrone for the Contixo F19 and write its settings.
rem Usage: install.bat            (Turbodrone next to this repo, or E:\drone follower\turbodrone)
rem        install.bat "D:\path\to\turbodrone"

set "HERE=%~dp0"
set "TURBO=%~1"
if "%TURBO%"=="" for %%I in ("%HERE%..\..\..\turbodrone") do set "TURBO=%%~fI"
if not exist "%TURBO%\backend\web_server.py" set "TURBO=E:\drone follower\turbodrone"
if not exist "%TURBO%\backend\web_server.py" (
  echo Could not find Turbodrone. Run:  install.bat "path\to\turbodrone"
  pause
  exit /b 1
)
echo Using Turbodrone at: %TURBO%

if not exist "%TURBO%\backend\venv\Scripts\python.exe" (
  echo Turbodrone's Python environment is missing. In PowerShell run:
  echo   cd "%TURBO%\backend"; python -m venv venv; .\venv\Scripts\python -m pip install -r requirements.txt windows-curses
  pause
  exit /b 1
)

"%TURBO%\backend\venv\Scripts\python.exe" "%HERE%patch_turbodrone.py" "%TURBO%"
if errorlevel 1 (
  echo Patch failed, see the messages above.
  pause
  exit /b 1
)

copy /y "%HERE%turbodrone.env" "%TURBO%\backend\.env" >nul
echo Wrote drone settings to %TURBO%\backend\.env

echo Installing web page packages (needs internet)...
pushd "%TURBO%\frontend"
call npm.cmd install --no-audit --no-fund
popd

echo.
echo Setup done. From now on just double-click start_drone.bat in this folder.
pause
