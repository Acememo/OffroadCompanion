#!/usr/bin/env python3
"""Offroad Companion's helper program (the companion server).

The game's Lua cannot reach the internet (and its UI browser refuses every http request), so like BeamNG.Earth's
own server this small one runs on this PC and the game talks to it over a local socket (127.0.0.1:47614, the same
length-prefixed JSON framing as BeamNG.Earth). It answers:

    hello                                   -> hello {version, sources, tracksDir}
    route {id, lat0, lon0, lat1, lon1, bearing?, lang?}
                                            -> route_result {id, points, dist, dur, steps[]} | {id, error}
    track_list {id, source, lat?, lon?, q?, radius?}
                                            -> track_list_result {id, source, items[], note} | {id, error}
    track_get {id, source, ref}             -> track_result {id, track} | {id, error}
    paint {id, enabled, trackId, scale, paint?, clear?, points?}
                                            -> paint_result {id, painting, painter, need?}: the course BeamNG.Earth's
                                               server paints dirt tracks along (gpsd/paintfile.py, earthpatch.py)
    paint_status {id}                       -> paint_result {id, painter}
    paint_near {id, trackId, scale, lat, lon, have[]}
                                            -> paint_near_result {id, cid, windows [{k, pieces}], pending} | {need}:
                                               the dirt track planned here (gpsd/paintsource.py), for a BeamNG.Earth
                                               without the server painter (its .exe): the game draws it

Run it next to BeamNG.Earth's server:  python3 earth_gpsd.py   (Python 3.9+, standard library only)
"""
import argparse
import asyncio
import concurrent.futures
import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gpsd import courseroads, geocode, paintfile, paintsource, protocol, routing, sources, spots, streets  # noqa: E402
from gpsd import terrain, urban, wetness  # noqa: E402
from gpsd import trackparse  # noqa: E402
from gpsd.fetch import VERSION, Fetcher, FetchError  # noqa: E402

# what this companion answers beyond the first version's messages (the game asks only for what it is told is here)
FEATURES = ["route_clear", "streets", "track_save", "geocode", "pose", "course_sides", "terrain_snapshot", "wetness",
            "ground_code"]


def bundled_mod_build(path=None):
    """The build of the Offroad Companion mod shipped with this companion (OffroadCompanion/mod/offroad_companion.zip: main.lua's M.BUILD), or
    None: the app says so when the game runs an older one."""
    import re
    import zipfile
    path = path or os.path.join(HERE, "mod", "offroad_companion.zip")
    try:
        with zipfile.ZipFile(path) as z:
            src = z.read("lua/ge/extensions/offroadCompanion/main.lua").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    m = re.search(r"M\.BUILD\s*=\s*'([^']+)'", src)
    return m.group(1) if m else None
POSE_EVERY_S = 1.5          # the pose file written at most this often

log = logging.getLogger("earth_gpsd")
DEFAULT_PORT = 47614


def _num(v, lo=None, hi=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or (lo is not None and f < lo) or (hi is not None and f > hi):
        return None
    return f


def _safe_name(name):
    keep = "".join(ch if (ch.isalnum() or ch in " -_.()") else "_" for ch in name).strip(" .")
    return keep[:60] or "My track"


def save_gpx(tracks_dir, name, points, checkpoints=()):
    """Write points ([[lat, lon]...], at least 2) as tracks_dir/<name>.gpx (a number added when the name is taken):
    {ref, path, name}."""
    from xml.sax.saxutils import escape
    pts = [(float(a), float(b)) for a, b in points]
    if len(pts) < 2:
        raise ValueError("a track needs at least two points")
    for la, lo in pts:
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            raise ValueError("a point is off the Earth")
    base = _safe_name(name)
    os.makedirs(tracks_dir, exist_ok=True)
    fn, n = f"{base}.gpx", 2
    while os.path.exists(os.path.join(tracks_dir, fn)):
        fn, n = f"{base} ({n}).gpx", n + 1
    wpts = [("Start", pts[0]), ("Finish", pts[-1])]
    for c in checkpoints or []:
        try:
            wpts.append((str(c.get("name") or "CP"), (float(c["lat"]), float(c["lon"]))))
        except (KeyError, TypeError, ValueError):
            continue
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="Offroad Companion" xmlns="http://www.topografix.com/GPX/1/1">',
             f"<metadata><name>{escape(base)}</name></metadata>"]
    for wn, (la, lo) in wpts:
        lines.append(f'<wpt lat="{la:.7f}" lon="{lo:.7f}"><name>{escape(wn)}</name></wpt>')
    lines.append(f"<trk><name>{escape(base)}</name><trkseg>")
    lines += [f'<trkpt lat="{la:.7f}" lon="{lo:.7f}"/>' for la, lo in pts]
    lines.append("</trkseg></trk></gpx>")
    path = os.path.join(tracks_dir, fn)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(path + ".tmp", path)
    return {"ref": fn, "path": path, "name": base}


def earth_version():
    """The BeamNG.Earth the painter runs in (its folder, remembered by start_earth_with_tracks), or None."""
    cfg = paintfile.read_json(os.path.join(paintfile.base_dir(), "launcher.json")) or {}
    return terrain.earth_version(cfg.get("earth"))


def prune_snapshots(keep=None):
    """The newest paintfile.SNAPSHOTS_KEEP snapshots kept, older ones removed."""
    import shutil
    keep = paintfile.SNAPSHOTS_KEEP if keep is None else keep
    root = paintfile.snapshots_dir()
    try:
        dirs = [os.path.join(root, d) for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
    except OSError:
        return
    dirs.sort(key=lambda d: os.path.getmtime(d), reverse=True)
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)


def danger_points(track):
    """The course file's DANGER waypoints [[lat, lon]] (the server's "auto" relief roughens the course there)."""
    out = []
    for w in (track or {}).get("waypoints") or ():
        try:
            if w.get("kind") == "danger":
                out.append([round(float(w["lat"]), 7), round(float(w["lon"]), 7)])
        except (TypeError, ValueError, KeyError, AttributeError):
            pass
    return out


class Server:
    def __init__(self, fetcher, tracks_dir):
        self.fetcher = fetcher
        self.tracks_dir = tracks_dir
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="gpsd")
        self.tracks = {}            # track id -> track (the last few loaded: what paint names)
        self.painter = paintsource.Painter(fetcher)
        self.plan = {"course": None, "route": None}     # what BeamNG.Earth's server clears / paints (paintfile)
        self.streets = streets.Streets(fetcher)
        self.urban = urban.Urban(fetcher)            # (how urban the course is along it: the Lots crowds)

    # -- blocking handlers (run in the pool) -----------------------------------------------------------------
    def do_route(self, m):
        out = {"type": "route_result", "id": m.get("id")}
        lat0, lon0 = _num(m.get("lat0"), -90, 90), _num(m.get("lon0"), -180, 180)
        lat1, lon1 = _num(m.get("lat1"), -90, 90), _num(m.get("lon1"), -180, 180)
        if None in (lat0, lon0, lat1, lon1):
            out["error"] = "bad coordinates"
            return out
        b = _num(m.get("bearing"))
        try:
            out.update(routing.plan(self.fetcher, lat0, lon0, lat1, lon1, b, m.get("lang") or "en"))
        except (FetchError, ValueError) as e:
            out["error"] = str(e)
        return out

    def _ctx(self, m):
        return {"lat": _num(m.get("lat"), -90, 90), "lon": _num(m.get("lon"), -180, 180),
                "q": str(m.get("q") or "")[:100], "radius": _num(m.get("radius"), 100, 200000)}

    def do_track_list(self, m):
        src = str(m.get("source") or "")
        out = {"type": "track_list_result", "id": m.get("id"), "source": src}
        try:
            out.update(sources.list_items(src, self.fetcher, self._ctx(m), self.tracks_dir))
        except (FetchError, ValueError, trackparse.TrackError) as e:
            out["error"] = str(e)
            out["items"] = []
        except Exception as e:                       # a site changed its pages: say so, keep serving
            log.exception("track_list %s", src)
            out["error"] = f"{src}: {e}"
            out["items"] = []
        return out

    def do_track_get(self, m):
        src, ref = str(m.get("source") or ""), str(m.get("ref") or "")
        out = {"type": "track_result", "id": m.get("id"), "source": src, "ref": ref}
        try:
            t = sources.get(src, ref, self.fetcher, self._ctx(m), self.tracks_dir)
            t["id"] = f"{src}:{ref}"
            out["track"] = t
            self.tracks[t["id"]] = t
            while len(self.tracks) > 4:
                self.tracks.pop(next(iter(self.tracks)))
            log.info("track %s: %s, %d points, %d waypoints, %.1f km", t["id"], t["name"], len(t["points"]),
                     len(t["waypoints"]), t["length"] / 1000)
        except (FetchError, ValueError, trackparse.TrackError) as e:
            out["error"] = str(e)
        except Exception as e:
            log.exception("track_get %s %s", src, ref)
            out["error"] = f"could not read that course: {e}"
        return out

    def do_paint(self, m):
        out = {"type": "paint_result", "id": m.get("id")}
        if m.get("type") == "paint":
            enabled = bool(m.get("enabled"))
            do_paint, do_clear = m.get("paint", True) is not False, m.get("clear", True) is not False
            tid = str(m.get("trackId") or "")
            scale = _num(m.get("scale"), 0.5, 2.0) or 1.0
            ruts = str(m.get("ruts") or "auto")
            ruts = ruts if ruts in ("auto", "on", "off") else "auto"
            rough = str(m.get("rough") or "on")
            rough = rough if rough in ("off", "mild", "on", "extra", "auto", "default") else "on"
            # a replay's ground: the snapshot made when it was recorded (its course too, if not loaded now) and the
            # terrain version it was made with
            pin = paintfile.snapshot_name(m.get("pin")) if m.get("pin") else None
            snap = None
            if pin:
                snap = paintfile.read_json(os.path.join(paintfile.snapshots_dir(pin), "meta.json"))
                if not isinstance(snap, dict):
                    out["pinMissing"] = pin
                    pin, snap = None, None
            tv = m.get("tv")
            if enabled:
                t = self.tracks.get(tid)
                if t is None and snap and snap.get("points") and (snap.get("trackId") or "") == tid:
                    t = {"points": snap["points"], "name": snap.get("name") or "Course", "approximate": False,
                         "waypoints": [{"kind": "danger", "lat": a, "lon": b} for a, b in snap.get("dangers") or ()]}
                points, name = (t["points"], t["name"]) if t else (m.get("points"), m.get("name"))
                if not t and points:            # (a restarted companion: the game sent them; paint_near needs them)
                    self.tracks[tid] = {"points": points, "name": name or "Course", "approximate": False}
                if t and t.get("approximate"):
                    points = None           # a rough line between race-mile markers: nothing to paint along
                if not points:
                    if t or m.get("points") is not None:
                        out["error"] = "this course has no course line to paint along"
                        enabled = False
                    else:
                        out["need"] = tid   # (a companion restarted since the course was loaded)
                        out["painter"] = paintfile.painter_status()
                        return out
            try:
                if enabled:
                    self.plan["course"] = {"kind": "course", "points": [[float(a), float(b)] for a, b in points],
                                           "name": name or "Course", "scale": scale, "paint": do_paint,
                                           "clear": do_clear, "trackId": tid, "ruts": ruts, "rough": rough,
                                           "dangers": danger_points(t)}
                    if snap and snap.get("dangers") is not None:
                        self.plan["course"]["dangers"] = snap["dangers"]      # (as recorded)
                    if pin:
                        self.plan["course"]["pin"] = pin
                    if tv is not None:
                        self.plan["course"]["tv"] = int(tv)
                    log.info("course for BeamNG.Earth: %s (%d points, track size %.2f, dirt track %s, clear %s)", name,
                             len(points), scale, "on" if do_paint else "off", "on" if do_clear else "off")
                else:
                    self.plan["course"] = None
                self.write_plan()
                out["painting"] = enabled
            except (OSError, TypeError, ValueError) as e:
                out["error"] = f"could not write the course for BeamNG.Earth: {e}"
        out["painter"] = paintfile.painter_status()
        out["paintFile"] = paintfile.course_path()
        c = self.plan.get("course")
        if c:
            out["seal"] = self.seal_of(c)
            out["code"] = self.code_of(c)
            out["terrain"] = terrain.VERSION
            out["earth"] = earth_version()
            out["terrains"] = list(terrain.VERSIONS)
        return out

    def seal_of(self, c):
        """The seal of plan line c (terrain.seal): the same seal, the same ground."""
        cid = courseroads.course_id(c["points"], float(c.get("scale") or 1.0), c.get("tv"))
        return terrain.seal(cid, c.get("paint", True), c.get("clear", True), c.get("rough") or "on",
                            c.get("ruts") or "auto", c.get("dangers") or (), c.get("tv") or terrain.VERSION,
                            earth_version())

    def code_of(self, c):
        """The ground code to share of plan line c (terrain.share_code): its seal and the settings that made it."""
        return terrain.share_code(self.seal_of(c), c.get("paint", True), c.get("clear", True), c.get("rough") or "on",
                                  c.get("ruts") or "auto", c.get("scale") or 1.0, c.get("tv") or terrain.VERSION,
                                  earth_version())

    def do_ground_code(self, m):
        """A ground code a friend shared (terrain.parse_share), pasted with the same course loaded: {ok, settings}
        (the settings that give its seal here: the game applies them and paints again), or {error} saying why not
        (another course, another BeamNG.Earth version, a terrain version this companion can't make)."""
        out = {"type": "ground_code_result", "id": m.get("id")}
        got = terrain.parse_share(m.get("code"))
        c = self.plan.get("course")
        if got is None:
            out["error"] = "that is not a ground code (it looks like T3-1a2b3c-0D8G0Z810R1G4)"
            return out
        if not c:
            out["error"] = "load the course first (with its dirt track on), then paste the code"
            return out
        if "tv" not in got:
            same = self.seal_of(c) == got["seal"]
            out.update({"ok": same, "same": same})
            if not same:
                out["error"] = ("that is only the short code (the seal): ask for the whole code from Settings' Copy, "
                                "or match the settings by hand")
            return out
        if got["tv"] not in terrain.VERSIONS:
            out["error"] = (f"that code is from terrain version {got['tv']}, which this Offroad Companion can't make: "
                            "update Offroad Companion")
            return out
        want = dict(c, paint=got["paint"], clear=got["clear"], rough=got["rough"], ruts=got["ruts"],
                    scale=got["scale"], tv=got["tv"])
        if self.seal_of(want) != got["seal"]:
            mine = earth_version()
            if got.get("earth") and mine and got["earth"] != mine:
                out["error"] = (f"that code was made with BeamNG.Earth {got['earth']} (you have {mine}): its own ground "
                                "differs; use the same BeamNG.Earth version")
            else:
                out["error"] = "that code is for another course (or another file of it): load the same course"
            return out
        out.update({"ok": True, "settings": {k: got[k] for k in ("paint", "clear", "rough", "ruts", "scale", "tv")},
                    "seal": got["seal"]})
        return out

    def do_terrain_snapshot(self, m):
        """The course's ground as it is planned now (its windows, as BeamNG.Earth's server wrote them) kept under
        m["name"] for a replay: played back later, the server uses exactly these (paint with pin)."""
        out = {"type": "terrain_snapshot_result", "id": m.get("id")}
        c = self.plan.get("course")
        name = paintfile.snapshot_name(m.get("name"))
        if not c or not name:
            out["error"] = "no course" if not c else "no name"
            return out
        try:
            tv = c.get("tv")
            cid = courseroads.course_id(c["points"], float(c.get("scale") or 1.0), tv)
            src = paintfile.windows_dir(cid)
            dst = paintfile.snapshots_dir(name)
            os.makedirs(dst, exist_ok=True)
            n = 0
            for fn in sorted(os.listdir(src)) if os.path.isdir(src) else ():
                if fn.endswith(".json") and fn[:1] in ("w", "r") and not fn.startswith(".tmp"):
                    obj = paintfile.read_json(os.path.join(src, fn))
                    if obj is not None:
                        paintfile.write_json(os.path.join(dst, fn), obj)
                        n += 1
            seal = self.seal_of(c)
            meta = {"version": 1, "cid": cid, "seal": seal, "tv": int(tv or terrain.VERSION), "made": time.time(),
                    "earth": earth_version(),
                    "trackId": c.get("trackId"), "name": c.get("name"), "points": c["points"],
                    "scale": c.get("scale"), "paint": c.get("paint", True), "clear": c.get("clear", True),
                    "ruts": c.get("ruts"), "rough": c.get("rough"), "dangers": c.get("dangers") or [],
                    "windows": n}
            paintfile.write_json(os.path.join(dst, "meta.json"), meta)
            prune_snapshots()
            out.update({"ok": True, "seal": seal, "windows": n, "cid": cid})
            log.info("terrain snapshot %s: %d window file(s) of %s (%s)", name, n, c.get("name"), seal)
        except OSError as e:
            out["error"] = f"could not keep the ground: {e}"
        return out

    def write_plan(self):
        lines = [x for x in (self.plan.get("course"), self.plan.get("route")) if x]
        paintfile.write_plan(lines)

    def do_route_clear(self, m):
        """The GPS road route the player follows: cleared like a course (buildings in its lanes, walls across it, low
        overpasses), never painted."""
        out = {"type": "route_clear_result", "id": m.get("id")}
        pts = m.get("points") or []
        try:
            if m.get("enabled") and len(pts) >= 2:
                self.plan["route"] = {"kind": "route", "points": [[float(a), float(b)] for a, b in pts],
                                      "name": str(m.get("name") or "GPS route"), "paint": False, "clear": True}
                log.info("route for BeamNG.Earth: %s (%d points), cleared of blockages", self.plan["route"]["name"],
                         len(pts))
            else:
                self.plan["route"] = None
            self.write_plan()
            out["clearing"] = self.plan["route"] is not None
        except (OSError, TypeError, ValueError) as e:
            out["error"] = f"could not write the route for BeamNG.Earth: {e}"
        out["painter"] = paintfile.painter_status()
        return out

    def do_streets(self, m):
        out = {"type": "streets_result", "id": m.get("id")}
        lat, lon = _num(m.get("lat"), -90, 90), _num(m.get("lon"), -180, 180)
        if lat is None or lon is None:
            out.update(tiles=[], pending=0)
            return out
        out.update(self.streets.near(lat, lon, _num(m.get("radius"), 100, 20000) or 1500, m.get("have") or []))
        out["attribution"] = "Streets (c) OpenStreetMap contributors (ODbL)"
        return out

    def on_pose(self, m):
        """Where the car is, for BeamNG.Earth's server: its course painter plans the dirt track around it in the
        background (earthpatch prefetch), so road data is ready before the world streams in there."""
        lat, lon = _num(m.get("lat"), -90, 90), _num(m.get("lon"), -180, 180)
        now = time.time()
        jump = bool(m.get("jump"))      # (a teleport about to happen: where the car is going, at once)
        if lat is None or lon is None or (not jump and now - getattr(self, "_pose_at", 0.0) < POSE_EVERY_S):
            return
        self._pose_at = now
        self.preload_circuits(lat, lon)
        try:
            paintfile.write_json(paintfile.pose_path(), {"lat": lat, "lon": lon, "speed": _num(m.get("speed"), 0, 500),
                                                         "heading": _num(m.get("heading"), -360, 720), "t": now})
        except OSError:
            pass

    def preload_circuits(self, lat, lon):
        """OpenStreetMap's circuits around the car fetched in the background (when its area changes), so the Courses
        list shows at once instead of waiting on busy Overpass servers (the user, 2026-10-22)."""
        from gpsd.sources import osm
        key = osm.area(lat, lon, osm.DEFAULT_RADIUS)[:2]
        if key == getattr(self, "_preload_key", None) or getattr(self, "_preloading", False) or \
                time.time() < getattr(self, "_preload_retry", 0.0):
            return
        self._preload_key, self._preloading = key, True

        def job():
            try:
                osm.preload(self.fetcher, lat, lon)
                log.info("circuits around %.2f, %.2f ready (OpenStreetMap)", key[0], key[1])
            except Exception as e:
                log.info("circuits around %.2f, %.2f not pre-loaded: %s", key[0], key[1], e)
                self._preload_key = None                    # (asked again in a couple of minutes)
                self._preload_retry = time.time() + 120.0
            finally:
                self._preloading = False
        self.pool.submit(job)

    def do_wetness(self, m):
        """How wet the ground is at (lat, lon) from the rain of the last days (gpsd/wetness.py): {w 0 .. 1, level,
        rainMmH, last24, ...}; w 0 when the weather service can't be reached (dry: nothing changes)."""
        lat, lon = _num(m.get("lat"), -90, 90), _num(m.get("lon"), -180, 180)
        if lat is None or lon is None:
            return {"type": "wetness_result", "id": m.get("id"), "error": "no position"}
        try:
            got = wetness.fetch(self.fetcher, lat, lon)
        except Exception as e:
            log.info("wetness: %s", e)
            return {"type": "wetness_result", "id": m.get("id"), "w": 0.0, "level": "dry", "error": str(e)}
        return dict(got, type="wetness_result", id=m.get("id"))

    def do_course_sides(self, m):
        """Where the painted course's track or road is (relief profiles the BeamNG.Earth server wrote, every 10 m):
        {step, i0, hw [half width m | null], ctr [the road's middle, m left of the course line | null]} for the samples
        from s0 to s1 (m along the course). The game's course signs stand beside the track, not on it (the user,
        2026-10-22: "sometimes the markers appear in the middle of the road")."""
        out = {"type": "course_sides_result", "id": m.get("id")}
        c = self.plan.get("course")
        if not c or not c.get("points"):
            out["error"] = "no course painted"
            return out
        from gpsd import courseroads
        key = (len(c["points"]), float(c.get("scale") or 1.0), tuple(c["points"][0]), tuple(c["points"][-1]),
               c.get("tv"))
        if getattr(self, "_sides_key", None) != key:
            self._sides_course = courseroads.Course([(float(a), float(b)) for a, b in c["points"]],
                                                    float(c.get("scale") or 1.0), tv=c.get("tv"))
            self._sides_key = key
        course = self._sides_course
        step = courseroads.STEP_M
        s0 = max(0.0, _num(m.get("s0"), -1e9, 1e9) or 0.0)
        s1 = min((course.n - 1) * step, _num(m.get("s1"), -1e9, 1e9) or 0.0)
        i0, i1 = int(s0 // step), int(s1 // step) + 1
        i1 = min(i1, course.n - 1)
        hw, ctr = [None] * max(0, i1 - i0 + 1), [None] * max(0, i1 - i0 + 1)
        pin = paintfile.snapshots_dir(c["pin"]) if c.get("pin") else None
        # (a margin either side for the crossings: dirt on both sides of a paved road is looked for that far)
        m = spots.CROSS_SIDE_N
        e0, e1 = max(0, i0 - m), min(course.n - 1, i1 + m)
        rough, rock = [None] * (e1 - e0 + 1), [None] * (e1 - e0 + 1)
        for k in range(e0 // courseroads.WINDOW, e1 // courseroads.WINDOW + 1):
            fn = f"r{k:06d}.json"
            prof = paintfile.read_json(os.path.join(pin, fn)) if pin else None      # (a replay's ground: as recorded)
            if not isinstance(prof, dict):
                prof = paintfile.read_json(os.path.join(paintfile.windows_dir(course.cid), fn))
            if not isinstance(prof, dict) or "ctr" not in prof:
                continue
            a = int(prof.get("a", 0))
            for j, (h, cc) in enumerate(zip(prof.get("hw") or [], prof.get("ctr") or [])):
                i = a + j
                if i0 <= i <= i1:
                    # (terrain 8: the samples on the course's rounded corners, bend m left of the file's line: the
                    # game counts from that line)
                    bend = course.bend[i] if i < len(getattr(course, "bend", ())) else 0.0
                    hw[i - i0], ctr[i - i0] = h, (round(cc + bend, 2) if cc is not None else cc)
            for j, (ru, rk) in enumerate(zip(prof.get("rough") or [], prof.get("rock") or [])):
                i = a + j
                if e0 <= i <= e1:
                    rough[i - e0], rock[i - e0] = ru, rk
        # where spectators gather on this stretch (gpsd/spots.py): the jumps the track terrain has, the paved crossings
        found = []
        for sx in spots.crossings(rough, e0):
            if s0 <= sx <= s1:
                found.append({"s": sx, "kind": "crossing"})
        if (c.get("rough") or "on") != "off" and c.get("paint", True) is not False:

            def rock_at(sv):
                i = int(round(sv / step)) - e0
                v = rock[i] if 0 <= i < len(rock) else None
                return 1.0 if v is None else v                  # (not planned yet: no jump said)

            def dirt_at(sv):
                i = int(round(sv / step)) - e0
                v = rough[i] if 0 <= i < len(rough) else None
                return v is not None and v >= 0.5
            for sx, size in spots.kicks(course.lat, course.lon, s0, s1, rock_at):
                if dirt_at(sx):
                    found.append({"s": sx, "kind": "jump", "size": size})
        found.sort(key=lambda f: f["s"])
        out.update({"step": step, "i0": i0, "hw": hw, "ctr": ctr, "cid": course.cid, "spots": found,
                    "spotsFrom": s0, "spotsTo": s1})
        # how urban the stretch is (gpsd/urban.py: towns along the course, for the Lots crowds): every urban.STEP_M,
        # from urbK0; null while the towns are being fetched (urbState 'pending'), 0 everywhere when they could not be
        try:
            out["urbState"] = self.urban.state(course.cid, course.lat, course.lon)
            k0, k1 = int(s0 // urban.STEP_M), int(s1 // urban.STEP_M) + 1
            out.update({"urbStep": urban.STEP_M, "urbK0": k0,
                        "urb": self.urban.values(course.lat, course.lon, k0, k1, step)})
        except Exception as e:
            log.debug("urban: %s", e)
        return out

    def do_geocode(self, m):
        """Search (geocode.py): {results [{name, detail, kind, lat, lon}], source, error?}."""
        out = {"type": "geocode_result", "id": m.get("id"), "q": str(m.get("q") or "")}
        out.update(geocode.search(self.fetcher, out["q"], _num(m.get("lat"), -90, 90), _num(m.get("lon"), -180, 180),
                                  str(m.get("lang") or "en"), bool(m.get("submitted"))))
        return out

    def do_track_save(self, m):
        """A track made in the game (points [[lat, lon]...], checkpoints [{name, lat, lon}]) saved as GPX in the tracks
        folder: {ok, ref (its name there, for track_get source 'local'), path}."""
        out = {"type": "track_save_result", "id": m.get("id")}
        try:
            out.update(save_gpx(self.tracks_dir, str(m.get("name") or ""), m.get("points") or [],
                                m.get("checkpoints") or []))
            out["ok"] = True
            log.info("track saved: %s (%d points)", out["path"], len(m.get("points") or []))
        except (OSError, TypeError, ValueError) as e:
            out["ok"], out["error"] = False, str(e)
        return out

    def do_paint_near(self, m):
        out = {"type": "paint_near_result", "id": m.get("id"), "trackId": m.get("trackId")}
        t = self.tracks.get(str(m.get("trackId") or ""))
        lat, lon = _num(m.get("lat"), -90, 90), _num(m.get("lon"), -180, 180)
        if t is None:
            out["need"] = m.get("trackId")
            return out
        if t.get("approximate") or len(t.get("points") or []) < 2 or lat is None or lon is None:
            out.update(windows=[], pending=0)
            return out
        have = [int(k) for k in (m.get("have") or []) if isinstance(k, (int, float))]
        out.update(self.painter.near(t["points"], _num(m.get("scale"), 0.5, 2.0) or 1.0, t.get("name"), lat, lon, have))
        out["attribution"] = paintsource.ATTRIBUTION
        return out

    # -- connection --------------------------------------------------------------------------------------------
    async def handle(self, reader, writer):
        peer = writer.get_extra_info("peername")
        log.info("game connected %s", peer)
        lock = asyncio.Lock()
        loop = asyncio.get_running_loop()

        async def send(msg):
            async with lock:
                writer.write(protocol.encode(msg))
                await writer.drain()

        async def run(fn, m):
            try:
                res = await loop.run_in_executor(self.pool, fn, m)
            except Exception as e:                   # never leave the game waiting
                log.exception("handler")
                res = {"type": (m.get("type") or "error") + "_result", "id": m.get("id"), "error": str(e)}
            try:
                await send(res)
            except (ConnectionError, RuntimeError):
                pass

        tasks = set()
        try:
            while True:
                m = await protocol.read_message(reader)
                if m is None:
                    break
                t = m["type"]
                if t == "hello":
                    await send({"type": "hello", "version": VERSION, "sources": sources.CATALOG,
                                "tracksDir": self.tracks_dir, "attribution": routing.ATTRIBUTION,
                                "painter": paintfile.painter_status(), "features": FEATURES,
                                "modBuild": bundled_mod_build()})
                elif t == "ping":
                    await send({"type": "pong", "id": m.get("id")})
                elif t == "pose":
                    self.on_pose(m)             # (no answer: the game sends it every few seconds)
                elif t in ("route", "track_list", "track_get", "paint", "paint_status", "paint_near", "route_clear",
                           "streets", "track_save", "geocode", "course_sides", "terrain_snapshot", "wetness",
                           "ground_code"):
                    fn = {"route": self.do_route, "track_list": self.do_track_list, "track_get": self.do_track_get,
                          "paint": self.do_paint, "paint_status": self.do_paint, "paint_near": self.do_paint_near,
                          "route_clear": self.do_route_clear, "streets": self.do_streets,
                          "track_save": self.do_track_save, "geocode": self.do_geocode,
                          "course_sides": self.do_course_sides, "terrain_snapshot": self.do_terrain_snapshot,
                          "wetness": self.do_wetness, "ground_code": self.do_ground_code}[t]
                    task = asyncio.ensure_future(run(fn, m))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                else:
                    await send({"type": "error", "id": m.get("id"), "error": f"unknown message type {t!r}"})
        except (protocol.ProtocolError, ConnectionError) as e:
            log.warning("connection dropped: %s", e)
        finally:
            for task in tasks:
                task.cancel()
            writer.close()
            log.info("game disconnected %s", peer)


async def main_async(args):
    os.makedirs(args.tracks_dir, exist_ok=True)
    srv = Server(Fetcher(args.cache_dir, offline=args.offline), args.tracks_dir)
    server = await asyncio.start_server(srv.handle, "127.0.0.1", args.port)
    port = server.sockets[0].getsockname()[1]
    log.info("Offroad Companion %s on 127.0.0.1:%d (tracks folder: %s)", VERSION, port, args.tracks_dir)
    async with server:
        await server.serve_forever()


def update_game_mod():
    """The Offroad Companion mod in the game's mods folder kept to this companion's copy (and other copies of it moved aside), when the
    user folder is known (start_earth_with_tracks / setup_earth_source remember it): an updated companion folder then
    updates the game's app too."""
    if os.environ.get("OFFROAD_COMPANION_APP"):    # (the .exe put it there just before: app_launcher.py)
        return
    try:
        cfg = paintfile.read_json(os.path.join(paintfile.base_dir(), "launcher.json")) or {}
        user_dir = cfg.get("user_dir")
        if user_dir and os.path.isdir(user_dir):
            import setup_earth_source
            setup_earth_source.install_gps_mod(user_dir)
    except Exception as e:                      # never keeps the companion from starting
        log.warning("Offroad Companion mod not updated in the game's mods folder: %s", e)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--tracks-dir", default=os.path.join(HERE, "tracks"))
    ap.add_argument("--cache-dir", default=os.path.join(HERE, "cache"))
    ap.add_argument("--offline", action="store_true", help="only use cached downloads")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--log-prefix", default="", help="put before every line (started in BeamNG.Earth's window: GPS)")
    args = ap.parse_args(argv)
    pre = f"[{args.log_prefix}] " if args.log_prefix else ""
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format=f"%(asctime)s {pre}%(levelname)s %(message)s", datefmt="%H:%M:%S")
    update_game_mod()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass
    except OSError as e:
        log.error("cannot listen on 127.0.0.1:%d (%s). Is the companion already running?", args.port, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
