"""Where Offroad Companion and BeamNG.Earth keep their data (the user, 2026-10-28: "could you give the option to save all
its cache and stuff somewhere else apart from the current drive? Maybe on the first run it asks you where to save that
data").

The first start of the .exe asks: keep it on the system drive (Enter), or choose a folder (the system's folder window,
or the path typed). Chosen elsewhere, everything that grows goes there:

    <folder>/OffroadCompanion        Offroad Companion's data (the courses' planned ground, replay snapshots, your
                                     tracks, downloads): paintfile.base_dir() follows LOCATION_FILE to it
    <folder>/BeamNG.Earth cache      BeamNG.Earth's map downloads (elevation, photos, map data: the big one, up to its
                                     cache cap, 20 GB by default): its own remembered cacheDir (apppaths), so
                                     BeamNG.Earth's own .exe uses the same folder

What is already there can be moved over (asked; or left to be downloaded again). The answer is kept in the system
drive's small Offroad Companion folder (paintfile.LOCATION_FILE) and never asked again; --pick-data-dir asks again.
BeamNG.Earth's logs and remembered choices (a few MB) and the game's own user folder stay where they are.

Standard library only. The questions go through ask / say (input / print), the folder window through BeamNG.Earth's
apppaths (pick, ask_path).
"""
import os
import shutil
import time

from . import paintfile

OURS = "OffroadCompanion"
EARTH_CACHE = "BeamNG.Earth cache"
NEED_GB = 25.0          # free space below this on the chosen drive: said so (BeamNG.Earth's cache cap is 20 GB)


def location(home=None):
    """What was chosen: {"dir": our folder or None (the system drive)} or None (never asked)."""
    loc = paintfile.read_json(os.path.join(home or paintfile.default_dir(), paintfile.LOCATION_FILE))
    return loc if isinstance(loc, dict) and "dir" in loc else None


def remember(home, ours_dir, earth_cache=None):
    paintfile.write_json(os.path.join(home, paintfile.LOCATION_FILE),
                         {"dir": ours_dir, "earthCache": earth_cache, "chosen": time.strftime("%Y-%m-%d %H:%M")})
    paintfile._WHERE.clear()


def size_of(path):
    """Bytes in the folder (0: none)."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def gb(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.0f} MB" if n >= 1e6 else "under 1 MB"


def writable(path):
    """path (absolute, the system's separators) when a folder can be made there and written in, else None."""
    try:
        path = os.path.abspath(os.path.expanduser(str(path).strip().strip('"')))
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".offroad-write-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return path
    except OSError:
        return None


def same(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def inside(a, b):
    """Is a inside b (or b itself)?"""
    a, b = os.path.normcase(os.path.abspath(a)), os.path.normcase(os.path.abspath(b))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def move_contents(src, dst, say=print, skip=()):
    """Everything in src moved into dst (one entry at a time, said as it goes; one in use stays where it is).
    Returns (moved, left) counts."""
    moved = left = 0
    if not os.path.isdir(src) or same(src, dst):
        return 0, 0
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        if name in skip:
            continue
        a, b = os.path.join(src, name), os.path.join(dst, name)
        if os.path.exists(b):
            left += 1
            continue
        n = size_of(a) if os.path.isdir(a) else os.path.getsize(a)
        if n >= 200e6:
            say(f"    moving {name} ({gb(n)})...")
        try:
            shutil.move(a, b)
            moved += 1
        except (OSError, shutil.Error) as e:
            say(f"    {name} left where it was ({e})")
            left += 1
    try:
        if not os.listdir(src):
            os.rmdir(src)
    except OSError:
        pass
    return moved, left


def earth_cache_now(apppaths):
    """BeamNG.Earth's download cache folder now (its remembered one, else its default)."""
    if apppaths is None:
        return None
    try:
        return apppaths.saved_cache_dir() or apppaths.default_cache_dir()
    except Exception:
        return None


def setup(apppaths=None, pick_again=False, ask=input, say=print, home=None, busy=False, interactive=True):
    """The data folder for this start: asks the first time (or with pick_again), moves what is there when wanted, and
    remembers it. Returns Offroad Companion's data folder (also when nothing is asked). busy: another Offroad Companion
    or BeamNG.Earth is running (nothing is moved then). interactive False (no one to answer): nothing asked, nothing
    remembered."""
    home = home or paintfile.default_dir()
    loc = location(home)
    if loc is not None and not pick_again:
        d = loc.get("dir")
        if not d:
            return home
        if os.path.isdir(d) or writable(d):
            return d
        say(f"  Your data folder {d} can't be reached (a drive unplugged or renamed?).")
        say("  Plug the drive in and start again, or choose where it goes now.")
    if not interactive:
        return loc.get("dir") if loc and loc.get("dir") else home
    current = loc.get("dir") if loc and loc.get("dir") else home
    cache_now = earth_cache_now(apppaths)
    say("")
    say("  Where should the map downloads and Offroad Companion's data be kept?")
    say(f"  BeamNG.Earth's map downloads grow to about 20 GB as you drive; Offroad Companion's planned tracks and")
    say(f"  replays' ground add some more. Now: {current}" + (f" and {cache_now}" if cache_now else ""))
    try:
        answer = ask("  Enter: keep them where they are.  F: choose another folder (another drive).  ").strip()
    except (EOFError, OSError):
        answer = ""
    if answer.lower() not in ("f", "folder") and not os.path.isabs(os.path.expanduser(answer.strip('"'))):
        if loc is None:
            remember(home, None if same(current, home) else current, cache_now)
        say(f"  Data stays in {current}")
        return current
    if os.path.isabs(os.path.expanduser(answer.strip('"'))):
        root = writable(os.path.abspath(os.path.expanduser(answer.strip('"'))))
        if root is None:
            say(f"  Can't write in {answer}: nothing changed")
            return current
    elif apppaths is not None and hasattr(apppaths, "ask_path"):
        root = apppaths.ask_path("Which folder? (a new folder is made in it for each)", "folder", writable,
                                 ask=ask, say=say)
    else:
        try:
            typed = ask("  Type or paste the folder: ").strip().strip('"')
        except (EOFError, OSError):
            typed = ""
        root = writable(os.path.abspath(os.path.expanduser(typed))) if typed else None
    if not root:
        if loc is None:
            remember(home, None if same(current, home) else current, cache_now)
        say(f"  Nothing chosen: data stays in {current}")
        return current
    ours = os.path.join(root, OURS)
    cache = os.path.join(root, EARTH_CACHE)
    if inside(ours, home) and not same(ours, home):
        say("  That folder is inside the current one: choose another")
        return current
    try:
        free = shutil.disk_usage(root).free
        if free < NEED_GB * 1e9:
            say(f"  (only {gb(free)} free there: BeamNG.Earth's map downloads can take up to 20 GB)")
    except OSError:
        pass
    have = [(p, size_of(p)) for p in (current, cache_now) if p and os.path.isdir(p)]
    total = sum(n for _p, n in have)
    move = False
    if total and not busy:
        try:
            a = ask(f"  Move what's already there ({gb(total)}) to the new folder? Enter: yes.  N: start empty "
                    "(downloaded again).  ").strip().lower()
        except (EOFError, OSError):
            a = "n"
        move = a in ("", "y", "yes", "s", "si", "sí")
    elif total and busy:
        say("  (Offroad Companion or BeamNG.Earth is running in another window: nothing is moved; close it and use "
            "--pick-data-dir to move it later)")
    os.makedirs(ours, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    if move:
        say("  Moving (this can take a few minutes for the map downloads)...")
        m1, l1 = move_contents(current, ours, say, skip=(paintfile.LOCATION_FILE,) if same(current, home) else ())
        # (on Linux BeamNG.Earth's own files share its cache folder: its remembered choices and logs stay)
        keep = ()
        try:
            if apppaths is not None and same(cache_now, apppaths.data_dir()):
                keep = ("app.json", "logs", "gcpatch")
        except Exception:
            pass
        m2, l2 = move_contents(cache_now, cache, say, skip=keep) if cache_now and not inside(cache_now, ours) else (0, 0)
        say(f"  Moved {m1 + m2} item(s)" + (f"; {l1 + l2} left where they were" if l1 + l2 else ""))
    if apppaths is not None and hasattr(apppaths, "set_cache_dir"):
        got, err = apppaths.set_cache_dir(cache)
        if err:
            say(f"  (BeamNG.Earth's map downloads stay in {cache_now}: {err})")
            cache = cache_now
    remember(home, ours, cache)
    say(f"  Data now in {root}")
    return ours
