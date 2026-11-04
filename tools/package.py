"""Builds the release zips into dist/, named after OffroadCompanion/VERSION:

    OffroadCompanion-<version>.zip                 the OffroadCompanion folder (with the game mod in OffroadCompanion/mod)
    OffroadCompanion-BeamMP-Server-<version>.zip  Resources/Client/offroad_companion.zip for a BeamMP server
    OffroadCompanion-source-<version>.zip         everything (README, CHANGELOG, LICENSE, OffroadCompanion, mod, tools)
    offroad_companion.zip                          the game mod alone (its name is the game's mod name: never versioned)

    python3 tools/package.py
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")


def version():
    with open(os.path.join(ROOT, "OffroadCompanion", "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def past_stamp(mtime):
    """A zip entry's time for the game's mod zip: mtime - 14 h as UTC wall time (BeamNG.Earth 1.8.1's packager does the
    same for its own). Zip times have no time zone and the game reads them as local time: built on a UTC machine they
    were hours in the future west of UTC (the Americas), and the game took the mod's terrain materials for newer than
    its texture cache and packed the ground's textures again at every new block (BeamNG.Earth 1.8.0's 15-25 s freezes
    in BeamMP). 14 h back is in the past in every time zone (UTC-12 .. +14)."""
    import time
    return time.gmtime(mtime - 14 * 3600)[:6]


def add_tree(z, src, arc, skip=(), past=False):
    for dp, dns, fns in os.walk(src):
        dns[:] = sorted(d for d in dns if d != "__pycache__" and os.path.join(dp, d) not in skip)
        for fn in sorted(fns):
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(dp, fn)
            name = os.path.join(arc, os.path.relpath(full, src)).replace(os.sep, "/")
            if past:
                info = zipfile.ZipInfo(name, past_stamp(os.path.getmtime(full)))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as f:
                    z.writestr(info, f.read())
            else:
                z.write(full, name)


def main():
    v = version()
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST)
    mod_src = os.path.join(ROOT, "mod", "offroad_companion")
    mod_zip = os.path.join(DIST, "offroad_companion.zip")
    with zipfile.ZipFile(mod_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for part in ("scripts", "lua", "ui", "art", "levels"):
            if os.path.isdir(os.path.join(mod_src, part)):
                add_tree(z, os.path.join(mod_src, part), part, past=True)
    comp = os.path.join(ROOT, "OffroadCompanion")
    shutil.rmtree(os.path.join(comp, "mod"), ignore_errors=True)
    os.makedirs(os.path.join(comp, "mod"))
    shutil.copy(mod_zip, os.path.join(comp, "mod", "offroad_companion.zip"))
    skip = {os.path.join(comp, "cache")}
    out = []
    p = os.path.join(DIST, f"OffroadCompanion-{v}.zip")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        add_tree(z, comp, "OffroadCompanion", skip)
    out.append(p)
    p = os.path.join(DIST, f"OffroadCompanion-BeamMP-Server-{v}.zip")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("Resources/Client/offroad_companion.zip", past_stamp(os.path.getmtime(mod_zip)))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o644 << 16
        with open(mod_zip, "rb") as f:
            z.writestr(info, f.read())      # (dated in the past too: past_stamp)
        z.write(os.path.join(ROOT, "tools", "beammp_readme.md"), "OffroadCompanion-README.md")
    out.append(p)
    p = os.path.join(DIST, f"OffroadCompanion-source-{v}.zip")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(ROOT, "README.md"), "README.md")
        z.write(os.path.join(ROOT, "CHANGELOG.md"), "CHANGELOG.md")
        z.write(os.path.join(ROOT, "LICENSE"), "LICENSE")
        add_tree(z, comp, "OffroadCompanion", skip | {os.path.join(comp, "mod")})
        add_tree(z, os.path.join(ROOT, "mod"), "mod")
        add_tree(z, os.path.join(ROOT, "tools"), "tools")
    out.append(p)
    shutil.copy(os.path.join(ROOT, "README.md"), DIST)
    shutil.copy(os.path.join(ROOT, "CHANGELOG.md"), DIST)
    for q in out + [mod_zip]:
        print(f"{os.path.relpath(q, ROOT)}  ({os.path.getsize(q) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
