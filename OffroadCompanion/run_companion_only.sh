#!/usr/bin/env sh
# Starts the Offroad Companion helper program alone (127.0.0.1:47614). Keep it running while you play.
cd "$(dirname "$0")"
exec python3 earth_gpsd.py "$@"
