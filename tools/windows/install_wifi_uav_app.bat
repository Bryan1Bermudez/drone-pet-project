@echo off
rem Opens the WiFi UAV app (com.lcfld.fldpublic) in the phone's Play Store and shows
rem the phone screen with scrcpy, so you can tap Install from the PC.
rem Needs: phone plugged in, "adb devices" showing "device", scrcpy installed.
where adb >nul 2>nul || (echo adb not found. Run: winget install Genymobile.scrcpy  then open a new window. & pause & exit /b 1)
adb get-state 1>nul 2>nul || (echo Phone not found. Plug it in and check "adb devices". & pause & exit /b 1)
adb shell am start -a android.intent.action.VIEW -d "market://details?id=com.lcfld.fldpublic"
echo In the scrcpy window: tap Install. Close scrcpy when done.
scrcpy
