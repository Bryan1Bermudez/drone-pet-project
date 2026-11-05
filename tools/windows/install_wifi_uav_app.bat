@echo off
rem Opens the Play Store on a virtual phone screen (scrcpy --new-display), so the
rem phone's broken inner screen does not matter. Search "WiFi UAV" (developer
rem LcForever, package com.lcfld.fldpublic) and click Install.
rem Needs: phone plugged in, "adb devices" showing "device", scrcpy installed.
where adb >nul 2>nul || (echo adb not found. Run: winget install Genymobile.scrcpy  then open a new window. & pause & exit /b 1)
adb get-state 1>nul 2>nul || (echo Phone not found. Plug it in and check "adb devices". & pause & exit /b 1)
echo In the scrcpy window: search "WiFi UAV" (by LcForever) and click Install. Close it when done.
scrcpy --new-display=1080x1920 --start-app=com.android.vending
