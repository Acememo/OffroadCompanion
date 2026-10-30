#!/usr/bin/env python3
"""Start BeamNG.Earth's world server with the GPS course painter: dirt tracks along the loaded race course where no
road runs (gpsd/courseroads.py). Use it instead of BeamNG.Earth's run_server, the same way; everything else is
BeamNG.Earth's own start.py (its Python, its recommended options, its mod update).

    python start_earth_with_tracks.py [--earth PATH-TO-BeamNG.Earth] [--no-gps] [--pick-user-dir] [start.py options]
                                      [-- earthd options]
    (--pick-user-dir: choose the BeamNG.drive user folder again instead of the one chosen before)

The BeamNG.Earth folder is found when this folder is inside it or next to it, and remembered; --earth sets it.
The Offroad Companion (earth_gpsd.py, what run_companion_only starts) runs in this same window, its lines marked [Offroad], and stops
with the server; unless one is running already, or --no-gps.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gpsd import beamngdirs, paintfile  # noqa: E402

CONFIG = os.path.join(paintfile.base_dir(), "launcher.json")


def is_earth(path):
    return bool(path) and os.path.isfile(os.path.join(path, "start.py")) and \
        os.path.isfile(os.path.join(path, "server", "earthd.py"))


def find_earth():
    cfg = paintfile.read_json(CONFIG) or {}
    if is_earth(cfg.get("earth")):
        return cfg["earth"]
    for here in (os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))):    # unzipped inside BeamNG.Earth
        if is_earth(here):
            return here
    seen = set()
    for root in (os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE)), os.path.expanduser("~"),
                 os.path.join(os.path.expanduser("~"), "Downloads"), os.path.join(os.path.expanduser("~"), "Documents"),
                 os.path.join(os.path.expanduser("~"), "Desktop")):
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            if p in seen or "earth" not in n.lower():
                continue
            seen.add(p)
            if is_earth(p):
                return p
            for sub in sorted(os.listdir(p)) if os.path.isdir(p) else []:      # an unzipped release's folder
                q = os.path.join(p, sub)
                if is_earth(q):
                    return q
    return None


def companion_running(port=47614):
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def start_companion():
    """The Offroad Companion as a child of this window (one window for both; the user, 2026-10-22: "so I don't have to open
    two CMDs"): stopped when the server stops (or with Ctrl+C, which reaches both). None when one already runs."""
    import atexit
    import subprocess
    if companion_running():
        print("Offroad Companion: the Offroad Companion is already running (its own window): using that one")
        return None
    try:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "earth_gpsd.py"), "--log-prefix", "Offroad"], cwd=HERE)
    except OSError as e:
        print(f"Offroad Companion: the Offroad Companion did not start ({e}): run run_companion_only instead")
        return None

    def stop():
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
    atexit.register(stop)
    print("Offroad Companion: the Offroad Companion runs in this window too (its lines start with [Offroad])")
    return p


def main():
    argv = sys.argv[1:]
    gps = "--no-gps" not in argv
    argv = [a for a in argv if a != "--no-gps"]
    pick_again = "--pick-user-dir" in argv            # (the user folder asked again, not the one chosen before)
    if pick_again:
        argv.remove("--pick-user-dir")
    try:                                            # (the folder of before 1.2.0, "companion": its tracks brought over)
        import setup_earth_source
        n, aside = setup_earth_source.migrate_old_folder(HERE)
        if aside:
            print(f"Offroad Companion: the old companion folder renamed to {os.path.basename(aside)}"
                  + (f" ({n} of your tracks copied here)" if n else "") + "; delete it when you like")
    except Exception as e:
        print(f"  (the old companion folder left as it is: {e})")
    earth = None
    if "--earth" in argv:
        i = argv.index("--earth")
        if i + 1 >= len(argv):
            sys.exit("--earth needs the BeamNG.Earth folder")
        earth = os.path.abspath(os.path.expanduser(argv[i + 1]))
        del argv[i:i + 2]
    earth = earth or find_earth()
    if not is_earth(earth):
        sys.exit("BeamNG.Earth was not found. Run again with its folder:\n"
                 "    python start_earth_with_tracks.py --earth \"C:\\path\\to\\BeamNG.Earth\"")
    cfg = paintfile.read_json(CONFIG) or {}
    # the game's user folder: BeamNG.Earth's start.py only knows AppData's (and its own config); the one the game
    # really uses goes to it (a user folder moved to another drive in the game's launcher)
    own = argv[:argv.index("--")] if "--" in argv else argv
    if "--user-dir" in own:
        i = argv.index("--user-dir")
        user_dir = beamngdirs.as_current(argv[i + 1]) if i + 1 < len(argv) else None
    else:
        user_dir = beamngdirs.find(cfg.get("user_dir"), earth, pick_again=pick_again)
        if user_dir:
            argv = ["--user-dir", user_dir] + argv
    cfg.update({"earth": earth, "user_dir": user_dir or cfg.get("user_dir")})
    try:
        paintfile.write_json(CONFIG, cfg)
    except OSError:
        pass
    if user_dir:
        try:
            import setup_earth_source
            setup_earth_source.install_gps_mod(user_dir)        # (the Offroad Companion mod kept up to date like BeamNG.Earth's)
        except Exception as e:
            print(f"  (Offroad Companion mod not copied: {e})")
    if gps:
        start_companion()
    print(f"Offroad Companion: starting BeamNG.Earth from {earth} with the course painter")
    os.environ["EARTHGPS_EARTH_ROOT"] = earth
    sys.path.insert(0, earth)
    os.chdir(earth)
    import start                                    # BeamNG.Earth's own launcher
    start.EARTHD = os.path.join(HERE, "earth_tracks_server.py")
    sys.argv = [os.path.join(earth, "start.py")] + argv
    start.main()


if __name__ == "__main__":
    main()
