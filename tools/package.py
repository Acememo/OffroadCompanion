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


def add_tree(z, src, arc, skip=()):
    for dp, dns, fns in os.walk(src):
        dns[:] = sorted(d for d in dns if d != "__pycache__" and os.path.join(dp, d) not in skip)
        for fn in sorted(fns):
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(dp, fn)
            z.write(full, os.path.join(arc, os.path.relpath(full, src)).replace(os.sep, "/"))


def main():
    v = version()
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST)
    mod_src = os.path.join(ROOT, "mod", "offroad_companion")
    mod_zip = os.path.join(DIST, "offroad_companion.zip")
    with zipfile.ZipFile(mod_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for part in ("scripts", "lua", "ui", "art", "levels"):
            if os.path.isdir(os.path.join(mod_src, part)):
                add_tree(z, os.path.join(mod_src, part), part)
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
        z.write(mod_zip, "Resources/Client/offroad_companion.zip")
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
