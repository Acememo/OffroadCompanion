"""Where the companion and the BeamNG.Earth server meet: one small folder per user.

    course.json      the course to paint (written by the companion when the game says so)
    painter.json     a heartbeat from a BeamNG.Earth server started with the course painter (earthpatch.py)
    windows/<cid>/   computed track pieces per course window (shared by the server's processes; each written once:
                     the first ground planned for a course stays its ground)
    snapshots/<name>/  a course's windows as they were when a replay was recorded (meta.json: the course, its
                     settings and seal): the server uses them as they are when a plan pins it

Standard library only: the companion runs on any Python, the server side imports this too.
"""
import json
import os
import tempfile
import time

VERSION = 1


_MOVED = []


LOCATION_FILE = "data-location.json"     # in default_dir(): {"dir": the data folder chosen elsewhere, or null}


def base_dir():
    """The folder: EARTHGPS_DIR, else the one chosen on another drive (datadir.py: LOCATION_FILE in the default folder
    says where; the user, 2026-10-28: "the option to save all its cache and stuff somewhere else apart from the current
    drive"), else default_dir()."""
    env = os.environ.get("EARTHGPS_DIR")
    if env:
        return env
    home = default_dir()
    now = time.monotonic()
    got = _WHERE.get(home)
    if got is None or now - got[0] > 5.0:           # (read again every few seconds: asked often)
        loc = read_json(os.path.join(home, LOCATION_FILE))
        moved = loc.get("dir") if isinstance(loc, dict) else None
        got = _WHERE[home] = (now, moved if isinstance(moved, str) and moved else home)
    return got[1]


_WHERE = {}


def default_dir():
    """The folder on the system drive (OffroadCompanion in the user's local app data). The project was called
    BeamNG.Earth GPS until 1.2.0 (the user, 2026-10-23: "rename the whole project to Offroad Companion"): its folder
    is moved to the new name the first time (the course's planned ground, replay snapshots, the remembered folders:
    nothing planned again)."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        new, old = os.path.join(root, "OffroadCompanion"), os.path.join(root, "BeamNG.Earth-GPS")
    else:
        root = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        new, old = os.path.join(root, "offroad-companion"), os.path.join(root, "beamng-earth-gps")
    if not _MOVED:
        _MOVED.append(True)
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                os.replace(old, new)
            except OSError:             # (in use, another drive: the old one as it is)
                return old
    if not os.path.isdir(new) and os.path.isdir(old):
        return old
    return new


def course_path():
    return os.path.join(base_dir(), "course.json")


def heartbeat_path():
    return os.path.join(base_dir(), "painter.json")


def pose_path():
    """Where the player is (the game, through the companion): the server's prefetch plans the course's track there
    ahead of BeamNG.Earth asking for it."""
    return os.path.join(base_dir(), "pose.json")


def windows_dir(cid):
    return os.path.join(base_dir(), "windows", cid)


SNAPSHOTS_KEEP = 60


def snapshot_name(name):
    """A snapshot's folder name from any name (letters, digits, - and _; at most 80)."""
    out = "".join(ch if (ch.isalnum() and ch.isascii()) or ch in "-_" else "_" for ch in str(name or ""))
    return out[:80].strip("_") or None


def snapshots_dir(name=None):
    root = os.path.join(base_dir(), "snapshots")
    if name is None:
        return root
    n = snapshot_name(name)
    return os.path.join(root, n) if n else None


def write_json(path, obj):
    """Atomic: the server's processes never read half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json_first(path, obj):
    """Writes obj at path unless a file is there already, atomically; returns what is at path afterwards (obj, or the
    one another process wrote first). The course's ground is the first one planned: every process uses that one."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        got = read_json(path)
        if got is not None:
            return got
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"))
        try:
            os.link(tmp, path)              # (fails when the file is there: never replaced)
        except FileExistsError:
            got = read_json(path)
            return got if got is not None else obj
        except OSError:                     # (no hard links here: replaced only when still missing)
            if os.path.exists(path):
                got = read_json(path)
                return got if got is not None else obj
            os.replace(tmp, path)
            tmp = None
        return obj
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_course(points, name, scale=1.0, enabled=True, track_id="", paint=True, clear=True):
    """The course for BeamNG.Earth's server (points [[lat, lon]...]): paint its dirt track, clear its corridor of
    buildings, low bridges and walls; enabled False: nothing."""
    obj = {"version": VERSION, "enabled": bool(enabled), "name": name or "Course", "scale": float(scale),
           "paint": bool(paint), "clear": bool(clear), "trackId": track_id, "points": points if enabled else [],
           "t": time.time()}
    write_json(course_path(), obj)
    return obj


def write_plan(lines):
    """What BeamNG.Earth's server paints and clears: lines [{kind: course | route, points [[lat, lon]...], name, scale,
    paint, clear}] (nothing: an empty list)."""
    obj = {"version": 2, "enabled": bool(lines), "lines": lines or [], "t": time.time()}
    write_json(course_path(), obj)
    return obj


def painter_status(max_age=90.0):
    """The heartbeat of a painting BeamNG.Earth server: {pid, t, course, ...} when it is recent, else None."""
    hb = read_json(heartbeat_path())
    if not hb or time.time() - float(hb.get("t") or 0) > max_age:
        return None
    return hb
