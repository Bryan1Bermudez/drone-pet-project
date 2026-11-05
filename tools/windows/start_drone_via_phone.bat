@echo off
rem Fly through the phone: phone on the drone's Wi-Fi, PC stays on home Wi-Fi,
rem PC reaches the drone over the USB cable. See phone_relay.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0phone_relay.ps1" %*
