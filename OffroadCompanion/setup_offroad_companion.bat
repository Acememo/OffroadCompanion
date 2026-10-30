@echo off
title Offroad Companion setup
rem One-time setup: BeamNG.Earth from source next to this folder, so its server can clear the course
rem (buildings, low bridges, walls) and grade the dirt track. Then use run_offroad_companion.bat instead of the .exe.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 setup_earth_source.py %*) || (python setup_earth_source.py %*)
pause
