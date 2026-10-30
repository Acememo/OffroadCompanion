"""BeamNG.Earth's world server with the GPS course painter (gpsd/earthpatch.py).

Run by start_earth_with_tracks.py in BeamNG.Earth's own Python (its .venv), in place of server/earthd.py, with the
same options. The server's worker processes are started with "spawn": each one imports this file again as its main
module, so the top level below (paths + the hook) runs in every one of them, and only the main process starts the
server.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EARTH_ROOT = os.environ.get("EARTHGPS_EARTH_ROOT") or os.getcwd()
SERVER = os.path.join(EARTH_ROOT, "server")
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)
if HERE not in sys.path:
    sys.path.append(HERE)            # after BeamNG.Earth's modules: only the gpsd package comes from here

try:
    from gpsd import earthpatch
    earthpatch.install()
except Exception as e:               # BeamNG.Earth runs as it is rather than not at all
    print(f"Offroad Companion: the course painter could not be installed ({type(e).__name__}: {e}); "
          "the server runs without it.", file=sys.stderr)

if __name__ == "__main__":
    import earthd
    sys.exit(earthd.main())
