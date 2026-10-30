@echo off
title Offroad Companion
rem Offroad Companion: BeamNG.Earth's world server with the course painter (the dirt track, terrain and cleared
rem course along the loaded course) and the Offroad Companion helper program, in this one window.
rem Use it instead of BeamNG.Earths run_server.bat. Keep this window open while you play.
rem (The helper's lines are marked [Offroad]: no need for run_companion_only.bat.)
rem First time, if BeamNG.Earth is not found: run_offroad_companion.bat --earth "C:\path\to\BeamNG.Earth"
rem The BeamNG.drive user folder chosen once is used from then on; to choose again: run_offroad_companion.bat --pick-user-dir
cd /d "%~dp0"
where py >nul 2>nul && (py -3 start_earth_with_tracks.py %*) || (python start_earth_with_tracks.py %*)
pause
