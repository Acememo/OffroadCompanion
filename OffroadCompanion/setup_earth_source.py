#!/usr/bin/env python3
"""One-time setup: BeamNG.Earth from source, next to this companion, so its server can run with the GPS course
painter (run_offroad_companion). The .exe's server is sealed (a PyInstaller build): it can draw the dirt track only as
decals and cannot leave buildings, low bridges and walls off the course; the source build can.

    python setup_earth_source.py [--user-dir FOLDER] [--version 1.5.4-beta] [--dir FOLDER] [--zip ZIP]

When this companion is inside (or next to) a BeamNG.Earth source folder of a version it works with (COMPATIBLE), that
one is used; else the source of EARTH_VERSION, the release this companion was made and tested with, is downloaded next
to it (the user, 2026-10-25: "should only download the source of the BeamNG.Earth version it's compatible with": not
the newest release, which may have changed what the course painter hooks into). Then BeamNG.Earth's own installer runs
there with your BeamNG.drive user folder: the one the game really uses, also when it was moved out of AppData
(the game's launcher setting; BeamNG.Earth's installer only looks in AppData), else you are asked. It copies
BeamNG.Earth's mod and the Offroad Companion mod into it and sets up the server's Python packages (a few minutes, once).
Both folders are remembered for run_offroad_companion. Your .exe stays as it is; the map cache is shared.
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gpsd import beamngdirs, paintfile  # noqa: E402
from gpsd.fetch import USER_AGENT  # noqa: E402

REPO = "TecnaGamer/BeamNG.Earth"
EARTH_VERSION = "1.9.1-beta"            # downloaded: the release this companion was made and tested with
COMPATIBLE = ("1.9.1", "1.9.0", "1.8.2", "1.8.1", "1.8.0", "1.7.3", "1.7.2", "1.7.1", "1.7.0", "1.6.3", "1.6.2", "1.6.1", "1.6.0", "1.5.")     # versions it works with (a copy already here of one: used)
API = f"https://api.github.com/repos/{REPO}"
ZIP = "https://codeload.github.com/" + REPO + "/zip/refs/tags/{tag}"
CONFIG = os.path.join(paintfile.base_dir(), "launcher.json")


def get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def compatible(version):
    """Does this companion work with BeamNG.Earth `version` (e.g. "1.6.2-beta", "v1.5.4-beta")?"""
    v = str(version or "").strip().lstrip("v")
    return any(v == c or v.startswith(c + "-") or (c.endswith(".") and v.startswith(c)) for c in COMPATIBLE)


def extract(data, dest):
    """The source zip (one top folder) into dest. Returns dest."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        top = names[0].split("/")[0] + "/"
        tmp = dest + ".part"
        shutil.rmtree(tmp, ignore_errors=True)
        for n in names:
            if not n.startswith(top) or n.endswith("/"):
                continue
            rel = n[len(top):]
            if not rel or ".." in rel.split("/"):
                continue
            out = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as f:
                shutil.copyfileobj(src, f)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.replace(tmp, dest)
    return dest


def is_earth(path):
    return bool(path) and os.path.isfile(os.path.join(path, "start.py")) and \
        os.path.isfile(os.path.join(path, "server", "earthd.py")) and os.path.isfile(os.path.join(path, "install.py"))


def existing_earth(cfg, out=print):
    """A BeamNG.Earth source folder already here of a version this companion works with: the one it is in (or next
    to), or the one set up before. One of another version is passed over (said so)."""
    for d in (os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE)), cfg.get("earth")):
        if is_earth(d):
            v = earth_version(d)
            if compatible(v):
                return os.path.abspath(d)
            out(f"BeamNG.Earth {v or '(version unknown)'} in {os.path.abspath(d)}: not a version this Offroad Companion "
                f"works with; using {EARTH_VERSION} instead (downloaded next to it)")
    return None


def earth_version(path):
    try:
        with open(os.path.join(path, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def mod_zip():
    """The Offroad Companion game mod zip shipped with the companion (OffroadCompanion/mod/offroad_companion.zip), or None."""
    for d in (os.path.join(HERE, "mod"), HERE, os.path.dirname(HERE)):
        p = os.path.join(d, "offroad_companion.zip")
        if os.path.isfile(p):
            return p
    return None


MOD_MARK = "lua/ge/extensions/offroadCompanion/main.lua"
# (the mod was beamng_earth_gps.zip, extension earthGps, until 1.2.0: an old copy is put aside the same way, or the
# game would run both apps)
MOD_MARKS = (MOD_MARK, "lua/ge/extensions/earthGps/main.lua")
ASIDE = "_old_offroad_companion"


def put_aside_other_copies(mods, keep):
    """Other zips of this mod in the mods folder (a browser's "offroad_companion (1).zip", a renamed copy, its repo
    folder): the game mounts them all and an older one's files can win (the user, 2026-10-22: a setting from the
    newest version missing), and the mod under its old name (beamng_earth_gps.zip, before 1.2.0). Moved into
    mods/_old_offroad_companion/. Returns the paths moved."""
    import zipfile
    out = []
    for root in (mods, os.path.join(mods, "repo")):
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            if not n.lower().endswith(".zip") or os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(keep)):
                continue
            try:
                with zipfile.ZipFile(p) as z:
                    names = set(z.namelist())
                    ours = any(m in names for m in MOD_MARKS)
            except (OSError, zipfile.BadZipFile):
                continue
            if not ours:
                continue
            aside = os.path.join(mods, ASIDE)
            os.makedirs(aside, exist_ok=True)
            dst = os.path.join(aside, n)
            k = 1
            while os.path.exists(dst):
                dst = os.path.join(aside, f"{k}-{n}")
                k += 1
            try:
                os.replace(p, dst)
                out.append(p)
            except OSError:
                pass
    return out


GPS_MOD_NAME = "offroad_companion"       # (its entry in the game's mods/db.json: the zip's name)


def ensure_gps_mod_active(user_dir):
    """The Offroad Companion mod turned back on in the game's mod list (mods/db.json) if something turned it off: joining a BeamMP
    server turns off every mod the server does not send and leaves them off afterwards (BeamNG.Earth 1.6 turns its own
    back on the same way). Only this mod's entry changes. True if it did."""
    path = os.path.join(user_dir, "mods", "db.json")
    try:
        with open(path, encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, ValueError):
        return False
    entry = db.get("mods", {}).get(GPS_MOD_NAME) if isinstance(db, dict) else None
    if not isinstance(entry, dict) or entry.get("active") is not False:
        return False
    entry["active"] = True
    tmp = path + ".egps-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)
    os.replace(tmp, path)
    return True


OLD_APP, NEW_APP = "earthGps", "offroadCompanion"


def migrate_layouts(user_dir):
    """The app under its old name (earthGps, before 1.2.0) in the player's saved UI layouts
    (settings/ui_apps/layouts/**/*.uilayout.json) renamed to the new one, so it stays where it was put. Only those
    entries change. Returns how many layout files changed."""
    root = os.path.join(user_dir, "settings", "ui_apps", "layouts")
    n = 0
    for dp, _dns, fns in os.walk(root):
        for fn in fns:
            if not fn.endswith(".uilayout.json"):
                continue
            p = os.path.join(dp, fn)
            try:
                with open(p, encoding="utf-8") as f:
                    lay = json.load(f)
            except (OSError, ValueError):
                continue
            apps = lay.get("apps") if isinstance(lay, dict) else None
            hit = False
            for a in apps if isinstance(apps, list) else ():
                if isinstance(a, dict) and OLD_APP in (a.get("appName"), a.get("directive")):
                    a["appName"] = a["directive"] = NEW_APP
                    if a.get("domElement"):
                        a["domElement"] = "<offroad-companion></offroad-companion>"
                    if a.get("name") == "BeamNG.Earth: GPS":
                        a["name"] = "Offroad Companion"
                    hit = True
            if hit:
                tmp = p + ".oc-tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(lay, f, indent=2)
                os.replace(tmp, p)
                n += 1
    return n


def migrate_old_folder(here=None):
    """The companion folder of before 1.2.0 (named "companion", beside this one): the player's saved tracks copied
    over (those not here yet), and the old folder renamed so its scripts are not started by mistake. Returns
    (tracks copied, the old folder's new path or None)."""
    here = os.path.abspath(here or HERE)
    old = os.path.join(os.path.dirname(here), "companion")
    if os.path.normcase(old) == os.path.normcase(here) or not os.path.isfile(os.path.join(old, "earth_gpsd.py")):
        return 0, None
    n = 0
    src, dst = os.path.join(old, "tracks"), os.path.join(here, "tracks")
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(src):
            a, b = os.path.join(src, fn), os.path.join(dst, fn)
            if os.path.isfile(a) and not os.path.exists(b) and fn != "README.txt":
                shutil.copy2(a, b)
                n += 1
    aside = old + " (old - now OffroadCompanion)"
    k = 2
    while os.path.exists(aside):
        aside = old + f" (old {k} - now OffroadCompanion)"
        k += 1
    try:
        os.rename(old, aside)
    except OSError:                         # (a window still open in it: left as it is)
        aside = None
    return n, aside


def install_gps_mod(user_dir):
    """The Offroad Companion mod into the user folder's mods (when it is not there yet or differs). Returns the path."""
    src = mod_zip()
    if not src:
        print("  (the Offroad Companion mod zip is not in the companion folder: copy offroad_companion.zip into "
              f"{os.path.join(user_dir, 'mods')} yourself)")
        return None
    mods = os.path.join(user_dir, "mods")
    os.makedirs(mods, exist_ok=True)
    dst = os.path.join(mods, "offroad_companion.zip")
    with open(src, "rb") as f:
        new = f.read()
    try:
        with open(dst, "rb") as f:
            same = f.read() == new
    except OSError:
        same = False
    moved = put_aside_other_copies(mods, dst)
    if moved:
        print(f"  Offroad Companion mod: {len(moved)} other copy(ies) moved out of the way (the game loaded an older one): "
              + ", ".join(os.path.basename(m) for m in moved))
    try:
        if ensure_gps_mod_active(user_dir):
            print("  Offroad Companion mod: it had been turned off in the game's mod list (a BeamMP server does that); turned it back on")
    except OSError as e:
        print(f"  (Offroad Companion mod: could not turn it back on in the game's mod list: {e})")
    try:
        n = migrate_layouts(user_dir)
        if n:
            print(f"  Offroad Companion mod: the app kept in {n} of your UI layouts under its new name")
    except OSError as e:
        print(f"  (Offroad Companion mod: UI layouts not updated: {e})")
    if same:
        print(f"  Offroad Companion mod: already up to date in {mods}")
    else:
        with open(dst + ".tmp", "wb") as f:
            f.write(new)
        os.replace(dst + ".tmp", dst)
        print(f"  Offroad Companion mod: copied into {mods}")
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", help=f"BeamNG.Earth version to download (default: {EARTH_VERSION}, the one this "
                    "companion is made for; another must be one it works with: " + ", ".join(COMPATIBLE) + ")")
    ap.add_argument("--any-version", action="store_true", help="allow a --version or --zip it was not made for")
    ap.add_argument("--dir", help="where to put a downloaded copy (default: next to this companion's folder)")
    ap.add_argument("--user-dir", help="your BeamNG.drive user folder (default: the one the game uses, found)")
    ap.add_argument("--fresh", action="store_true", help="download BeamNG.Earth even when a copy is already here")
    ap.add_argument("--no-install", action="store_true", help="only download (run BeamNG.Earth's install.py later)")
    ap.add_argument("--zip", help="a BeamNG.Earth source zip you downloaded yourself (GitHub: Code > Download ZIP)")
    args = ap.parse_args(argv)
    try:
        migrate_old_folder(HERE)
    except Exception:
        pass
    if sys.version_info < (3, 10):
        raise SystemExit("BeamNG.Earth's server needs Python 3.10 or newer (3.12 recommended): "
                         "https://www.python.org/downloads/")
    cfg = paintfile.read_json(CONFIG) or {}
    dest = None if (args.fresh or args.zip) else existing_earth(cfg)
    if dest:
        print(f"BeamNG.Earth from source: using the copy in {dest}")
    else:
        dest = fetch(args)
    # the game's user folder: the one the game uses (also moved out of AppData), not only BeamNG.Earth's default
    if args.user_dir:
        user_dir = beamngdirs.as_current(args.user_dir)
        if not os.path.isdir(user_dir):
            raise SystemExit(f"{user_dir} is not a folder")
    else:
        user_dir = beamngdirs.find(cfg.get("user_dir"), dest)
    if not user_dir:
        raise SystemExit("Your BeamNG.drive user folder was not found. Start the game once, then run this again, or "
                         "give it:  setup_earth_source --user-dir \"D:\\BeamNGUser\\current\"")
    cfg.update({"earth": dest, "user_dir": user_dir})
    try:
        paintfile.write_json(CONFIG, cfg)
    except OSError:
        pass
    if not args.no_install:
        print("  running BeamNG.Earth's installer (its mod into the game, the server's Python packages) ...\n")
        cmd = [sys.executable, os.path.join(dest, "install.py"), "--user-dir", user_dir, "--yes"]
        r = subprocess.call(cmd, cwd=dest)
        if r != 0:
            raise SystemExit(f"BeamNG.Earth's installer stopped (exit {r}); run it again: {' '.join(cmd)}")
    install_gps_mod(user_dir)
    print("\nDone. From now on:\n"
          "  1. close BeamNG.Earth's .exe if it is running (one world server at a time),\n"
          "  2. start OffroadCompanion/run_offroad_companion (instead of the .exe) and keep its window open,\n"
          "  3. start BeamNG.drive and pick the BeamNG.Earth level.\n"
          f"  (user folder: {user_dir})\n")
    return 0


def fetch(args):
    """Download (or unpack --zip) BeamNG.Earth's source next to this companion's folder: EARTH_VERSION, or --version
    when it is one this companion works with. Returns the folder."""
    any_version = getattr(args, "any_version", False)
    tag = "v" + (args.version or EARTH_VERSION).lstrip("v")
    if not compatible(tag) and not any_version:
        raise SystemExit(f"This Offroad Companion works with BeamNG.Earth {', '.join(COMPATIBLE)} (made for "
                         f"{EARTH_VERSION}), not {tag}. Leave --version out, or add --any-version to try it anyway.")
    by_hand = (f"Download it yourself: {release_zip(tag)}\n"
               "then run:  setup_offroad_companion --zip PATH-TO-THAT-ZIP")
    data = None
    if args.zip:
        with open(args.zip, "rb") as f:
            data = f.read()
        if not args.version:
            tag = "vlocal"
    parent = args.dir or os.path.dirname(os.path.dirname(HERE))
    dest = os.path.join(os.path.abspath(parent), f"BeamNG.Earth-{tag.lstrip('v')}-source")
    print(f"BeamNG.Earth {tag} from source -> {dest}")
    if os.path.isfile(os.path.join(dest, "server", "earthd.py")) and not args.zip:
        print("  already downloaded")
        return dest
    if data is None:
        print(f"  downloading {ZIP.format(tag=tag)} ...")
        try:
            data = get(ZIP.format(tag=tag))
        except Exception as e:
            raise SystemExit(f"Download failed ({e}).\n" + by_hand)
    extract(data, dest)
    if not is_earth(dest):
        raise SystemExit(f"{dest} does not hold BeamNG.Earth's source (no server/earthd.py)")
    v = earth_version(dest)
    if args.zip and not compatible(v) and not any_version:
        raise SystemExit(f"That zip is BeamNG.Earth {v or '(version unknown)'}, not one this Offroad Companion works "
                         f"with ({', '.join(COMPATIBLE)}). " + by_hand + "\n(or add --any-version to try it anyway)")
    print("  unpacked")
    return dest


def release_zip(tag):
    """The web address of a BeamNG.Earth release's source zip (to download by hand)."""
    return f"https://github.com/{REPO}/archive/refs/tags/{tag}.zip"


if __name__ == "__main__":
    sys.exit(main())
