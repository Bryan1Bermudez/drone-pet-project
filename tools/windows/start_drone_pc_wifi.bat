@echo off
rem NOT the default. The PC's own Wi-Fi joins the drone (you leave home Wi-Fi).
rem The default is start_drone.bat: the phone joins the drone, the PC stays on home Wi-Fi.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0drone.ps1" %*
