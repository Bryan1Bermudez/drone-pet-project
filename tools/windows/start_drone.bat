@echo off
rem Double-click to fly: switches Wi-Fi to the drone, starts Turbodrone,
rem and switches back to home Wi-Fi when you press Enter in this window.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0drone.ps1" %*
