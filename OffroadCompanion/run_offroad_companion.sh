#!/usr/bin/env sh
# Offroad Companion: BeamNG.Earth's world server with the course painter and the helper program, in one terminal.
# Use it instead of BeamNG.Earth's run_server.sh. Add --earth /path/to/BeamNG.Earth the first time if it is not found.
cd "$(dirname "$0")"
exec python3 start_earth_with_tracks.py "$@"
