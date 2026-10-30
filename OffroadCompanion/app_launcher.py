#!/usr/bin/env python3
"""Offroad Companion as one program: OffroadCompanion-<version>.exe (the user, 2026-10-26: "Can we make it all an exe
like BeamNG.Earth? some friends are struggling installing python and all those steps").

The .exe is BeamNG.Earth's own launcher (its launcher.py, the same that makes BeamNG.Earth's .exe) with BeamNG.Earth's
server, its mod, Python and Offroad Companion inside (tools/build_exe.py). Double-clicked, it:

  1. finds the BeamNG.drive user folder the game really uses (also one moved out of AppData; asked once when it can't
     tell, then remembered),
  2. puts Offroad Companion's mod into the game's mods folder (BeamNG.Earth's launcher puts BeamNG.Earth's there),
  3. runs Offroad Companion's helper (the courses, the routes: earth_gpsd.py) in this window, its lines marked
     [Offroad],
  4. hands over to BeamNG.Earth's launcher: it starts BeamNG.Earth's world server (itself again, with --server), with
     the course painter installed in it and in its worker processes (gpsd/earthpatch.py: the dirt track, the track
     terrain, the cleared course), then BeamNG.drive through Steam and BeamMP when it is set up, and stops it all when
     the game closes (GAME_GONE_S_WIN after it). The server and BeamMP end with this program however it ends (its
     window closed: KillGroup), and a BeamMP left over from an earlier start is closed first.

Nothing to install: no Python, no BeamNG.Earth source folder, no setup step. The BeamNG.Earth inside is the version
this release was made and tested with (setup_earth_source.EARTH_VERSION); its in-game update notice is turned off (an
update of BeamNG.Earth comes with the next Offroad Companion). Its map cache and settings are BeamNG.Earth's own, shared
with BeamNG.Earth's .exe.

    OffroadCompanion.exe                     everything
    OffroadCompanion.exe --pick-user-dir     choose the BeamNG.drive user folder again
    OffroadCompanion.exe --pick-data-dir     choose again where the map downloads and Offroad Companion's data go
    OffroadCompanion.exe --no-game           only the servers (start the game yourself)
    OffroadCompanion.exe --companion         only Offroad Companion's helper (with BeamNG.Earth's own .exe)
    OffroadCompanion.exe --selftest          check the course painter gets into the server's processes
    (any of BeamNG.Earth's launcher options: --cache-dir, --game-dir, --no-beammp, ... and -- server options)

From source (for testing): python app_launcher.py --earth PATH-TO-BeamNG.Earth [...].
"""
import importlib
import multiprocessing
import os
import shutil
import sys
import threading

FROZEN = getattr(sys, "frozen", False)
BUNDLE = getattr(sys, "_MEIPASS", None)
# Offroad Companion's own files: a folder of the bundle (its sources as they are, so the painter's code fingerprint,
# earthpatch.gps_code_id, is the same as a source install's: the same ground code), or this folder
HERE = os.path.join(BUNDLE, "OffroadCompanion") if BUNDLE else os.path.dirname(os.path.abspath(__file__))
PAINTER_ENV = "OFFROAD_COMPANION_PAINTER"       # set in the server: its worker processes install the painter too
EARTH_ENV = "EARTHGPS_EARTH_ROOT"
SERVER_OPTIONS = ["--update-check", "off"]      # (BeamNG.Earth's update notice: it comes with Offroad Companion)


def earth_root():
    """BeamNG.Earth's files: the bundle, or (from source) --earth / EARTHGPS_EARTH_ROOT."""
    if BUNDLE:
        return BUNDLE
    if "--earth" in sys.argv:
        i = sys.argv.index("--earth")
        if i + 1 < len(sys.argv):
            os.environ[EARTH_ENV] = os.path.abspath(os.path.expanduser(sys.argv[i + 1]))
            del sys.argv[i:i + 2]
    return os.environ.get(EARTH_ENV)


def set_paths(earth):
    """Imports: BeamNG.Earth's launcher and server (frozen in the .exe, from its folder in source), then ours."""
    if earth and not BUNDLE:
        for p in (os.path.join(earth, "server"), earth):
            if p not in sys.path:
                sys.path.insert(0, p)
    if HERE not in sys.path:
        sys.path.append(HERE)


def ours(name):
    """One of Offroad Companion's modules (imported by name: the .exe carries them as plain files, not frozen)."""
    return importlib.import_module(name)


def install_painter(earth):
    """The course painter in BeamNG.Earth's server (earth_tracks_server.py's job in a source install)."""
    os.environ[PAINTER_ENV] = "1"
    if earth:
        os.environ.setdefault(EARTH_ENV, earth)
    set_paths(earth)
    try:
        ours("gpsd.earthpatch").install()
    except Exception as e:               # BeamNG.Earth runs as it is rather than not at all
        print(f"Offroad Companion: the course painter could not be installed ({type(e).__name__}: {e}); "
              "the server runs without it.", file=sys.stderr, flush=True)


# The server (--server) and every worker process it starts (multiprocessing's spawn runs this file's top again, before
# freeze_support takes over): the painter in place before BeamNG.Earth's modules are used.
if os.environ.get(PAINTER_ENV) == "1" or sys.argv[1:2] == ["--server"]:
    install_painter(earth_root())


# --- the helper ---------------------------------------------------------------------------------------------------

def data_dir():
    return ours("gpsd.paintfile").base_dir()


def tracks_dir():
    """The player's tracks (course files of their own): in Offroad Companion's data folder. The first time, the tracks
    of a source install (the folder remembered in launcher.json) are copied over, and the folder's README."""
    d = os.path.join(data_dir(), "tracks")
    os.makedirs(d, exist_ok=True)
    readme = os.path.join(HERE, "tracks", "README.txt")
    if os.path.isfile(readme) and not os.path.exists(os.path.join(d, "README.txt")):
        shutil.copy2(readme, d)
    if BUNDLE:
        cfg = ours("gpsd.paintfile").read_json(os.path.join(data_dir(), "launcher.json")) or {}
        earth = cfg.get("earth")
        old = os.path.join(earth, "OffroadCompanion", "tracks") if isinstance(earth, str) else None
        if old and os.path.isdir(old) and os.path.normcase(old) != os.path.normcase(d):
            n = 0
            for fn in os.listdir(old):
                a, b = os.path.join(old, fn), os.path.join(d, fn)
                if os.path.isfile(a) and fn != "README.txt" and not os.path.exists(b):
                    shutil.copy2(a, b)
                    n += 1
            if n:
                print(f"  Offroad Companion: {n} of your tracks copied from {old}", flush=True)
    return d


def helper_args():
    return ["--log-prefix", "Offroad", "--tracks-dir", tracks_dir(), "--cache-dir", os.path.join(data_dir(), "cache")]


def helper_running(port=47614):
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def start_helper():
    """Offroad Companion's helper in this process (a thread): it ends with the launcher. None when one already runs."""
    if helper_running():
        print("  Offroad Companion: its helper is already running (another window): using that one", flush=True)
        return None
    gpsd_main = ours("earth_gpsd").main
    args = helper_args()
    t = threading.Thread(target=gpsd_main, args=(args,), name="offroad-helper", daemon=True)
    t.start()
    return t


# --- closing neatly ----------------------------------------------------------------------------------------------
# (the user, 2026-10-28: "it's not closing beamMP when I close beamNG and also close the offroad companion window ...
# Can we check everything closes neatly after closing beam? like beamMP does it"). BeamNG.Earth's launcher stops the
# world server and the BeamMP launcher it started once the game has been gone GAME_GONE_S, but only when it gets to:
# a window closed before that (its X) ended it at once and left both running, and the next start then used that BeamMP
# ("BeamMP is already running"), whose session lost its player list and ping ("No players... something is wrong").

GAME_GONE_S_WIN = 10        # the game gone this long (Windows: its process, reliably seen): everything stops


class KillGroup:
    """Windows: a job object that ends the processes put in it (and every process they start) when this program ends,
    however it ends: its window closed, killed in the task manager, an error. The game is never put in it."""

    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
            k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            k32.CloseHandle.argtypes = (wintypes.HANDLE,)

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class IO(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

            class EXTENDED(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO),
                            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
            h = k32.CreateJobObjectW(None, None)
            if not h:
                return
            info = EXTENDED()
            info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):  # (Extended...)
                k32.CloseHandle(h)
                return
            self.k32, self.handle = k32, h          # (kept open for this program's life: closing it ends them)
        except Exception:
            self.handle = None

    def add(self, pid):
        """Process pid in the group (with the processes it starts from now on). True when it is."""
        if not self.handle or not pid:
            return False
        h = self.k32.OpenProcess(0x0100 | 0x0001, False, int(pid))     # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if not h:
            return False
        try:
            return bool(self.k32.AssignProcessToJobObject(self.handle, h))
        finally:
            self.k32.CloseHandle(h)


GROUP = None


def keep_together(launcher):
    """BeamNG.Earth's world server and the BeamMP launcher it starts put in this program's KillGroup: they end with
    it. The game (started through Steam) is not."""
    global GROUP
    GROUP = KillGroup()
    import bmplaunch
    orig_server, orig_beammp = launcher.start_server, bmplaunch.start

    def start_server(*a, **kw):
        p = orig_server(*a, **kw)
        GROUP.add(p.pid)
        return p

    def start_beammp(*a, **kw):
        p = orig_beammp(*a, **kw)
        GROUP.add(p.pid)
        return p
    launcher.start_server, bmplaunch.start = start_server, start_beammp
    if os.name == "nt":
        launcher.GAME_GONE_S = min(launcher.GAME_GONE_S, GAME_GONE_S_WIN)


def beammp_leftovers(exe_name=None, run=None):
    """[(pid, command line)] of BeamMP launchers started for a game by this program or BeamNG.Earth's (--no-launch:
    the game is started separately) that are still running. Windows; [] when it can't tell."""
    if os.name != "nt" and run is None:
        return []
    import subprocess
    exe_name = exe_name or "BeamMP-Launcher.exe"
    run = run or subprocess.run
    ps = (f"Get-CimInstance Win32_Process -Filter \"Name='{exe_name}'\" | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        r = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    out = []
    for line in (r.stdout or b"").decode("utf-8", "replace").splitlines():
        pid, _, cmd = line.strip().partition("\t")
        if pid.isdigit() and "--no-launch" in cmd:
            out.append((int(pid), cmd))
    return out


def close_leftovers(launcher):
    """Before starting: a BeamMP launcher left from an earlier start (its window closed before it could stop it)
    stopped, when the game isn't running (it waits for a game that is gone; a new one is started for this one)."""
    if os.name != "nt":
        return 0
    try:
        if launcher.game_pids():
            return 0
        import bmplaunch
        import subprocess
        left = beammp_leftovers(getattr(bmplaunch, "EXE", None))
        for pid, _cmd in left:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if left:
            print(f"  Multiplayer   closed a BeamMP launcher left over from an earlier start", flush=True)
        return len(left)
    except Exception:
        return 0


# --- the launcher ---------------------------------------------------------------------------------------------------

OWN_OPTIONS = ("--pick-user-dir", "--pick-data-dir", "--no-companion")


def split_args(argv):
    """(our options, BeamNG.Earth launcher's arguments): ours are taken out wherever they are before '--'."""
    cut = argv.index("--") if "--" in argv else len(argv)
    mine = [a for a in argv[:cut] if a in OWN_OPTIONS]
    rest = [a for a in argv[:cut] if a not in OWN_OPTIONS] + argv[cut:]
    return mine, rest


def with_server_options(rest):
    """BeamNG.Earth launcher's arguments with SERVER_OPTIONS added after '--' (the server's own options)."""
    if "--" in rest:
        i = rest.index("--")
        return rest[:i + 1] + SERVER_OPTIONS + rest[i + 1:]
    return rest + ["--"] + SERVER_OPTIONS


def user_folder(rest, pick_again):
    """The BeamNG.drive user folder: given (--user-dir), remembered, or found (asked when it can't tell)."""
    beamngdirs = ours("gpsd.beamngdirs")
    paintfile = ours("gpsd.paintfile")
    cut = rest.index("--") if "--" in rest else len(rest)
    if "--user-dir" in rest[:cut]:
        i = rest.index("--user-dir")
        return beamngdirs.as_current(rest[i + 1]) if i + 1 < len(rest) else None
    cfg_path = os.path.join(paintfile.base_dir(), "launcher.json")
    cfg = paintfile.read_json(cfg_path) or {}
    d = beamngdirs.find(cfg.get("user_dir"), None, pick_again=pick_again, out=lambda m: print("  " + m, flush=True))
    if d:
        cfg["user_dir"] = d
        try:
            paintfile.write_json(cfg_path, cfg)
        except OSError:
            pass
    return d


def data_folder(launcher, pick_again=False):
    """Where the map downloads and Offroad Companion's data go (gpsd/datadir.py: asked at the first start, remembered),
    for this program and everything it starts (EARTHGPS_DIR; BeamNG.Earth's cache: its own remembered folder)."""
    if os.environ.get("EARTHGPS_DIR"):          # (given: tests, a developer's own folder)
        return os.environ["EARTHGPS_DIR"]
    try:
        import apppaths                         # BeamNG.Earth's (its folder window, its remembered cache folder)
    except ImportError:
        apppaths = None
    busy = helper_running()
    try:
        busy = busy or bool(launcher.server_port_busy())
    except Exception:
        pass
    interactive = bool(sys.stdin) and sys.stdin.isatty()
    try:
        d = ours("gpsd.datadir").setup(apppaths, pick_again=pick_again, busy=busy, interactive=interactive,
                                       say=lambda m: print(m, flush=True))
    except Exception as e:                      # (the system drive's folder then, as before)
        print(f"  (data folder: {type(e).__name__}: {e})", flush=True)
        d = ours("gpsd.paintfile").base_dir()
    os.environ["EARTHGPS_DIR"] = d
    print(f"  Data          {d}", flush=True)
    return d


def console_title(text):
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(text)
        except (OSError, AttributeError):
            pass


def companion_version():
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "?"


def run(argv):
    earth = earth_root()
    if not BUNDLE and not earth:
        sys.exit("From source: python app_launcher.py --earth PATH-TO-BeamNG.Earth")
    set_paths(earth)
    if earth:
        os.environ.setdefault(EARTH_ENV, earth)
    mine, rest = split_args(argv)
    import launcher                          # BeamNG.Earth's own
    launcher.hand_over = lambda: False       # (a newer BeamNG.Earth .exe beside this one is not started instead)
    if not FROZEN:                           # (its server: this file again with --server, so the painter goes in)
        launcher.__file__ = os.path.abspath(__file__)
    orig_console = launcher.windows_console

    def windows_console():
        if not os.environ.get("OFFROAD_COMPANION_NO_CONSOLE"):    # (tests: the output stays where it goes)
            orig_console()
        console_title("Offroad Companion")
    launcher.windows_console = windows_console
    if os.name == "nt":
        launcher.windows_console()
    import install as earth_install
    print("", flush=True)
    print(f"  Offroad Companion {companion_version()}  (BeamNG.Earth {earth_install.version()} inside)", flush=True)
    print("  " + "-" * 48, flush=True)
    data_folder(launcher, "--pick-data-dir" in mine)
    user_dir = user_folder(rest, "--pick-user-dir" in mine)
    if user_dir and "--user-dir" not in rest[:rest.index("--") if "--" in rest else len(rest)]:
        rest = ["--user-dir", user_dir] + rest
    if user_dir:
        try:
            ours("setup_earth_source").install_gps_mod(user_dir)
        except Exception as e:
            print(f"  (Offroad Companion mod not copied: {e})", flush=True)
    keep_together(launcher)
    close_leftovers(launcher)
    if "--no-companion" not in mine:
        os.environ["OFFROAD_COMPANION_APP"] = "1"
        start_helper()
    sys.argv = [sys.argv[0]] + with_server_options(rest)
    launcher.main()


def run_helper_only(argv):
    """--companion: the helper alone in this window (beside BeamNG.Earth's own .exe: the game draws the track)."""
    set_paths(earth_root())
    console_title("Offroad Companion helper")
    return ours("earth_gpsd").main(helper_args() + argv)


def _probe():
    """In this process: is the course painter in BeamNG.Earth's grading, and its code's fingerprint."""
    import grading
    ep = ours("gpsd.earthpatch")
    return {"painter": bool(getattr(grading.Grader.apply, "_earthgps", False)), "code": ep.gps_code_id(),
            "planner": ep._is_server_main()}


def selftest():
    """--selftest: the painter in this process and in a worker process started the way the server starts its own
    (spawn), as JSON; exit 0 when it is in both (the build's check: tools/build_exe.py)."""
    import json
    install_painter(earth_root())
    here = _probe()
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        worker = pool.apply(_probe)
    import install as earth_install
    print(json.dumps({"offroad": companion_version(), "earth": earth_install.version(), "main": here,
                      "worker": worker}), flush=True)
    # (the planner ahead of the car: in the server's own process only, never in a worker: 1.6.5 and before started
    # one in every worker of the .exe)
    return 0 if here["painter"] and worker["painter"] and here["code"] == worker["code"] and here["planner"] \
        and not worker["planner"] else 1


def main():
    earth_root()                            # (from source: --earth taken out of the arguments)
    argv = sys.argv[1:]
    if argv[:1] == ["--server"]:
        earth = earth_root()
        set_paths(earth)
        import launcher
        launcher.ensure_ca_certs()
        launcher.run_server(argv[1:])
        return 0
    if argv[:1] == ["--companion"]:
        return run_helper_only(argv[1:])
    if argv[:1] == ["--selftest"]:
        return selftest()
    run(argv)
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()        # the server's worker processes in the .exe
    sys.exit(main())
