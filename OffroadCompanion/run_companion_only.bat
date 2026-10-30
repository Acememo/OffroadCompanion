@echo off
title Offroad Companion (helper only)
rem Starts the Offroad Companion helper program alone (127.0.0.1:47614). Keep this window open while you play.
rem Only needed without run_offroad_companion.bat (with BeamNG.Earth's own .exe / run_server): that one starts it too.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 earth_gpsd.py %*) || (python earth_gpsd.py %*)
pause
