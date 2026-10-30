#!/usr/bin/env sh
# One-time setup: BeamNG.Earth from source next to this folder (see setup_earth_source.py).
cd "$(dirname "$0")"
exec python3 setup_earth_source.py "$@"
