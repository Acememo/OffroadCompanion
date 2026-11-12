"""The course's ground: its version and its seal (the user, 2026-10-22: "it needs to be more deterministic ... especially
important not only for replays but also for when it gets combined with BeamMP so everyone races the exact same track
down to every bump and dip, everything the same every time").

What shapes the ground along a course, given BeamNG.Earth's own data (its pinned Overture release, the Mapterhorn DEM,
the canopy and land cover releases):
  - the course line and the track size (courseroads.course_id),
  - the settings: dirt track on / off, corridor cleared or not, ruts, track terrain (rough), the DANGER waypoints
    (auto),
  - the code that turns them into ground: courseroads (the track's pieces), relief (the bumps, dips and rocks),
    earthpatch's glue. Its version is VERSION.

The rule (for whoever changes that code): the ground of a VERSION never changes. A change that moves a single bump
makes VERSION + 1, keeps the old behaviour reachable for the old version (a course carries its version: Course.tv;
`if course.tv >= N:`), and adds the new version's fingerprint to tests/test_terrain.py (the golden test: it computes
every version's pieces, profiles, heights and rocks for a fixed course and compares them with the stored ones, so a
change that would move anything fails there first). Replays and races name the version their ground was made with.

seal(): a short code naming one ground: the same seal, the same ground (on any computer with the same BeamNG.Earth
data). Pure Python.
"""
import hashlib

VERSION = 13                # (2: natural cut banks beside the track where BeamNG.Earth stood a bare step: banks.py;
                            # 3: the ground's surfaces along the course, sand, mud, loose and packed dirt: surfaces.py;
                            # 4: the track round the trees, courseroads.weave_shifts; grass and scrub on the track
                            # where the land around has them, the wheel paths bare: surfaces.py; washes rarer and
                            # shallower, a flat floor between eased banks, the DANGER ditches too: relief.dip;
                            # 5: banked corners on rough ground, rutted sections: relief.bank_weight, rut_weight;
                            # 6: every shape at least ~3 cells of the game's 2 m lattice wide, no creases: relief.SMOOTH_TV;
                            # 7: the track's sections where the place has them, sand traps, rock sections, gravel, rock
                            # crawls at some canyon DANGER waypoints: variety.py;
                            # 8: the course's corners rounded to arcs, wider tracks: courseroads.CURVES_TV;
                            # 9: Baja's rough sections rarer, the rougher the rarer, and softer on a mapped dirt road
                            # BeamNG.Earth 1.8.2 wears too (not at the DANGER waypoints): relief.AUTO_TV;
                            # 10: those roads no longer worn by BeamNG.Earth (earthpatch.followed_rows), so as rough as
                            # the course's own track again, 9's shares kept: relief.UNWORN_TV;
                            # 11: no boulder on a road (relief.rocks_off_roads: ROCKS_OFF_ROADS_TV), a run that leaves
                            # or joins a paved road meets its edge, not its middle: courseroads.PAVED_EDGE_TV;
                            # 12: the track's relief never on a paved road or its shoulder: relief.paved_clear;
                            # 13: a dip under a low bridge the track passes under, a ramp where the course comes off
                            # a paved road cut into the ground (or raised over it): shaping.py)
VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)  # the versions this code can still make


def seal(cid, paint=True, clear=True, rough="on", ruts="auto", dangers=(), tv=VERSION, earth=None):
    """'T<version>-<6 hex>' for the ground of course cid (courseroads.course_id) with these settings; dangers
    [(lat, lon)] (only "auto" uses them); earth: BeamNG.Earth's version (its own ground changes between versions:
    1.6 levels roads and draws them differently), None when not known."""
    dk = ";".join(f"{float(a):.5f},{float(b):.5f}" for a, b in (dangers or ())) if rough == "auto" else ""
    text = f"{int(tv)}|{cid}|{int(bool(paint))}{int(bool(clear))}|{rough}|{ruts}|{dk}"
    if earth:
        text += f"|E{earth}"
        if _earth_bytes(earth)[:3] >= bytes([1, 8, 2]):
            text += "|W2"           # (1.8.2's dirt road wear as the setting has it, also off the roads the course follows)
    return f"T{int(tv)}-{hashlib.sha1(text.encode()).hexdigest()[:6]}"


def earth_version(root):
    """BeamNG.Earth's version from its folder (its VERSION file), or None."""
    import os
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as f:
            v = f.read().strip()
        return v or None
    except (OSError, TypeError):
        return None


# -- the ground code to share (the user, 2026-10-28: "could you let people share terrain code so someone else can paste
# it on his settings while the same track is already loaded so they for sure get the exact same track?") ------------
# The seal names a ground; the code shared is the seal with the settings that made it, so a friend who pastes it into
# the app on the same course gets those settings (track size, track terrain, ruts, dirt track, cleared course, the
# terrain version) and the same seal back: 'T3-ea6a63-<SETTINGS>'. SETTINGS: B32 (Crockford's base 32, no padding) of
# bytes: terrain version, flags (dirt track, cleared, track terrain, ruts), track size x 100 (2), BeamNG.Earth's
# version (major, minor, patch, suffix).
B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ROUGHS = ("on", "off", "mild", "extra", "auto", "default")
RUTS = ("auto", "on", "off")
EARTH_SUFFIXES = ("", "-beta", "-preview")


def _b32(data):
    bits = "".join(f"{b:08b}" for b in data)
    bits += "0" * (-len(bits) % 5)
    return "".join(B32[int(bits[i:i + 5], 2)] for i in range(0, len(bits), 5))


def _unb32(text, nbytes):
    bits = ""
    for ch in text.upper().replace("O", "0").replace("I", "1").replace("L", "1"):
        k = B32.find(ch)
        if k < 0:
            return None
        bits += f"{k:05b}"
    if len(bits) < nbytes * 8:
        return None
    return bytes(int(bits[i:i + 8], 2) for i in range(0, nbytes * 8, 8))


def _earth_bytes(earth):
    import re
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(.*)$", str(earth or "").strip())
    if not m:
        return bytes(4)
    suf = m.group(4)
    return bytes([min(255, int(m.group(1))), min(255, int(m.group(2))), min(255, int(m.group(3))),
                  EARTH_SUFFIXES.index(suf) + 1 if suf in EARTH_SUFFIXES else 255])


def _earth_text(b):
    if not any(b):
        return None
    suf = EARTH_SUFFIXES[b[3] - 1] if 1 <= b[3] <= len(EARTH_SUFFIXES) else ""
    return f"{b[0]}.{b[1]}.{b[2]}{suf}"


def share_code(seal_, paint=True, clear=True, rough="on", ruts="auto", scale=1.0, tv=VERSION, earth=None):
    """The ground code to share: seal_ (seal()) and the settings that made it. Pure."""
    flags = (1 if paint else 0) | (2 if clear else 0) | (ROUGHS.index(rough if rough in ROUGHS else "on") << 2) | \
        (RUTS.index(ruts if ruts in RUTS else "auto") << 5)
    sc = max(0, min(65535, int(round(float(scale or 1.0) * 100))))
    data = bytes([max(0, min(255, int(tv))), flags, sc >> 8, sc & 255]) + _earth_bytes(earth)
    return f"{seal_}-{_b32(data)}"


def parse_share(code):
    """{seal, tv, paint, clear, rough, ruts, scale, earth} of a shared ground code, {seal} alone for a bare seal
    ('T3-ea6a63': nothing to apply, only to compare), None when it is not one. Pure."""
    import re
    m = re.match(r"^\s*T(\d+)-([0-9a-fA-F]{6})(?:-([0-9A-Za-z]+))?\s*$", str(code or ""))
    if not m:
        return None
    seal_ = f"T{int(m.group(1))}-{m.group(2).lower()}"
    if not m.group(3):
        return {"seal": seal_}
    data = _unb32(m.group(3), 8)
    if data is None:
        return None
    tv, flags = data[0], data[1]
    r, u = (flags >> 2) & 7, (flags >> 5) & 3
    if tv != int(m.group(1)) or r >= len(ROUGHS) or u >= len(RUTS):
        return None
    return {"seal": seal_, "tv": tv, "paint": bool(flags & 1), "clear": bool(flags & 2), "rough": ROUGHS[r],
            "ruts": RUTS[u], "scale": ((data[2] << 8) | data[3]) / 100.0, "earth": _earth_text(data[4:8])}
