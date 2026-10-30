"""Where BeamNG.drive keeps its user folder, including one moved out of AppData (the game's launcher can put it on
another drive, e.g. D:\\BeamNGUser\\current): BeamNG.Earth's installer and start.py only look in AppData.

Order: a folder chosen before (remembered), the game's own setting (userFolder in
%LOCALAPPDATA%\\BeamNG\\BeamNG.drive.ini, as BeamNG.Earth's .exe launcher reads it), BeamNG.Earth's config
(.beamng_earth.json), the default folders. Standard library only.
"""
import glob
import json
import os
import sys

IS_WIN = os.name == "nt"


def _ini(path):
    out = {}
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith((";", "#", "[")):
                    k, v = line.split("=", 1)
                    out[k.strip().lower()] = os.path.expandvars(v.strip().strip('"'))
    except OSError:
        pass
    return out


def local_appdata():
    return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")


def as_current(d):
    """A user folder as the game uses it: <folder>\\current when that exists (0.32 and later)."""
    if not d:
        return None
    d = os.path.abspath(os.path.expanduser(d.strip().strip('"')))
    if os.path.basename(d.rstrip("\\/")).lower() != "current" and os.path.isdir(os.path.join(d, "current")):
        return os.path.join(d, "current")
    return d


def looks_like_user_dir(d):
    """The game has run with it: it has its mods or settings folder."""
    return bool(d) and os.path.isdir(d) and (os.path.isdir(os.path.join(d, "mods")) or
                                             os.path.isdir(os.path.join(d, "settings")))


def game_setting():
    """The user folder set in the game's launcher (BeamNG.drive.ini userFolder), or None."""
    if not IS_WIN:
        return None
    ini = _ini(os.path.join(local_appdata(), "BeamNG", "BeamNG.drive.ini"))
    for key in ("userfolder", "userpath", "user_folder"):
        d = as_current(ini.get(key))
        if d and os.path.isdir(d):
            return d
    return None


def defaults():
    out = []
    if IS_WIN:
        local = local_appdata()
        out.append(os.path.join(local, "BeamNG", "BeamNG.drive", "current"))
        out += sorted(glob.glob(os.path.join(local, "BeamNG.drive", "[0-9]*")), reverse=True)
    else:
        home = os.path.expanduser("~")
        out.append(os.path.join(home, ".local", "share", "BeamNG", "BeamNG.drive", "current"))
        out.append(os.path.join(home, ".local", "share", "BeamNG.drive", "current"))
    return [d for d in out if os.path.isdir(d)]


def candidates(remembered=None, earth_root=None):
    """[(folder, where it came from)], best first, each once."""
    out = []
    if remembered:
        out.append((as_current(remembered), "chosen before"))
    g = game_setting()
    if g:
        out.append((g, "the game's user folder setting"))
    if earth_root:
        try:
            with open(os.path.join(earth_root, ".beamng_earth.json"), encoding="utf-8") as f:
                ud = json.load(f).get("user_dir")
            if ud:
                out.append((as_current(ud), "BeamNG.Earth's config"))
        except (OSError, ValueError):
            pass
    out += [(d, "the default folder") for d in defaults()]
    seen, keep = set(), []
    for d, why in out:
        if not d or not os.path.isdir(d):
            continue
        k = os.path.normcase(os.path.realpath(d))
        if k not in seen:
            seen.add(k)
            keep.append((d, why))
    # a folder the game has really used goes before an empty one
    keep.sort(key=lambda t: 0 if looks_like_user_dir(t[0]) else 1)
    return keep


def find(remembered=None, earth_root=None, ask=True, out=print, pick_again=False):
    """The user folder: the one chosen before when it is still there (never asked again: the user, 2026-10-23, "so I
    don't have to click enter EVERY time"), else the best candidate; with several real ones, or none, the player is
    asked (Enter = the first). pick_again: asked even with one chosen before. Returns a path or None."""
    cands = candidates(remembered, earth_root)
    real = [c for c in cands if looks_like_user_dir(c[0])]
    if not pick_again:
        before = [c for c in real if c[1] == "chosen before"]
        if before:
            out(f"BeamNG.drive user folder: {before[0][0]}  (chosen before; to pick another: --pick-user-dir)")
            return before[0][0]
    if len(real) == 1 or (real and not ask):
        out(f"BeamNG.drive user folder: {real[0][0]}  ({real[0][1]})")
        return real[0][0]
    if not ask or not sys.stdin or not sys.stdin.isatty():
        return cands[0][0] if cands else None
    if cands:
        out("BeamNG.drive user folders found:")
        for i, (d, why) in enumerate(cands, 1):
            out(f"  {i}. {d}  ({why})")
    out("In the game, Options > Other > 'User folder' shows the one it uses.")
    while True:
        try:
            pick = input(f"Which one? [{'1-' + str(len(cands)) + ', ' if cands else ''}or type the folder"
                         f"{', Enter = 1' if cands else ''}] ").strip().strip('"')
        except EOFError:
            pick = ""
        if not pick and cands:
            return cands[0][0]
        if pick.isdigit() and cands and 1 <= int(pick) <= len(cands):
            return cands[int(pick) - 1][0]
        d = as_current(pick)
        if d and os.path.isdir(d):
            return d
        out(f"  {pick!r} is not a folder; type its full path, e.g. D:\\BeamNGUser\\current")
