@echo off
cd /d "E:\drone follower\turbodrone\backend"
start "Drone backend" cmd /k venv\Scripts\python -m uvicorn web_server:app
cd /d "E:\drone follower\turbodrone\frontend"
start "Drone frontend" cmd /k npm.cmd run dev
timeout /t 6 >nul
start http://localhost:5173
