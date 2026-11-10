#!/usr/bin/env python3
"""Builds dist/OffroadCompanion-<version>.exe: Offroad Companion as one Windows program (OffroadCompanion/app_launcher.py),
with BeamNG.Earth's launcher, server and mod and Python inside, the way BeamNG.Earth builds its own .exe
(its tools/build_app.py: PyInstaller, one file, a version resource and a manifest, no UPX).

    python tools/build_exe.py --earth PATH-TO-BeamNG.Earth-source [--bootloader run.exe]

Run it with a Windows Python 3.12 (on Windows, or under Wine) that has pyinstaller and BeamNG.Earth's server packages
(its server/requirements.txt). --earth: BeamNG.Earth's source folder of the version this release is made for
(OffroadCompanion/setup_earth_source.py EARTH_VERSION; the build stops on another). Run tools/package.py first (the
game mod zip goes in from OffroadCompanion/mod).

--bootloader: a PyInstaller bootloader built from source for this PyInstaller (its bootloader folder: python waf all,
or cross-built with MinGW-w64: CC=x86_64-w64-mingw32-gcc python waf configure --target-arch=64bit --gcc all); the
wheel's prebuilt one (shared by every PyInstaller app: antivirus heuristics know it) otherwise, with a warning.

Offroad Companion's own files go in as plain files (OffroadCompanion/ in the bundle), not frozen: the course painter's
code fingerprint (earthpatch.gps_code_id: its gpsd/*.py) is then the same as a source install's, so the ground codes
match between the .exe and a source install. The standard library modules they use are frozen in (found from their
imports).
"""
import argparse
import ast
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMP = os.path.join(ROOT, "OffroadCompanion")
NAME = "OffroadCompanion"
SEP = ";" if os.name == "nt" else ":"
# Offroad Companion's files the .exe needs (the rest: tests, the source install's scripts, caches)
KEEP_FILES = ("VERSION", "app_launcher.py", "appupdate.py", "earth_gpsd.py", "setup_earth_source.py")
KEEP_DIRS = ("gpsd", "mod")
SKIP_DIRS = ("__pycache__", "cache", "tests")
# BeamNG.Earth's server data files (in its server folder, read from beside its modules)
SERVER_DATA = ("*.npz", "koppen_*.png", "overture_stac_*.json.gz", "lidarbc*_index.json.gz", "sign_glyphs.json",
               "sign_states.geojson")


def earth_data_files(earth):
    """The server's data files BeamNG.Earth's own build (its tools/build_app.py) adds beside its modules, by name
    (os.path.join(server, '<name>')), with SERVER_DATA's patterns: a file a new BeamNG.Earth adds is never left out of
    our .exe (1.7.1 added the BC lidar indexes and the highway signs' lettering and state outlines)."""
    import re
    server = os.path.join(earth, "server")
    names = set()
    try:
        with open(os.path.join(earth, "tools", "build_app.py"), encoding="utf-8") as f:
            names.update(re.findall(r"os\.path\.join\(server, '([^']+)'\)", f.read()))
    except OSError:
        pass
    out = {os.path.join(server, n) for n in names if os.path.isfile(os.path.join(server, n))}
    for pat in SERVER_DATA:
        out.update(glob.glob(os.path.join(server, pat)))
    return sorted(out)


def earth_data_dirs(earth):
    """The server's data folders BeamNG.Earth's own build adds, each under its own name ((source, name) pairs: its
    build_app.py's os.path.join(server, '<dir>'){SEP}<name>). 1.8.2's server/data: the billboards, the direction
    signs' styles and lettering, the place search's places, read from beside the modules' "data" folder."""
    import re
    server = os.path.join(earth, "server")
    try:
        with open(os.path.join(earth, "tools", "build_app.py"), encoding="utf-8") as f:
            found = re.findall(r"os\.path\.join\(server, '([^']+)'\)\}\{SEP\}([A-Za-z0-9_./-]+)\"", f.read())
    except OSError:
        found = []
    out = []
    for src, name in found:
        path = os.path.join(server, src)
        if name != "." and os.path.isdir(path) and (path, name) not in out:
            out.append((path, name))
    data = os.path.join(server, "data")             # (named by hand too: never left out if its build names it otherwise)
    if os.path.isdir(data) and all(p != data for p, _ in out):
        out.append((data, "data"))
    return out


def have_module(name):
    import importlib.util
    return importlib.util.find_spec(name) is not None


def version():
    with open(os.path.join(COMP, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def earth_version(earth):
    with open(os.path.join(earth, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def stage(work):
    """Offroad Companion's files for the bundle, in work/OffroadCompanion. Returns that folder."""
    out = os.path.join(work, "OffroadCompanion")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for f in KEEP_FILES:
        shutil.copy2(os.path.join(COMP, f), out)
    for d in KEEP_DIRS:
        shutil.copytree(os.path.join(COMP, d), os.path.join(out, d),
                        ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
    os.makedirs(os.path.join(out, "tracks"))
    shutil.copy2(os.path.join(COMP, "tracks", "README.txt"), os.path.join(out, "tracks"))
    if not os.path.isfile(os.path.join(out, "mod", "offroad_companion.zip")):
        sys.exit("OffroadCompanion/mod/offroad_companion.zip is missing: run tools/package.py first")
    return out


def stdlib_imports(folder):
    """The standard library modules (dotted, and their packages) Offroad Companion's files import."""
    std = set(getattr(sys, "stdlib_module_names", ()))
    out = set()
    for dp, _dns, fns in os.walk(folder):
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(dp, fn), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for n in ast.walk(tree):
                mods = []
                if isinstance(n, ast.Import):
                    mods = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                    mods = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
                for m in mods:
                    if m.split(".")[0] in std:
                        out.add(m)
    # (a "from x import name" may name a function, not a module: only the module parts that are importable)
    import importlib.util
    keep = set()
    for m in sorted(out):
        try:
            if importlib.util.find_spec(m) is not None:
                keep.add(m)
        except (ImportError, ValueError, AttributeError):
            pass
    return sorted(keep)


def make_icon(work):
    from PIL import Image
    im = Image.open(os.path.join(ROOT, "mod", "offroad_companion", "ui", "modules", "apps", "OffroadCompanion", "app.png"))
    im = im.convert("RGBA")
    ico = os.path.join(work, "icon.ico")
    im.resize((256, 256), Image.LANCZOS).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                                           (256, 256)])
    return ico


def win_version(ver):
    nums = []
    for part in ver.split("-")[0].split(".")[:4]:
        digits = "".join(c for c in part if c.isdigit())
        nums.append(min(int(digits or 0), 65535))
    return tuple(nums + [0] * (4 - len(nums)))


def version_files(work, ver, earth_ver):
    """The .exe's version resource (its Properties' Details tab) and manifest, as BeamNG.Earth's build makes them."""
    v4 = win_version(ver)
    dotted = ".".join(map(str, v4))
    strings = {"CompanyName": "Offroad Companion", "FileDescription": "Offroad Companion for BeamNG.Earth",
               "FileVersion": ver, "InternalName": NAME,
               "LegalCopyright": "Offroad Companion; BeamNG.Earth: Copyright (c) 2026 TecnaGamer, MIT License",
               "OriginalFilename": f"{NAME}-{ver}.exe", "ProductName": "Offroad Companion", "ProductVersion": ver,
               "Comments": f"Off-road race courses in BeamNG.Earth (BeamNG.Earth {earth_ver} inside)"}
    vf = os.path.join(work, "version_info.txt")
    with open(vf, "w", encoding="utf-8") as f:
        f.write("VSVersionInfo(\n"
                f"  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004,\n"
                "                    fileType=0x1, subtype=0x0, date=(0, 0)),\n"
                "  kids=[\n"
                "    StringFileInfo([StringTable('040904B0', [\n")
        f.write(",\n".join(f"      StringStruct({k!r}, {v!r})" for k, v in strings.items()))
        f.write("])]),\n"
                "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
                "  ]\n)\n")
    mf = os.path.join(work, "app.manifest")
    with open(mf, "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity type="win32" name="OffroadCompanion.Launcher" version="{dotted}" processorArchitecture="amd64"/>
  <description>{strings["FileDescription"]}</description>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{{e2011457-1546-43c5-a5fe-008deee3d3f0}}"/>
      <supportedOS Id="{{35138b9a-5d96-4fbd-8e2d-a2440225f93a}}"/>
      <supportedOS Id="{{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}}"/>
      <supportedOS Id="{{1f676c76-80e1-4239-95bb-83d0f6d0da78}}"/>
      <supportedOS Id="{{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}}"/>
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
    </windowsSettings>
  </application>
</assembly>
""")
    return vf, mf


# PyInstaller with EXE's bootloader lookup pointed at our own run.exe (BeamNG.Earth's build_app.py does the same)
BOOT_SHIM = ("import sys\n"
             "from PyInstaller.building import api\n"
             "boot = sys.argv.pop(1)\n"
             "api.EXE._bootloader_file = lambda self, exe, extension=None: boot\n"
             "from PyInstaller.__main__ import run\n"
             "run(sys.argv[1:])\n")


def pyinstaller(work, earth, staged, ico, ver, earth_ver, boot=None):
    server = os.path.join(earth, "server")
    mods = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(server, "*.py")))
    cmd = [sys.executable] + (["-c", BOOT_SHIM, boot] if boot else ["-m", "PyInstaller"])
    cmd += ["--noconfirm", "--clean", "--console", "--noupx", "--onefile", "--name", NAME,
            "--distpath", os.path.join(work, "dist"), "--workpath", os.path.join(work, "build"),
            "--specpath", work, "--paths", server, "--paths", earth, "--icon", ico,
            "--collect-submodules", "fsspec",
            "--hidden-import", "certifi", "--collect-data", "certifi",
            "--add-data", f"{os.path.join(earth, 'mod', 'beamng_earth')}{SEP}mod/beamng_earth",
            "--add-data", f"{os.path.join(earth, 'VERSION')}{SEP}.",
            "--add-data", f"{staged}{SEP}OffroadCompanion",
            "--runtime-hook", os.path.join(ROOT, "tools", "rthook_wine.py"),
            "--exclude-module", "gpsd", "--exclude-module", "earth_gpsd", "--exclude-module", "setup_earth_source",
            "--exclude-module", "appupdate"]
    # the server's data files beside its modules, as BeamNG.Earth's build_app.py adds them (1.6: the bridge types;
    # 1.7: the climate map, oil wells, refineries, the pinned Overture release's index): every one there, so a new
    # one is never left out
    for p in earth_data_files(earth):
        cmd += ["--add-data", f"{p}{SEP}."]
    for p, name in earth_data_dirs(earth):          # (1.8.2: server/data, as "data")
        cmd += ["--add-data", f"{p}{SEP}{name}"]
    if have_module("truststore"):                   # (1.7: Windows' own certificate store, netfetch)
        cmd += ["--hidden-import", "truststore"]
    else:
        print("WARNING: no truststore package: BeamNG.Earth 1.7 checks HTTPS with certifi's bundle instead")
    sys.path.insert(0, server)
    import peerwork                                  # (BeamNG.Earth's code fingerprint, as its own build writes it)
    with open(os.path.join(work, "CODE_ID"), "w", encoding="ascii") as f:
        f.write(peerwork.source_id(server))
    cmd += ["--add-data", f"{os.path.join(work, 'CODE_ID')}{SEP}."]
    import revisit                                   # (1.8: the revisit cache's own fingerprint, as its build writes it:
    if hasattr(revisit, "source_id"):                # the modules its items are made with; else CODE_ID, all of it)
        with open(os.path.join(work, "REVISIT_ID"), "w", encoding="ascii") as f:
            f.write(revisit.source_id(server))
        cmd += ["--add-data", f"{os.path.join(work, 'REVISIT_ID')}{SEP}."]
    for name in ("LICENSE", "CREDITS.md"):          # (BeamNG.Earth's licence and data credits, as its own .exe has them)
        if os.path.isfile(os.path.join(earth, name)):
            cmd += ["--add-data", f"{os.path.join(earth, name)}{SEP}."]
    vf, mf = version_files(work, ver, earth_ver)
    cmd += ["--version-file", vf, "--manifest", mf]
    root = sorted({"launcher", "install", "apppaths", "bmplaunch"} |   # (and any other module beside the launcher: 1.9's
                  {os.path.splitext(n)[0] for n in os.listdir(earth)      # skypatch, the 3D map's sky from orbit)
                   if n.endswith(".py") and n not in ("start.py", "setup.py")})
    for m in mods + root:
        cmd += ["--hidden-import", m]
    for m in stdlib_imports(staged):
        cmd += ["--hidden-import", m]
    pyd = os.path.join(server, "earthfast.pyd")
    if os.path.isfile(pyd):
        cmd += ["--add-binary", f"{pyd}{SEP}."]
    else:
        print("WARNING: no server/earthfast.pyd (BeamNG.Earth's Rust kernels): the server needs it")
    cmd.append(os.path.join(staged, "app_launcher.py"))
    env = dict(os.environ)
    lib = os.path.join(sys.prefix, "Library", "bin")      # (a conda-forge Python's DLLs: OpenSSL, libffi, ...)
    if os.path.isdir(lib):
        env["PATH"] = lib + os.pathsep + env.get("PATH", "")
    log = os.path.join(work, "pyinstaller.log")
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run(cmd, check=True, cwd=earth, env=env, stdout=f, stderr=subprocess.STDOUT)
    with open(log, encoding="utf-8", errors="replace") as f:
        missing = [ln.strip() for ln in f if "Library not found" in ln and "api-ms-win" not in ln]
    if missing:
        sys.exit("DLLs the .exe needs were not found (" + log + "):\n  " + "\n  ".join(missing))
    return os.path.join(work, "dist", NAME + ".exe")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--earth", required=True, help="BeamNG.Earth's source folder (the version this release is for)")
    ap.add_argument("--bootloader", help="a PyInstaller run.exe built from source")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--any-earth", action="store_true", help="build with another BeamNG.Earth version (testing)")
    a = ap.parse_args()
    earth = os.path.abspath(a.earth)
    sys.path.insert(0, COMP)
    import setup_earth_source
    ev = earth_version(earth)
    if ev.lstrip("v") != setup_earth_source.EARTH_VERSION and not a.any_earth:
        sys.exit(f"BeamNG.Earth {ev} at {earth}: this release is made for {setup_earth_source.EARTH_VERSION}")
    work = os.path.join(ROOT, "build", "exe")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    os.makedirs(a.out, exist_ok=True)
    ver = version()
    if a.bootloader:
        print(f"bootloader: {a.bootloader} (built from source)")
    else:
        print("WARNING: PyInstaller's prebuilt bootloader (antivirus heuristics know it): pass --bootloader")
    staged = stage(work)
    exe = pyinstaller(work, earth, staged, make_icon(work), ver, ev, a.bootloader)
    out = os.path.join(a.out, f"{NAME}-{ver}.exe")
    shutil.copyfile(exe, out)
    print(f"built {out} ({os.path.getsize(out) / 1e6:.0f} MB)")
    if os.name == "nt":                 # the course painter in the server and its worker processes (app_launcher)
        r = subprocess.run([out, "--selftest"], capture_output=True, text=True, timeout=600)
        print("selftest:", (r.stdout or r.stderr).strip()[-600:])
        if r.returncode != 0:
            sys.exit("the .exe's selftest failed")


if __name__ == "__main__":
    main()
