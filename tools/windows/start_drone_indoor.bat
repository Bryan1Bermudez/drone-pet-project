@echo off
rem Same as start_drone.bat (through the phone) but for small rooms:
rem Low speed, gentle sticks, slow climbs.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0phone_relay.ps1" -Indoor %*
