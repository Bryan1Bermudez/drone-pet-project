@echo off
rem Test the follow software with the webcam. No drone, stays on home Wi-Fi.
rem Uses Turbodrone's Python (it already has OpenCV); falls back to python on PATH.
setlocal
set "HERE=%~dp0"
set "PY=python"
for %%I in ("%HERE%..\..\..\turbodrone\backend\venv\Scripts\python.exe") do if exist "%%~fI" set "PY=%%~fI"
if "%PY%"=="python" if exist "E:\drone follower\turbodrone\backend\venv\Scripts\python.exe" set "PY=E:\drone follower\turbodrone\backend\venv\Scripts\python.exe"
"%PY%" "%HERE%..\webcam_follow.py" %*
if errorlevel 1 pause
