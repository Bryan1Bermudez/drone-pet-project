@echo off
rem Fly through the phone: the phone joins the drone's Wi-Fi, the PC stays on home
rem Wi-Fi and reaches the drone over the USB cable. See phone_relay.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0phone_relay.ps1" %*
