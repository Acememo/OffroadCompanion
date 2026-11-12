"""Installs the course painter into a BeamNG.Earth server process (run by earth_tracks_server.py, in the server's
own Python with server/ on sys.path; every spawned worker process installs it again when it imports that script).

The hook is mapdata.MapData.cell. When a course is set (paintfile.course_path, written by the Offroad Companion):
  - paint: a cell's "roads" come back with the course's dirt-track pieces added (courseroads.py);
  - clear: short bridges the course crosses off-road become ground roads there, and the cell's "buildings" and
    "building_parts" come back without the ones on the course (corridor.py); roads.retaining_walls leaves out the
    walls along it.
Everything in BeamNG.Earth that reads the map through cell() then has them: the road tiles, the ground grading, the
surface masks, the trees and buildings kept off roads, the far tiles.

The course file is checked at most every CHECK_S; pieces are computed per course window once per process (and kept
on disk for the other processes); a cell's merged roads are kept for MEMO cells. Any failure leaves the cell's
roads as BeamNG.Earth made them.
"""
import logging
import multiprocessing
import hashlib
import math
import os
import sys
import threading
import time
from collections import OrderedDict

import numpy as np

from . import banks, corridor, courseroads, paintfile, relief, ruts, surfaces, terrain, variety

log = logging.getLogger("earthd.offroad")

CHECK_S = 2.0
MEMO = 512
ROUGH = {"off": 0.0, "mild": 0.55, "on": 1.0, "extra": 1.6, "auto": 1.0, "default": 0.0}     # the track's relief
# (relief.py), the player's setting ("auto", the app's Baja: each stretch its own, relief.course_auto; "default":
# none of the painter's, the track as BeamNG.Earth makes a track: install_course_grade)
HEARTBEAT_S = 20.0
RETRY_S = 30.0
# A window a build needs (kind DEMAND_KINDS: the ground, the road tiles, the vegetation being built now) is waited for:
# planned here, or by the process planning it already (a lock file beside it), up to DEMAND_WAIT_S, tried again after a
# failure (its data still coming). Only past that is the ground built without it (logged), and for DEMAND_GIVEUP_S
# after that the builds there do not wait again (offline). _planned.
DEMAND_KINDS = ("demand", "urgent")
DEMAND_WAIT_S = 45.0
DEMAND_GIVEUP_S = 30.0
POLL_S = 0.2
SLOW_PLAN_S = 3.0           # a demand read that took this long is logged (how long builds waited for the course)
PLAN_LOCK_STALE_S = 30.0    # a lock file not touched this long is a planner gone (its process stopped mid-plan) ...
PLAN_LOCK_TOUCH_S = 5.0     # ... its planner touches it this often while it plans

_state = None


_EARTH_VERSION = []


def _earth_version():
    """The BeamNG.Earth this server is (its VERSION, beside its server folder), or None."""
    if not _EARTH_VERSION:
        root = os.environ.get("EARTHGPS_EARTH_ROOT")
        if not root:
            try:
                import earthd
                root = os.path.dirname(os.path.dirname(os.path.abspath(earthd.__file__)))
            except Exception:
                root = None
        _EARTH_VERSION.append(terrain.earth_version(root) if root else None)
    return _EARTH_VERSION[0]


def _pinned(course, fn, algo):
    """Window file fn of the snapshot the course is pinned to (a replay's ground), or None."""
    d = getattr(course, "pin", None)
    if not d:
        return None
    got = paintfile.read_json(os.path.join(d, fn))
    return got if isinstance(got, dict) and got.get("algo") == algo else None


def _try_lock(path):
    """Takes path's planning lock (path + ".lock", made exclusively): True when this process plans it now. A lock older
    than PLAN_LOCK_STALE_S is taken over; a folder where no lock can be made plans without one."""
    lp = path + ".lock"
    for _ in range(2):
        try:
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lp) <= PLAN_LOCK_STALE_S:
                    return False
            except OSError:
                continue                    # (released meanwhile: tried again)
            _remove(lp)                     # (a planner gone)
            continue
        except OSError:
            return True
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    return False


def _keep_lock(path):
    """Touches path's lock every PLAN_LOCK_TOUCH_S until the event returned is set (the planner is alive)."""
    done = threading.Event()

    def run():
        while not done.wait(PLAN_LOCK_TOUCH_S):
            try:
                os.utime(path + ".lock")
            except OSError:
                return
    threading.Thread(target=run, name="offroad-plan-lock", daemon=True).start()
    return done


def _unlock(path):
    _remove(path + ".lock")


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def dem_fallback(dem, lat, lon, zoom, tile=512):
    """True when a DEM tile under the points was served by the fallback source (BeamNG.Earth's Dem.served: AWS while
    Mapterhorn failed): its heights differ a little from the usual ones (a window planned on them says so)."""
    served = getattr(dem, "served", None)
    if not served or not len(lat):
        return False
    lat = np.clip(np.asarray(lat, np.float64), -85.05, 85.05)
    lon = np.asarray(lon, np.float64)
    w = (2 ** zoom) * tile
    fx = (lon / 360.0 + 0.5) * w - 0.5
    fy = (0.5 - np.arcsinh(np.tan(np.radians(lat))) / (2 * np.pi)) * w - 0.5
    keys = set()
    for ox in (0, 1):
        for oy in (0, 1):
            tx = (np.floor(fx).astype(np.int64) + ox) // tile
            ty = (np.floor(fy).astype(np.int64) + oy) // tile
            keys.update(zip(tx.tolist(), ty.tolist()))
    for x, y in keys:
        src = served.get((zoom, x, y))
        if src is not None and src != "mapterhorn":
            return True
    return False


TREE_CLEAR_M = 1.0          # trees, bushes and rocks kept this far past the track's edge


def rock_groups(items, veg_mod, lat, lon):
    """The rock model group for boulders at (lat, lon) in a vegetation cell: the one BeamNG.Earth's own rocks in that
    cell use most (they fit the place: its region and land cover), else desert rock in the dry North American west,
    else the plain rock. Pure."""
    n = len(lat)
    try:
        own = np.asarray(items.group)[np.asarray(items.kind) == veg_mod.KIND_ROCK] if len(items) else ()
    except Exception:
        own = ()
    if len(own):
        vals, counts = np.unique(np.asarray(own, np.int64), return_counts=True)
        best = vals[counts == counts.max()].min()           # (ties: the lowest: the same pick every time)
        return np.full(n, int(best), np.uint8)
    lat, lon = np.asarray(lat), np.asarray(lon)
    dry = (lon < -100.0) & (lat > 20.0) & (lat < 46.0)
    return np.where(dry, veg_mod.G_DESERT_ROCK, veg_mod.G_ROCK).astype(np.uint8)


class Plan:
    """What the course file asks for: lines (courseroads.Course, each with .paint, .clear, .clear_m, .kind): the race
    course (its dirt track painted, its corridor cleared) and the GPS road route (cleared only)."""

    def __init__(self, lines):
        self.lines = lines
        self.paint = next((c for c in lines if c.paint), None)      # the one line whose dirt track is painted
        self.clearing = [c for c in lines if c.clear]
        self.key = "/".join(c.key for c in lines)
        self.name = " + ".join(c.name for c in lines)


def _line(obj, defaults):
    pts = obj.get("points") or []
    if len(pts) < 2:
        return None
    c = courseroads.Course([(float(a), float(b)) for a, b in pts], float(obj.get("scale") or 1.0),
                           str(obj.get("name") or defaults.get("name") or "Course"), obj.get("tv"))
    if c.tv != c.tv_asked:
        log.warning("course painter: terrain version %s asked; this version makes %s", c.tv_asked, terrain.VERSIONS)
    c.kind = str(obj.get("kind") or defaults.get("kind") or "course")
    c.paint = obj.get("paint", defaults.get("paint", True)) is not False and c.kind == "course"
    c.clear = obj.get("clear", True) is not False
    c.clear_m = float(obj.get("clearM") or (corridor.CLEAR_M if c.kind == "course" else corridor.ROUTE_CLEAR_M))
    ruts = str(obj.get("ruts") or "auto")
    c.ruts = ruts if ruts in ("auto", "on", "off") else "auto"
    rough = str(obj.get("rough") or "on")
    c.rough = rough if rough in ROUGH else "on"
    dangers = []
    for q in obj.get("dangers") or ():             # the course file's DANGER waypoints [lat, lon] (auto: rough there)
        try:
            dangers.append((float(q[0]), float(q[1])))
        except (TypeError, ValueError, IndexError):
            pass
    c.dangers = relief.danger_s(c, dangers)
    dk = hashlib.sha1(repr([round(v, 1) for v in c.dangers]).encode()).hexdigest()[:8] if c.dangers else "-"
    # a replay's ground: the windows kept when it was recorded (paintfile.snapshots_dir), used as they are
    c.pin = None
    pin = paintfile.snapshot_name(obj.get("pin")) if obj.get("pin") else None
    if pin and c.kind == "course":
        meta = paintfile.read_json(os.path.join(paintfile.snapshots_dir(pin), "meta.json"))
        if isinstance(meta, dict) and meta.get("cid") == c.cid:
            c.pin = paintfile.snapshots_dir(pin)
        else:
            log.warning("course painter: snapshot %s is not this course's ground (%s): planned as usual", pin,
                        meta.get("cid") if isinstance(meta, dict) else "missing")
    c.key = f"{c.cid}|{int(c.paint)}{int(c.clear)}|{c.clear_m:g}|{c.ruts}|{c.rough}|{dk}|{pin if c.pin else ''}"
    c.seal = terrain.seal(c.cid, c.paint, c.clear, c.rough, c.ruts, dangers, c.tv, _earth_version())
    return c


def parse_plan(obj):
    """Plan of the course file (its "lines", or the older one-course form), or None. Raises ValueError."""
    if not obj or not obj.get("enabled"):
        return None
    raw = obj.get("lines")
    if raw is None:
        raw = [{k: obj.get(k) for k in ("points", "name", "scale", "paint", "clear", "ruts", "rough", "dangers", "tv",
                                        "pin")}]
    lines = [c for c in (_line(o, {}) for o in raw if isinstance(o, dict)) if c is not None]
    return Plan(lines) if lines else None


class _State:
    def __init__(self, mapdata, mapcells, mapgeom, roadsmod, geodesy, demmod, orig_cell):
        self.mapdata, self.mapcells, self.mapgeom, self.roads, self.geodesy, self.demmod = \
            mapdata, mapcells, mapgeom, roadsmod, geodesy, demmod
        self.orig_cell = orig_cell
        self.lock = threading.Lock()
        self.checked = -1e9
        self.mtime = None
        self.course = None          # courseroads.Course or None
        self.wins = {}              # k -> pieces
        self.plan_failed = {}       # (what, k, demand) -> time: a window not to be had then (_planned)
        self.plan_locks = {}        # (what, k) -> this process's lock while it plans the window
        self.merged = OrderedDict()  # (cell key str, cid) -> Features
        self.segs = OrderedDict()   # cell key str -> (lonlat segments (M, 4), half widths (M,))
        self.dems = []              # Dem instances made in this process (BeamNG.Earth's own first)
        self.own_dem = None
        self.stats = {"windows": 0, "pieces": 0, "painted_m": 0.0, "cells": 0, "errors": 0, "buildings_off": 0,
                      "bridges_flat": 0, "walls_cut": 0, "ruts": 0, "relief_windows": 0, "relief_points": 0,
                      "bank_points": 0, "surface_points": 0, "rocks": 0,
                      "trees_off": 0}
        self.rwins = {}             # k -> relief profile (relief.window_profile)
        self.md = None              # the map data last read (the blocks' surfaces: install_surfaces)
        self.rock_cells = OrderedDict()     # (cell, course key) -> vegetation Items with the boulders added
        self.clear_cells = OrderedDict()    # (cell, course key) -> vegetation Items with nothing on the track
        self.veg_plan = None                # the course key the vegetation's own memory was made for
        self.water = OrderedDict()  # cell key str -> [(lonlat ring (k, 2)...)] of dry / salt lakes
        self.followed_ids = {}      # (road id, half width) -> followed by the course (followed_rows), for ...
        self.followed_plan = None   # ... this course
        self.bld = OrderedDict()    # (cell key str, layer, course key) -> Features
        self.cache_dir = None       # BeamNG.Earth's cache folder (its imagery tiles: the ruts' contrast)
        self._imagery = None

    def imagery(self):
        if self._imagery is None and self.cache_dir:
            self._imagery = ruts.CachedImagery(os.path.join(self.cache_dir, "imagery"))
        return self._imagery

    # -- the course file -----------------------------------------------------------------------------------------
    def current(self):
        now = time.monotonic()
        if now - self.checked < CHECK_S:
            return self.course
        with self.lock:
            if now - self.checked < CHECK_S:
                return self.course
            self.checked = now
            path = paintfile.course_path()
            try:
                mt = os.stat(path).st_mtime_ns
            except OSError:
                mt = None
            if mt == self.mtime:
                return self.course
            self.mtime = mt
            obj = paintfile.read_json(path) if mt is not None else None
            try:
                plan = parse_plan(obj)
            except (TypeError, ValueError) as e:
                log.warning("course painter: bad course file: %s", e)
                plan = None
            if (plan and plan.key) != (self.course and self.course.key):
                old = self.course.paint if self.course else None
                if (plan and plan.paint and (plan.paint.cid, plan.paint.pin)) != (old and (old.cid, old.pin)):
                    self.wins, self.rwins, self.plan_failed, self.plan_locks = {}, {}, {}, {}
                self.rock_cells.clear()
                self.course = plan
                self.merged.clear()
                self.bld.clear()
                try:                    # (the roads planned again: the new track, the new setting's dirt road wear)
                    forget_plans()
                except Exception as e:
                    log.debug("course painter: plans kept (%s: %s)", type(e).__name__, e)
                if plan is not None:
                    for c in plan.lines:
                        log.info("course painter: %s: %s (%.0f km)", c.name,
                                 " and ".join(w for w, on in (("dirt track", c.paint), ("clear of blockages", c.clear))
                                              if on) or "nothing", (c.n - 1) * courseroads.STEP_M / 1000)
                else:
                    log.info("course painter: no course")
            return self.course

    # -- data BeamNG.Earth already has -------------------------------------------------------------------------
    def elev(self, md):
        """The heights the track is planned on: BeamNG.Earth's own DEM at courseroads.DEM_ZOOM. The function's
        .fallback is set when a tile came from the fallback source (AWS, while Mapterhorn failed; dem_fallback): the
        window is kept all the same, marked (the first ground planned for a course stays its ground)."""
        dem = self.dems[0] if self.dems else None
        if dem is None:
            if self.own_dem is None:
                self.own_dem = self.demmod.Dem(os.path.join(md.cache_dir, "dem"), fetcher=md.fetcher)
            dem = self.own_dem

        def fn(la, lo):
            la, lo = np.asarray(la, np.float64), np.asarray(lo, np.float64)
            out = dem.sample(la, lo, courseroads.DEM_ZOOM)
            if dem_fallback(dem, la, lo, courseroads.DEM_ZOOM, getattr(self.demmod, "TILE", 512)):
                fn.fallback = True
            return out.tolist()
        fn.fallback = False
        return fn

    def cell_segments(self, md, key, kind):
        """BeamNG.Earth's drawn roads of one cell: (lonlat segment ends (M, 4), half widths (M,))."""
        return self.cell_roads(md, key, kind)[:2]

    def cell_roads(self, md, key, kind):
        """BeamNG.Earth's drawn roads of one cell: (lonlat segment ends (M, 4), half widths (M,), paved (M,): asphalt or
        cobbles)."""
        ks = str(key)
        with self.lock:
            got = self.segs.get(ks)
        if got is not None:
            return got
        feats = self.orig_cell(md, key, ("roads",), kind).layers.get("roads")
        ends, hws, pav = [], [], []
        if feats is not None and len(feats):
            specs = self.roads.road_specs(feats, None, None)
            for i in range(len(feats)):
                sp = specs[i]
                if sp is None or str(feats.ids[i]).startswith(courseroads.ID_PREFIX):
                    continue
                for ring in self.roads.ground_parts(feats, i):
                    r = np.asarray(ring, np.float64)
                    if len(r) >= 2:
                        ends.append(np.concatenate([r[:-1], r[1:]], axis=1))
                        hws.append(np.full(len(r) - 1, sp.width / 2))
                        pav.append(np.full(len(r) - 1, getattr(sp, "kind", "paved") in ("paved", "cobble")))
        got = (np.concatenate(ends) if ends else np.zeros((0, 4)), np.concatenate(hws) if hws else np.zeros(0),
               np.concatenate(pav) if pav else np.zeros(0, bool))
        with self.lock:
            self.segs[ks] = got
            while len(self.segs) > 256:
                self.segs.popitem(last=False)
        return got

    def ground_near(self, md, kind):
        """fn(lon, lat) -> (M, 5) lon0, lat0, lon1, lat1, half width of BeamNG.Earth's ground roads near the point."""
        def fn(lon, lat):
            pad = 60.0 / 111320.0
            padlo = pad / max(0.05, np.cos(np.radians(lat)))
            out = []
            for key in self.mapcells.cells_for_bbox(lat - pad, lon - padlo, lat + pad, lon + padlo):
                e, hw = self.cell_segments(md, key, kind)
                if len(e):
                    near = ((np.maximum(e[:, 0], e[:, 2]) >= lon - padlo) & (np.minimum(e[:, 0], e[:, 2]) <= lon + padlo) &
                            (np.maximum(e[:, 1], e[:, 3]) >= lat - pad) & (np.minimum(e[:, 1], e[:, 3]) <= lat + pad))
                    if near.any():
                        out.append(np.concatenate([e[near], hw[near][:, None]], axis=1))
            return np.concatenate(out) if out else np.zeros((0, 5))
        return fn

    def road_segs_fn(self, md, kind):
        def fn(lat0, lon0, lat1, lon1, plane):
            keys = self.mapcells.cells_for_bbox(lat0, lon0, lat1, lon1)
            out = []
            for key in keys:
                e, hw, pv = self.cell_roads(md, key, kind)
                if not len(e):
                    continue
                inb = ((np.maximum(e[:, 0], e[:, 2]) >= lon0) & (np.minimum(e[:, 0], e[:, 2]) <= lon1) &
                       (np.maximum(e[:, 1], e[:, 3]) >= lat0) & (np.minimum(e[:, 1], e[:, 3]) <= lat1))
                if not inb.any():
                    continue
                e, hw, pv = e[inb], hw[inb], pv[inb]
                ax = (e[:, 0] - plane.lon0) * plane.kx
                ay = (e[:, 1] - plane.lat0) * plane.ky
                bx = (e[:, 2] - plane.lon0) * plane.kx
                by = (e[:, 3] - plane.lat0) * plane.ky
                # (with each segment's paved flag: a dirt road is the course's from further off, courseroads.follow_rule)
                out.extend(zip(ax.tolist(), ay.tolist(), bx.tolist(), by.tolist(), hw.tolist(),
                               [1 if v else 0 for v in pv.tolist()]))
            return out
        return fn

    def canopy_fn(self, md, kind):
        def fn(lat, lon):
            lat, lon = np.asarray(lat, np.float64), np.asarray(lon, np.float64)
            keys = self.mapcells.cells_for_bbox(float(lat.min()), float(lon.min()), float(lat.max()), float(lon.max()))
            mx = courseroads.R_MERC * np.radians(lon)
            my = courseroads.R_MERC * np.log(np.tan(np.pi / 4 + np.radians(np.clip(lat, -85.05, 85.05)) / 2))
            out = np.zeros(len(lat))
            got = False
            for key in keys:
                # (a failed or deferred fetch is not "no trees": the window waits for it, else a track planned without
                # them would be kept, and differ from one planned with them)
                r = self.orig_cell(md, key, ("canopy",), kind).layers.get("canopy")
                if r is None:
                    continue
                v = r.sample(mx, my).astype(np.float64) if r.crs.endswith("3857") else r.sample(lon, lat).astype(np.float64)
                if r.nodata is not None:
                    v[v == r.nodata] = 0.0
                out = np.maximum(out, v)
                got = True
            return out.tolist() if got else None
        return fn

    def surface_segs_fn(self, md, kind):
        """road_segs_fn with each segment's paved flag (relief.window_profile)."""
        def fn(lat0, lon0, lat1, lon1, plane):
            out = []
            for key in self.mapcells.cells_for_bbox(lat0, lon0, lat1, lon1):
                e, hw, pv = self.cell_roads(md, key, kind)
                if not len(e):
                    continue
                inb = ((np.maximum(e[:, 0], e[:, 2]) >= lon0) & (np.minimum(e[:, 0], e[:, 2]) <= lon1) &
                       (np.maximum(e[:, 1], e[:, 3]) >= lat0) & (np.minimum(e[:, 1], e[:, 3]) <= lat1))
                if not inb.any():
                    continue
                e, hw, pv = e[inb], hw[inb], pv[inb]
                out.append(np.stack([(e[:, 0] - plane.lon0) * plane.kx, (e[:, 1] - plane.lat0) * plane.ky,
                                     (e[:, 2] - plane.lon0) * plane.kx, (e[:, 3] - plane.lat0) * plane.ky,
                                     hw, pv.astype(np.float64)], axis=1))
            return np.concatenate(out) if out else np.zeros((0, 6))
        return fn

    def lake_rings(self, md, key, kind):
        """The dry and salt lakes of a cell (water mapped intermittent or salt): [lonlat ring (k, 2)]."""
        ks = str(key)
        with self.lock:
            got = self.water.get(ks)
        if got is not None:
            return got
        rings = []
        f = self.orig_cell(md, key, ("water",), kind).layers.get("water")      # (a failure: raised, tried again)
        if f is not None and len(f):
            n = len(f.kind)
            inter = np.asarray(f.attrs.get("is_intermittent", np.zeros(n, bool)), bool)
            salt = np.asarray(f.attrs.get("is_salt", np.zeros(n, bool)), bool)
            for i in np.flatnonzero((inter | salt) & (np.asarray(f.kind) == self.mapgeom.POLYGON)):
                for part in f.parts(int(i)):
                    if part:
                        rings.append(np.asarray(part[0], np.float64))
        with self.lock:
            self.water[ks] = rings
            while len(self.water) > 128:
                self.water.popitem(last=False)
        return rings

    def land_fn(self, md, kind):
        """fn(lats, lons) -> ESA WorldCover classes (BeamNG.Earth's land cover; open sea: 80). Raises while a cell's
        land cover is not there yet (the window is planned again later)."""
        def fn(lat, lon):
            lat, lon = np.asarray(lat, np.float64), np.asarray(lon, np.float64)
            out = np.full(len(lat), 80, np.int64)
            for key in self.mapcells.cells_for_points(lat, lon):
                lon0, lat0, lon1, lat1 = key.bounds()
                inside = (lat >= lat0) & (lat < lat1) & (lon >= lon0) & (lon < lon1)
                if not inside.any():
                    continue
                r = self.orig_cell(md, key, ("landcover",), kind).layers.get("landcover")
                if r is not None:
                    out[inside] = np.asarray(r.sample(lon[inside], lat[inside]), np.int64)
            return out.tolist()
        return fn

    def waters_fn(self, md, kind):
        """fn(lat0, lon0, lat1, lon1) -> [(kind, half width, polygon, lonlat (k, 2))] of the water there (Overture's,
        BeamNG.Earth's map data; surfaces.water_kind). Raises while a cell's water is not there yet."""
        def fn(lat0, lon0, lat1, lon1):
            out, seen = [], set()
            for key in self.mapcells.cells_for_bbox(lat0, lon0, lat1, lon1):
                f = self.orig_cell(md, key, ("water",), kind).layers.get("water")
                if f is None or not len(f):
                    continue
                n = len(f.kind)
                a = f.attrs
                sub = a.get("subtype", np.full(n, "", object))
                cls = a.get("class", np.full(n, "", object))
                inter = np.asarray(a.get("is_intermittent", np.zeros(n, bool)), bool)
                salt = np.asarray(a.get("is_salt", np.zeros(n, bool)), bool)
                for i in range(n):
                    poly = f.kind[i] == self.mapgeom.POLYGON
                    wk = surfaces.water_kind(sub[i], cls[i], bool(inter[i]), bool(salt[i]), poly)
                    if wk is None:
                        continue
                    for part in f.parts(int(i)):
                        if part and len(part[0]) >= 2:
                            ll = np.asarray(part[0], np.float64)[:, :2]
                            if ll[:, 0].max() < lon0 or ll[:, 0].min() > lon1 or ll[:, 1].max() < lat0 or \
                                    ll[:, 1].min() > lat1:
                                continue
                            k_ = (wk[0], poly, ll.round(7).tobytes())
                            if k_ in seen:          # (the same water in two cells)
                                continue
                            seen.add(k_)
                            out.append((wk[0], wk[1], poly, ll))
            return out
        return fn

    def lake_fn(self, md, kind):
        def fn(lat, lon):
            lat, lon = np.asarray(lat, np.float64), np.asarray(lon, np.float64)
            out = np.zeros(len(lat))
            for key in self.mapcells.cells_for_bbox(float(lat.min()), float(lon.min()), float(lat.max()),
                                                    float(lon.max())):
                for r in self.lake_rings(md, key, kind):
                    out = np.maximum(out, _inside(r, lon, lat))
            return out.tolist()
        return fn

    # -- the track's relief (relief.py) ----------------------------------------------------------------------------
    def relief_window(self, md, course, k, kind, wait=None):
        """The relief window k's profile: kept, pinned, on disk, or planned now. kind "peek": never planned here (None
        when not planned yet): for the road tiles' workers, which must not wait on the ground (planning a window asks
        for elevation, from the block process, which may itself be waiting on those road tiles: 1.6.4's road tiles
        hung so, the user 2026-10-29). A demand read (a build of the ground) waits for it (_planned)."""
        with self.lock:
            if k in self.rwins:
                return self.rwins[k]
        if kind == "peek":
            prof = _pinned(course, f"r{k:06d}.json", relief.ALGO)
            if prof is None:
                prof = paintfile.read_json(os.path.join(paintfile.windows_dir(course.cid), f"r{k:06d}.json"))
                if not (isinstance(prof, dict) and prof.get("algo") == relief.ALGO):
                    return None
            with self.lock:
                self.rwins[k] = prof
            return prof
        pinned = _pinned(course, f"r{k:06d}.json", relief.ALGO)
        if pinned is not None:
            with self.lock:
                self.rwins[k] = pinned
            return pinned

        def valid(prof):
            return prof if isinstance(prof, dict) and prof.get("algo") == relief.ALGO else None

        def make():
            pieces = self.window(md, course, k, kind, wait)
            if pieces is None:
                raise ValueError("no track pieces yet")
            ef = self.elev(md)
            ground = getattr(course, "tv", 1) >= surfaces.FROM_TV
            prof = relief.window_profile(course, k, pieces, self.surface_segs_fn(md, kind), ef,
                                         self.lake_fn(md, kind),
                                         self.land_fn(md, kind) if ground else None,
                                         self.waters_fn(md, kind) if ground else None)
            if ef.fallback:
                prof["dem"] = "fallback"        # (kept all the same: the first ground planned is the course's)
                log.info("course painter: relief window %d planned on BeamNG.Earth's fallback elevation", k)
            return prof
        path = os.path.join(paintfile.windows_dir(course.cid), f"r{k:06d}.json")
        prof = self._planned("r", k, kind, path, valid, make, wait)
        if prof is not None:
            with self.lock:
                self.rwins[k] = prof
        return prof

    def _planned(self, what, k, kind, path, valid, make, wait=None):
        """Window k's plan (what: "w" the track's pieces, "r" the relief profile) as every process of this server has it:
        the file at path (the first one planned: write_json_first), else planned here by make() and written there.
        One process plans a window at a time (a lock file beside it, PLAN_LOCK_STALE_S); the others wait for its file.
        kind "demand" (a build of the ground, the road tiles, the vegetation: what it gets now is what the player
        drives) waits for it, planning it again after a failure, up to DEMAND_WAIT_S: a window missing there is ground
        built without the course's track, kept by BeamNG.Earth's caches for the session and differing from the
        ground built after it (1.7.10, the user 2026-11-10: walls and steps in the ground where the track met it,
        the course's track textured late). Other kinds try once, and leave a window another process is planning to it.
        None when not to be had now (another try: DEMAND_GIVEUP_S / RETRY_S later)."""
        demand = (kind in DEMAND_KINDS) if wait is None else bool(wait)
        fk = (what, k, demand)
        failed = self.plan_failed.get(fk)
        if failed is not None and time.monotonic() - failed < (DEMAND_GIVEUP_S if demand else RETRY_S):
            _fault()
            return None
        raw = paintfile.read_json(path)
        got = valid(raw)
        if got is not None:
            return got
        if raw is not None:
            _remove(path)                   # (another code's: never this course's ground)
        with self.lock:
            lk = self.plan_locks.setdefault((what, k), threading.Lock())
        if not lk.acquire(blocking=demand):
            return None                     # (this process plans it already: a background read does not wait)
        t0 = time.monotonic()
        try:
            last, delay, waited = None, 0.5, False
            while True:
                got = valid(paintfile.read_json(path))
                if got is not None:
                    break
                if _try_lock(path):
                    keep = _keep_lock(path)
                    try:
                        got = valid(paintfile.read_json(path))         # (planned meanwhile)
                        if got is None:
                            try:
                                obj = make()
                            except Exception as e:      # data not there yet (offline, deferred, a fetch failed)
                                last = e
                            else:
                                try:
                                    got = valid(paintfile.write_json_first(path, obj)) or obj
                                except OSError:
                                    got = obj
                                with self.lock:
                                    self.stats["relief_windows" if what == "r" else "windows"] += 1
                                    if what == "w":
                                        self.stats["pieces"] += len(obj.get("pieces") or ())
                                        self.stats["painted_m"] += sum((len(p["ll"]) - 1) * courseroads.STEP_M
                                                                       for p in obj.get("pieces") or ())
                    finally:
                        keep.set()
                        _unlock(path)
                    if got is not None:
                        break
                    if not demand or time.monotonic() - t0 + delay > DEMAND_WAIT_S:
                        raise last if last is not None else ValueError("not planned")
                    waited = True
                    time.sleep(delay)
                    delay = min(delay * 2.0, 4.0)
                else:
                    if not demand:
                        return None         # (another process plans it: this one gets the file later)
                    if time.monotonic() - t0 > DEMAND_WAIT_S:
                        raise TimeoutError(f"still being planned by another process after {DEMAND_WAIT_S:.0f} s")
                    waited = True
                    time.sleep(POLL_S)
            dt = time.monotonic() - t0
            if demand and (waited or dt > SLOW_PLAN_S):
                with self.lock:
                    self.stats["demand_waits"] = self.stats.get("demand_waits", 0) + 1
                    self.stats["demand_wait_s"] = round(self.stats.get("demand_wait_s", 0.0) + dt, 1)
                log.info("course painter: %s window %d ready for a build after %.1f s%s", "relief" if what == "r"
                         else "track", k, dt, " (waited)" if waited else "")
            self.plan_failed.pop(fk, None)
            return got
        except Exception as e:
            with self.lock:
                self.plan_failed[fk] = time.monotonic()
                self.stats["errors"] += 1
                if demand:
                    self.stats["bare_reads"] = self.stats.get("bare_reads", 0) + 1
            if demand:
                log.warning("course painter: %s window %d not ready for a build after %.1f s (%s: %s): built without "
                            "it", "relief" if what == "r" else "track", k, time.monotonic() - t0,
                            type(e).__name__, e)
            else:
                log.debug("course painter: %s window %d: %s: %s", what, k, type(e).__name__, e)
            _fault()
            return None
        finally:
            lk.release()

    def course_near(self, md, lat, lon, kind="demand"):
        """(course, its relief windows' profiles near the points) or None (no course painted near). kind "peek": only
        the windows already planned (relief_window)."""
        plan = self.current()
        c = plan.paint if plan is not None else None
        if c is None:
            return None
        lat = np.asarray(lat, np.float64)
        lon = np.asarray(lon, np.float64)
        if lat.size == 0:
            return None
        la0, la1, lo0, lo1 = float(lat.min()), float(lat.max()), float(lon.min()), float(lon.max())
        pad = relief.REACH_M / 111320.0
        padlo = pad / max(0.05, math.cos(math.radians(la0)))
        ks = c.windows_in((lo0 - padlo, la0 - pad, lo1 + padlo, la1 + pad))
        if not ks:
            return None
        profs = {k: self.relief_window(md, c, k, kind) for k in ks}
        profs = {k: p for k, p in profs.items() if p}
        return (c, profs) if profs else None

    def relief_at(self, md, lat, lon, near=None, ctx=None):
        """Metres the course's relief adds at the points (same shape), or None (no course near, relief off). ctx:
        course_near's answer for the points, near: relief.nearest's (each computed when None)."""
        plan = self.current()
        c = plan.paint if plan is not None else None
        scale = ROUGH.get(getattr(c, "rough", "on"), 1.0) if c is not None else 0.0
        if not scale:
            return None
        ctx = ctx if ctx is not None else self.course_near(md, lat, lon)
        if ctx is None:
            return None
        c, profs = ctx
        dz = relief.relief(c, profs, lat, lon, scale, auto=getattr(c, "rough", "on") == "auto", near=near)
        if getattr(c, "tv", 1) >= relief.PAVED_CLEAR_TV:
            try:
                dz = self.paved_clear(md, lat, lon, dz)
            except Exception as e:              # (the roads not to be had: the relief as it is, this build not kept)
                _fault()
                with self.lock:
                    self.stats["errors"] += 1
                log.warning("course painter: relief off the paved roads: %s: %s", type(e).__name__, e)
        with self.lock:
            self.stats["relief_points"] += int(np.count_nonzero(dz))
        return dz

    def paved_clear(self, md, lat, lon, dz):
        """dz without the relief on BeamNG.Earth's paved roads (relief.paved_clear: terrain 12)."""
        dz = np.array(dz, np.float64)
        flat = dz.reshape(-1)
        idx = np.flatnonzero(flat)
        if not len(idx):
            return dz
        la = np.asarray(lat, np.float64).reshape(-1)[idx]
        lo = np.asarray(lon, np.float64).reshape(-1)[idx]
        pad = 20.0 / 111320.0
        padlo = pad / max(0.05, math.cos(math.radians(float(la.mean()))))
        ends, hws = [], []
        for key in self.mapcells.cells_for_bbox(float(la.min()) - pad, float(lo.min()) - padlo,
                                                float(la.max()) + pad, float(lo.max()) + padlo):
            e, hw, pv = self.cell_roads(md, key, "demand")
            if len(e) and pv.any():
                ends.append(e[pv])
                hws.append(hw[pv])
        if not ends:
            return dz
        flat[idx] *= relief.paved_clear(la, lo, np.concatenate(ends), np.concatenate(hws))
        return dz

    def ruts_at(self, lat, lon):
        """relief.ruts_at for the points (0 where no course is near or its windows are not planned yet: the planner
        plans them ahead of the car, so the ground under a road tile normally is)."""
        plan = self.current()
        c = plan.paint if plan is not None else None
        if c is None:
            return np.zeros(len(lat))
        ctx = self.course_near(getattr(self, "md", None), lat, lon, "peek")    # (never waits on the ground)
        if ctx is None:
            return np.zeros(len(lat))
        return relief.ruts_at(ctx[0], ctx[1], lat, lon, ROUGH.get(getattr(c, "rough", "on"), 1.0),
                              auto=getattr(c, "rough", "on") == "auto")

    def banks_at(self, grader, grade_fn, lat, lon, base, graded, ctx, near):
        """graded with the course's cut banks (banks.py) in place of BeamNG.Earth's bare steps beside its dirt
        track. grade_fn(lat, lon, natural): BeamNG.Earth's own grading (the same lift)."""
        c, profs = ctx
        elev = getattr(grader, "elev", None)
        if elev is None or getattr(c, "tv", 1) < banks.FROM_TV:
            return graded

        def elev_fn(la, lo):
            return np.asarray(elev(np.asarray(la, np.float64), np.asarray(lo, np.float64)), np.float64)
        out = banks.banks(c, profs, lat, lon, base, graded, grade_fn, elev_fn, near=near)
        n = int(np.count_nonzero(out != np.asarray(graded, np.float64).reshape(np.shape(out))))
        if n:
            with self.lock:
                self.stats["bank_points"] += n
        return out

    def off_track(self, key, items, veg_mod, md):
        """A vegetation cell's Items without the trees, bushes and rocks standing on the course's track (the user,
        2026-10-28: "trees in the middle of the road ... remove the ones on the course"): its own dirt track, and a
        road or path it follows (BeamNG.Earth keeps trees off a road by its class's width only, none off a path, and
        its cells built before the course was loaded had none of it). Within the track's half width (relief's
        profiles: the track's or the followed road's) + TREE_CLEAR_M of its middle."""
        plan = self.current()
        c = plan.paint if plan is not None else None
        if c is None or items is None or not len(items):
            return items
        mk = (str(key), plan.key)
        with self.lock:
            got = self.clear_cells.get(mk)
        if got is not None:
            return got
        lat = np.asarray(items.lat, np.float64)
        lon = np.asarray(items.lon, np.float64)
        ctx = self.course_near(md, lat, lon)
        out, complete = items, True
        if ctx is not None:
            course, profs = ctx
            pad = relief.REACH_M / 111320.0
            padlo = pad / max(0.05, math.cos(math.radians(float(lat.min()))))
            want = course.windows_in((float(lon.min()) - padlo, float(lat.min()) - pad, float(lon.max()) + padlo,
                                      float(lat.max()) + pad))
            complete = len(profs) >= len(want or ())         # (a window not planned yet: asked again later)
            idx, d, s = relief.nearest(course, profs, lat, lon)
            if len(idx):
                f = relief._Facts(profs).at(s)
                on = np.abs(d - f["ctr"]) <= f["hw"] + TREE_CLEAR_M
                if on.any():
                    keep = np.ones(len(lat), bool)
                    keep[idx[on]] = False
                    out = items.take(keep)
                    with self.lock:
                        self.stats["trees_off"] += int(np.count_nonzero(on))
        if complete:
            with self.lock:
                self.clear_cells[mk] = out
                while len(self.clear_cells) > 64:
                    self.clear_cells.popitem(last=False)
        return out

    def rocks_for(self, key, items, veg_mod, md):
        """A vegetation cell's Items with the boulders beside the track added (relief.rocks)."""
        plan = self.current()
        c = plan.paint if plan is not None else None
        if c is None or not ROUGH.get(getattr(c, "rough", "on"), 1.0):
            return items
        mk = (str(key), plan.key)
        with self.lock:
            got = self.rock_cells.get(mk)
        if got is not None:
            return got
        ck = self.mapcells.CellKey(int(key[0]), int(key[1]), int(key[2]))
        bounds = ck.bounds()
        ks = c.windows_in(bounds)
        out = items
        if ks:
            profs = {k: self.relief_window(md, c, k, "demand") for k in ks}
            r = relief.rocks(c, profs, bounds, auto=getattr(c, "rough", "on") == "auto")
            if len(r["lon"]) and getattr(c, "tv", 1) >= relief.ROCKS_OFF_ROADS_TV:
                r = self.rocks_off_roads(md, r, bounds)
            n = len(r["lon"])
            if n:
                lat, lon = r["lat"], r["lon"]
                g = rock_groups(items, veg_mod, lat, lon)
                add = veg_mod.Items(lon, lat, r["size"].astype(np.float32), (r["size"] * 0.6).astype(np.float32),
                                    np.full(n, veg_mod.KIND_ROCK, np.uint8), g, r["rank"].astype(np.float32),
                                    r["yaw"].astype(np.float32), r["scale"].astype(np.float32))
                out = veg_mod._concat(items, add) if len(items) else add
                with self.lock:
                    self.stats["rocks"] += n
            if not all(profs.values()):
                return out          # (a window not ready: not kept, asked again)
        with self.lock:
            self.rock_cells[mk] = out
            while len(self.rock_cells) > 64:
                self.rock_cells.popitem(last=False)
        return out

    def rocks_off_roads(self, md, r, bounds):
        """relief.rocks_off_roads with BeamNG.Earth's roads round bounds (its cells' and their neighbours': a road
        just past the cell's edge, its width reaching in)."""
        lon0, lat0, lon1, lat1 = bounds
        pad = 40.0 / 111320.0
        padlo = pad / max(0.05, math.cos(math.radians(lat0)))
        ends, hws, pvs = [], [], []
        for key in self.mapcells.cells_for_bbox(lat0 - pad, lon0 - padlo, lat1 + pad, lon1 + padlo):
            e, hw, pv = self.cell_roads(md, key, "demand")
            if len(e):
                ends.append(e)
                hws.append(hw)
                pvs.append(pv)
        if not ends:
            return r
        out = relief.rocks_off_roads(r, np.concatenate(ends), np.concatenate(hws), np.concatenate(pvs))
        gone = len(r["lon"]) - len(out["lon"])
        if gone:
            with self.lock:
                self.stats["rocks_off_roads"] = self.stats.get("rocks_off_roads", 0) + gone
        return out

    # -- windows ---------------------------------------------------------------------------------------------------
    def window(self, md, course, k, kind, wait=None):
        with self.lock:
            if k in self.wins:
                return self.wins[k]
        ps = _pinned(course, f"w{k:06d}.json", courseroads.ALGO)
        if ps is None:
            def valid(obj):
                return obj if isinstance(obj, dict) and obj.get("algo") == courseroads.ALGO else None

            def make():
                ef = self.elev(md)
                pieces = courseroads.window_pieces(course, k, self.road_segs_fn(md, kind), ef,
                                                   self.canopy_fn(md, kind))
                obj = {"algo": courseroads.ALGO, "pieces": pieces}
                if ef.fallback:
                    obj["dem"] = "fallback"         # (kept all the same: the first ground planned is the course's)
                    log.info("course painter: window %d planned on BeamNG.Earth's fallback elevation", k)
                return obj
            path = os.path.join(paintfile.windows_dir(course.cid), f"w{k:06d}.json")
            ps = self._planned("w", k, kind, path, valid, make, wait)
            if ps is None:
                return None
        with self.lock:
            self.wins[k] = ps["pieces"]
        return ps["pieces"]

    def roads_for(self, md, key, base, kind):
        plan = self.current()
        if plan is None:
            return base
        base0 = base
        # (BeamNG.Earth 1.7 joins OpenStreetMap's railway tags to a decoded roads layer when they come, maybe after it
        # was first read: a merge made before them is made again)
        sig = (tuple(sorted(base.attrs)), base.__dict__.get("_rails_built"),
               base.__dict__.get("_lanes_built")) if base is not None else None
        mk = (str(key), plan.key, sig)
        with self.lock:
            got = self.merged.get(mk)
            if got is not None:
                self.merged.move_to_end(mk)
                return got
        bounds = key.bounds()
        ps, complete = [], True
        if plan.clearing and base is not None and len(base):
            idx = set()
            for c in plan.clearing:
                lines = corridor.course_lines(c, bounds, 200.0)
                if lines:
                    idx |= set(corridor.bridges_to_flatten(self.roads, base, lines, self.ground_near(md, kind),
                                                           elev_fn=self.elev(md)))
            if idx:
                base = corridor.flatten(self.mapgeom, base, sorted(idx))
                with self.lock:
                    self.stats["bridges_flat"] += len(idx)
                log.debug("course painter: %s: %d bridge(s) on the way made ground roads", key, len(idx))
        course = plan.paint
        for k in (course.windows_in(bounds) if course is not None else ()):
            w = self.window(md, course, k, kind)
            if w is None:
                complete = False
                continue
            for p in w:
                x0, y0, x1, y1 = courseroads.piece_box(p)
                if x1 >= bounds[0] and x0 <= bounds[2] and y1 >= bounds[1] and y0 <= bounds[3]:
                    ps.append(p)
        if ps and getattr(course, "tv", 1) >= variety.VARIETY_TV:
            # (terrain 7: a sand trap, a rock section or a crawl drawn as the ground itself, no dirt decal: its stretch
            # of track a "rock" surface road. The relief windows only as already planned: never waits on the ground)
            profs = {k: self.relief_window(md, course, k, "peek") for k in course.windows_in(bounds)}
            if all(profs.values()):
                ps, done = variety.split_bare(course, profs, ps)
                complete = complete and done
            else:
                complete = False
        if not ps:
            out = base
        else:
            lat_c, lon_c = key.center()
            out = merge(self.mapgeom, base, ps, bounds, self.geodesy.EnuFrame(lat_c, lon_c, 0.0),
                                    course.name)
            dirt = [p for p in ps if p.get("surface") != "rock"]
            if len(dirt) < len(ps) and out is not None:
                # (BeamNG.Earth paints its roads into the ground's photo by their kind, a "rock" road as dirt: the photo
                # gets the layer without those stretches, so the place's own sand or rock shows: _photo_roads)
                photo = merge(self.mapgeom, base, dirt, bounds, self.geodesy.EnuFrame(lat_c, lon_c, 0.0),
                              course.name) if dirt else base
                if photo is not base0:
                    _carry(base0, photo, md, key, share_tag(self) + "-photo")
                out.__dict__[PHOTO_KEY] = photo
        if out is not base0:
            _carry(base0, out, md, key, share_tag(self))
        if complete:                            # (a window that failed is tried again later: not kept)
            with self.lock:
                self.merged[mk] = out
                self.stats["cells"] += 1
                while len(self.merged) > MEMO:
                    self.merged.popitem(last=False)
        return out


# What BeamNG.Earth hangs on a decoded roads layer that is about the cell, not its rows, and goes on with the roads
# layer made with the course's track (1.7: OpenStreetMap's railway nodes, for the level crossings' gates and lights).
# Memos of the layer's rows (_lonlat_boxes, _bridge_ends, _gs_rows, ...) stay behind: the new layer has more rows.
CARRY = ("_rail_nodes", "_rails_built", "_lanes_built",
         "_bnge_neighbours")    # (1.8: the eight cells round it, BeamNG.Earth's own layers: a road's lanes and bridge
#                                 ranges from its copy in its home cell, roads.home_copy; the same for a layer with the
#                                 track as for BeamNG.Earth's own, or a road's bridge came out twice at two heights)


def _carry(base, out, md, key, tag="-"):
    """BeamNG.Earth's per-cell extras of the roads layer base onto out (the layer with the course's track): CARRY as
    they are, its grade separations (1.7, gradesep: a hook working on the layer's own rows) made for out, and (1.8)
    its cell id (_bnge_cell: the cell, the layer, the map data's versions), the layer's name marked with the GPS
    ground's tag: BeamNG.Earth keeps a cell's road facts by it (roads._FACTS_MEM, its revisit cache), which must never
    be those of the layer without the track, or of another course's."""
    if base is None or out is None:
        return
    for k in CARRY:
        if k in base.__dict__:
            out.__dict__[k] = base.__dict__[k]
    cid = base.__dict__.get("_bnge_cell")
    if isinstance(cid, tuple) and len(cid) >= 3:
        out.__dict__["_bnge_cell"] = (cid[0], f"{cid[1]}+egps-{tag}") + tuple(cid[2:])
    if "_bnge_gradesep" in base.__dict__:
        try:
            import gradesep
            out.__dict__["_bnge_gradesep"] = gradesep.hook(md, key)
        except Exception as e:      # (the map's own bridges only, as before 1.7)
            log.debug("course painter: no grade separations for %s: %s: %s", key, type(e).__name__, e)


# -- the course's pieces as road features of a cell (numpy: BeamNG.Earth's columns) -----------------------------
def _buildings_for(st, md, key, f, layer):
    plan = st.current()
    if plan is None or not plan.clearing or f is None or len(f) == 0:
        return f
    mk = (str(key), layer, plan.key)
    with st.lock:
        got = st.bld.get(mk)
        if got is not None:
            st.bld.move_to_end(mk)
            return got
    out = f
    off = set()
    for c in plan.clearing:
        lines = corridor.course_lines(c, key.bounds(), 250.0)
        if lines:
            off |= set(corridor.buildings_off(f, lines, c.clear_m))
    if off:
        off -= _toll_keep(st, md, key, f, off)
    if off:
        keep = np.setdiff1d(np.arange(len(f)), np.asarray(sorted(off), np.int64))
        out = corridor.subset(st.mapgeom, f, keep)
        with st.lock:
            st.stats["buildings_off"] += len(off)
    with st.lock:
        st.bld[mk] = out
        while len(st.bld) > MEMO:
            st.bld.popitem(last=False)
    return out


def _toll_keep(st, md, key, f, off):
    """The indices among off (to be left out of f) that belong to a toll plaza (corridor.toll_plaza): its islands,
    booths and flat footprint stay for BeamNG.Earth to draw as toll booths. Only looked into when one of them could
    be (low or booth sized): the footprints and parts of the cells around are read for the island / booth pairs."""
    cand = [i for i in off if corridor.toll_like(f, i)]
    if not cand:
        return set()
    try:
        lon0, lat0, lon1, lat1 = key.bounds()
        pad = 60.0 / 111320.0
        padlo = pad / max(0.05, math.cos(math.radians((lat0 + lat1) / 2)))
        blds, parts = [], []
        for k in st.mapcells.cells_for_bbox(lat0 - pad, lon0 - padlo, lat1 + pad, lon1 + padlo):
            cd = st.orig_cell(md, k, ("buildings", "building_parts"), "demand")
            blds.append(cd.layers.get("buildings"))
            parts.append(cd.layers.get("building_parts"))
        ids = corridor.toll_plaza(blds, parts, (lat0 + lat1) / 2, (lon0 + lon1) / 2)
    except Exception as e:
        log.debug("course painter: toll plaza check %s: %s: %s", key, type(e).__name__, e)
        return set()
    kept = {i for i in cand if str(f.ids[i]) in ids}
    if kept:
        with st.lock:
            st.stats["toll_kept"] = st.stats.get("toll_kept", 0) + len(kept)
    return kept


def _fill(dtype, n, value=None):
    if dtype.kind == "U":
        return np.array([value or ""] * n, dtype=f"<U{max(1, len(value or ''))}")
    if dtype.kind == "f":
        return np.full(n, np.nan if value is None else value, dtype)
    if dtype.kind == "b":
        return np.zeros(n, bool)
    if dtype.kind == "O":           # (OpenStreetMap's tags joined by BeamNG.Earth 1.7: None where a way has none)
        return np.full(n, value, object)
    return np.zeros(n, dtype)


def merge(mapgeom, base, ps, key_bounds, frame, name):
    """base (mapgeom.Features of a cell's "roads", or None) with the pieces ps added as dirt tracks. A new Features
    (base is shared and never changed). key_bounds: the cell's (lon0, lat0, lon1, lat1), for `own`."""
    ps = sorted(ps, key=lambda p: p["id"])
    if not ps:
        return base
    nb = len(base) if base is not None else 0
    ne = len(ps)
    ids = np.array([p["id"] for p in ps])
    geoms = [(mapgeom.LINE, [[np.asarray(p["ll"], np.float64)]]) for p in ps]
    extra = mapgeom.build("roads", ids, geoms)
    x0, y0, x1, y1 = key_bounds
    own = np.zeros(ne, bool)
    for j, p in enumerate(ps):
        bx0, by0, bx1, by1 = courseroads.piece_box(p)
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        own[j] = x0 <= cx < x1 and y0 <= cy < y1
    texts = {"subtype": "road", "class": "track", "name": name, "src_dataset": "Offroad Companion course"}
    if base is None:
        attrs = {k: np.array([texts.get(k, "")] * ne) for k in ("subtype", "class", "subclass", "name",
                                                                  "src_dataset", "src_record")}
        rules = {}
        out = extra
        out.own, out.clipped = own, np.zeros(ne, bool)
    else:
        attrs = {}
        for k, col in base.attrs.items():
            col = np.asarray(col)
            add = _fill(col.dtype, ne, texts.get(k)) if col.dtype.kind == "U" else _fill(col.dtype, ne)
            attrs[k] = np.concatenate([col, add])
        for k, v in texts.items():
            if k not in attrs:
                attrs[k] = np.concatenate([np.array([""] * nb), np.array([v] * ne)])
        rules = dict(base.rules)
        off_p = len(base.part_off) - 1
        off_r = len(base.ring_off) - 1
        off_c = len(base.lonlat)
        out = mapgeom.Features(
            "roads", np.concatenate([base.ids, ids]), np.concatenate([base.kind, extra.kind]),
            np.concatenate([base.part_off, extra.part_off[1:] + off_p]),
            np.concatenate([base.ring_off, extra.ring_off[1:] + off_r]),
            np.concatenate([base.coord_off, extra.coord_off[1:] + off_c]),
            np.concatenate([base.lonlat, extra.lonlat]), None,
            np.concatenate([base.own if base.own is not None else np.zeros(nb, bool), own]),
            np.concatenate([base.clipped if base.clipped is not None else np.zeros(nb, bool), np.zeros(ne, bool)]))
    feat = np.arange(nb, nb + ne, dtype=np.int32)

    def with_rows(name_, values, kind):
        old = rules.get(name_)
        if old is not None and len(old.feature):
            vdtype = np.asarray(old.value).dtype
            vals = np.asarray(values, vdtype) if kind == "f" else np.asarray(values)
            rules[name_] = mapgeom.RuleTable(np.concatenate([np.asarray(old.feature, np.int32), feat]),
                                             np.concatenate([np.asarray(old.value), vals]),
                                             np.concatenate([np.asarray(old.start, np.float32), np.zeros(ne, np.float32)]),
                                             np.concatenate([np.asarray(old.end, np.float32), np.ones(ne, np.float32)]))
        else:
            vals = np.asarray(values, np.float32) if kind == "f" else np.asarray(values)
            rules[name_] = mapgeom.RuleTable(feat, vals, np.zeros(ne, np.float32), np.ones(ne, np.float32))
    with_rows("width", [p["w"] for p in ps], "f")
    with_rows("surface", [p.get("surface") or "dirt" for p in ps], "U")
    out.attrs, out.rules = attrs, rules
    if not np.all(out.ids[:-1] <= out.ids[1:]):          # (never with Overture's ids: ours sort after them)
        raise ValueError("road ids out of order after adding the course")
    return out.localize(frame)


def _inside(ring, x, y):
    """0 / 1 per point (x, y): inside the closed ring (k, 2) (even-odd)."""
    ring = np.asarray(ring, np.float64)
    out = np.zeros(len(x), bool)
    if len(ring) < 3:
        return out.astype(np.float64)
    m = (x >= ring[:, 0].min()) & (x <= ring[:, 0].max()) & (y >= ring[:, 1].min()) & (y <= ring[:, 1].max())
    if not m.any():
        return out.astype(np.float64)
    px, py = x[m], y[m]
    xa, ya = ring[:, 0], ring[:, 1]
    xb, yb = np.roll(xa, -1), np.roll(ya, -1)
    ins = np.zeros(len(px), bool)
    for i in range(len(ring)):
        c = (ya[i] > py) != (yb[i] > py)
        if c.any():
            xc = xa[i] + (py - ya[i]) * (xb[i] - xa[i]) / ((yb[i] - ya[i]) or 1e-300)
            ins ^= c & (px < xc)
    out[m] = ins
    return out.astype(np.float64)


def surface_mats(surfacemod):
    """Material name -> index in BeamNG.Earth's surface.MATERIALS (with surfaces.EXTRA_MATERIALS appended)."""
    names = [m[0] for m in surfacemod.MATERIALS]
    mats = {k: getattr(surfacemod, k) for k in ("ASPHALT", "GRASS", "DUSTY", "LOOSE", "ROCK", "SNOW", "MUD", "COBBLE",
                                                "LAWN", "DIRT") if hasattr(surfacemod, k)}
    mats["SAND"] = names.index(surfaces.EXTRA_MATERIALS[0][0])
    mats["GRAVEL"] = names.index(surfaces.EXTRA_MATERIALS[1][0])
    return mats


COURSE_SRC = "Offroad Companion course"     # (merge's src_dataset of the track's rows)
_CourseSpec = None


def course_spec_class(roadsmod):
    """A subclass of roads.Spec, the same fields: the course's track's specs, so BeamNG.Earth's grading can tell them
    from a mapped track's (a namedtuple's _replace keeps the class)."""
    global _CourseSpec
    if _CourseSpec is None or _CourseSpec.__bases__[0] is not roadsmod.Spec:
        _CourseSpec = type("CourseSpec", (roadsmod.Spec,), {"__slots__": (), "__module__": __name__})
        globals()["CourseSpec"] = _CourseSpec           # (pickled by name: gpsd.earthpatch.CourseSpec)
    return _CourseSpec


def course_rows(feats):
    """The rows of a roads layer that are the course's track (merge: src_dataset COURSE_SRC), remembered on it."""
    got = feats.__dict__.get("_egps_course_rows")
    if got is None:
        src = (getattr(feats, "attrs", None) or {}).get("src_dataset")
        got = () if src is None else tuple(int(i) for i in np.flatnonzero(np.asarray(src) == COURSE_SRC))
        feats.__dict__["_egps_course_rows"] = got
    return got


FOLLOWED_MEMO = 200000      # roads' answers kept (followed_rows)
LEAN_SHARE = 0.05       # Baja, Mild, Rough, Extra: the share of BeamNG.Earth's dirt road parts that keep their lean


def dirt_wear(mode, course):
    """How BeamNG.Earth 1.8.2's dirt road wear goes on a dirt road part with the course's terrain setting mode (None:
    no course) and course (the course's own track or not): (bumps, lean, smoothing), each "earth" (BeamNG.Earth's own)
    or None / "rare" / "smooth". The user, 2026-11-06:
      default   BeamNG.Earth 1.8.2's ground, the course's track a worn track like any other (the painter's relief off)
      off       Flat: like BeamNG.Earth before 1.8.2, no wear on any dirt road (smoothed over DIRT_SIGMA_M)
      others    Baja (auto), Mild, Rough, Extra: the track the painter's own, unworn; the mapped dirt roads keep their
                potholes but lean only rarely (LEAN_SHARE)
    No course: BeamNG.Earth's own everywhere. Pure."""
    if mode is None or mode == "default":
        return "earth", "earth", "earth"
    if course or mode == "off":
        return None, None, "smooth"
    return "earth", "rare", "earth"


def lean_kept(xy):
    """Whether a dirt road part keeps its lean (LEAN_SHARE of them): from the part's first point, so every process
    and tile picks the same. Pure."""
    xy = np.asarray(xy, np.float64)
    if xy.ndim != 2 or not len(xy):
        return False
    key = f"{int(round(float(xy[0, 0]) * 3.0))},{int(round(float(xy[0, 1]) * 3.0))}".encode()
    h = int.from_bytes(hashlib.blake2s(key, digest_size=4).digest(), "little")
    return h / 2.0 ** 32 < LEAN_SHARE


def wear_mode(st):
    """The course's terrain setting (its rough), None when no course is loaded."""
    plan = st.current() if st is not None else None
    if plan is None:
        return None
    c = plan.paint or next((ln for ln in plan.lines if getattr(ln, "kind", "") == "course"), None)
    return getattr(c, "rough", None) if c is not None else None


def followed_rows(st, roadsmod, feats, specs):
    """The mapped dirt roads (rows of feats, specs: road_specs') the loaded course runs along (corridor.rows_followed,
    courseroads' follow rule for dirt roads): the course's road there, so BeamNG.Earth's dirt road wear stays off it as
    off the course's own track (the user, 2026-11-08: "our track on baja still is being influenced by the vanilla
    BeamNG.Earth new dirt roads"). Remembered on feats for the course loaded. -> tuple of rows."""
    plan = st.current() if st is not None else None
    c = getattr(plan, "paint", None) if plan is not None else None
    if c is None:
        return ()
    memo = feats.__dict__.get("_egps_followed")
    if memo is not None and memo[0] == plan.key:
        return memo[1]
    got = ()
    built = getattr(roadsmod, "BUILT", ())
    own = set(course_rows(feats))
    cand = [i for i, sp in enumerate(specs) if sp is not None and i not in own and getattr(sp, "kind", None) not in built]
    if cand and len(feats):
        boxes = corridor._feature_boxes(feats)
        pad = courseroads.FOLLOW_UNPAVED_M + 30.0
        dlat = pad / 111320.0
        ok = np.isfinite(boxes).all(axis=1)
        if ok.any():
            b = boxes[ok]
            bounds = (float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max()))
            lines = corridor.course_lines(c, bounds, pad)
            if lines:
                allc = np.concatenate(lines)
                dlon = pad / (111320.0 * max(0.05, math.cos(math.radians(float(allc[:, 1].mean())))))
                cl0, cl1 = allc.min(axis=0), allc.max(axis=0)
                near = [i for i in cand if np.isfinite(boxes[i]).all() and boxes[i, 0] <= cl1[0] + dlon and
                        boxes[i, 2] >= cl0[0] - dlon and boxes[i, 1] <= cl1[1] + dlat and boxes[i, 3] >= cl0[1] - dlat]
                half = {i: float(getattr(specs[i], "width", 6.0)) / 2.0 for i in near}
                # (a road's answer is its own geometry's, whichever cell it is read in: kept per road id for the
                # course loaded, so the many reads of a cell's roads (its neighbours', the bridges', the grading's)
                # work it out once; 1.7.10, the user's server.log 2026-11-10: road geotiles waiting minutes on it)
                ids = getattr(feats, "ids", None)
                known, todo = {}, []
                with st.lock:
                    memo = st.followed_ids if st.followed_plan == plan.key else None
                    if memo is None:
                        st.followed_ids, st.followed_plan = {}, plan.key
                        memo = st.followed_ids
                    for i in near:
                        key = (str(ids[i]), round(half[i], 3)) if ids is not None else None
                        if key is not None and key in memo:
                            known[i] = memo[key]
                        else:
                            todo.append(i)
                fol = set(corridor.rows_followed(feats, todo, lines, half, courseroads.FOLLOW_UNPAVED_M,
                                                 courseroads.FOLLOW_UNPAVED_DEG)) if todo else set()
                if ids is not None:
                    with st.lock:
                        if st.followed_plan == plan.key:
                            for i in todo:
                                st.followed_ids[(str(ids[i]), round(half[i], 3))] = i in fol
                            while len(st.followed_ids) > FOLLOWED_MEMO:
                                st.followed_ids.pop(next(iter(st.followed_ids)))
                got = tuple(sorted(set(i for i, v in known.items() if v) | fol))
    feats.__dict__["_egps_followed"] = (plan.key, got)
    return got


def install_course_grade(st):
    """BeamNG.Earth 1.8.2 wears its dirt roads (grading.dirt_bumps: potholes, broken patches, deep pits, 2.5 times as
    deep on a track; dirt_bank: a lean of up to 0.2 m per m; profile_sigma: a minor one smoothed over 2.5 m, not 8).
    The course's terrain setting decides where (dirt_wear): roads.road_specs marks the course's track's specs
    (course_spec_class), the three hooks go by dirt_wear for the part. The track's own ground stays the painter's
    (relief.py, by its ground version), the same as on 1.8.1, but on Default."""
    import grading as gradingmod
    roadsmod = st.roads
    if not hasattr(gradingmod, "dirt_bumps") or getattr(gradingmod, "_egps_course_grade", False):
        return False
    cls = course_spec_class(roadsmod)
    orig_specs = roadsmod.road_specs

    def road_specs(feats, *a, **kw):
        got = orig_specs(feats, *a, **kw)
        try:
            if got is None:
                return got
            rows = course_rows(feats) + followed_rows(st, roadsmod, feats, got)
            if not rows:
                return got
            # (BeamNG.Earth hands out a copy of its remembered list each time: marked in it, the track's rows and the
            # mapped dirt roads the course runs along alone)
            out = got if isinstance(got, list) else list(got)
            for i in rows:
                if i < len(out) and out[i] is not None and not isinstance(out[i], cls):
                    out[i] = cls(*out[i])
            return out
        except Exception as e:
            st.stats["errors"] += 1
            log.warning("course painter: track specs: %s: %s", type(e).__name__, e)
            return got

    orig_bumps, orig_bank, orig_sigma = gradingmod.dirt_bumps, gradingmod.dirt_bank, gradingmod.profile_sigma

    def wear(spec):
        try:
            return dirt_wear(wear_mode(st), isinstance(spec, cls))
        except Exception:                   # (never break BeamNG.Earth's grading: its own)
            return "earth", "earth", "earth"

    def dirt_bumps(xy, spec, *a, **kw):
        return orig_bumps(xy, spec, *a, **kw) if wear(spec)[0] == "earth" else None

    def dirt_bank(xy, spec, *a, **kw):
        how = wear(spec)[1]
        if how == "earth" or (how == "rare" and lean_kept(xy)):
            return orig_bank(xy, spec, *a, **kw)
        return None

    def profile_sigma(spec, *a, **kw):         # (1.9: profile_sigma(spec, coarse=False))
        coarse = bool(a[0]) if a else bool(kw.get("coarse", False))
        if not coarse and spec.kind not in roadsmod.BUILT and wear(spec)[2] == "smooth":
            return gradingmod.DIRT_SIGMA_M
        return orig_sigma(spec, *a, **kw)

    roadsmod.road_specs = road_specs
    gradingmod.dirt_bumps, gradingmod.dirt_bank, gradingmod.profile_sigma = dirt_bumps, dirt_bank, profile_sigma
    gradingmod._egps_course_grade = True
    return True


def forget_plans():
    """This process's road plans made so far dropped from its memory (BeamNG.Earth 1.8 keeps one plan store a
    process, whatever the anchor): another course or terrain setting plans the roads again (their track, their wear),
    from the plan cache of that ground or anew. True when there was one."""
    import sys
    g = sys.modules.get("grading")
    store = getattr(g, "_ACTIVE_STORE", None) if g is not None else None
    planners = getattr(store, "planners", None)
    if planners is None:
        return False
    with store.lock:
        planners.clear()
    return True


def install_surfaces(st):
    """surface.MATERIALS with the sand and gravel layers appended (after the level's dirt, so BeamNG.Earth's own
    indices stay), and surface.paint_lots (every block's last land paint before its gas station pads) followed by the
    course's ground (surfaces.course_surfaces)."""
    import surface as surfacemod
    if getattr(surfacemod.paint_lots, "_earthgps", False):
        return
    names = [m[0] for m in surfacemod.MATERIALS]
    extra = tuple(m for m in surfaces.EXTRA_MATERIALS if m[0] not in names)
    if extra:
        surfacemod.MATERIALS = tuple(surfacemod.MATERIALS) + extra
    mats = surface_mats(surfacemod)
    orig = surfacemod.paint_lots

    def paint_lots(idx, lat, lon, *a, **kw):
        out = orig(idx, lat, lon, *a, **kw)
        try:
            md = getattr(st, "md", None)
            plan = st.current()
            c = plan.paint if plan is not None else None
            if md is None or c is None or getattr(c, "tv", 1) < surfaces.FROM_TV:
                return out
            ctx = st.course_near(md, lat, lon)
            if ctx is None:
                return out
            got = surfaces.course_surfaces(out, lat, lon, ctx[0], ctx[1], mats)
            n = int(np.count_nonzero(got != np.asarray(out)))
            if n:
                with st.lock:
                    st.stats["surface_points"] += n
            return got.astype(np.asarray(out).dtype)
        except Exception as e:          # never break BeamNG.Earth: its own surfaces then
            st.stats["errors"] += 1
            log.warning("course painter: surfaces: %s: %s", type(e).__name__, e)
            return out
    paint_lots._earthgps = True
    surfacemod.paint_lots = paint_lots
    # (terrain 7) the roads painted into the ground's photo: a cell's roads layer with the course's sand traps, rock
    # sections and crawls left out (roads_for: PHOTO_KEY), so the photo there is the place's own
    orig_segs = getattr(surfacemod, "_road_segments", None)
    if orig_segs is not None and not getattr(orig_segs, "_earthgps", False):
        def _road_segments(frame, x0, y0, size, w, h, feats_list, *a, **kw):
            try:
                feats_list = [_photo_roads(f) for f in feats_list]
            except Exception:
                pass
            return orig_segs(frame, x0, y0, size, w, h, feats_list, *a, **kw)
        _road_segments._earthgps = True
        surfacemod._road_segments = _road_segments


PHOTO_KEY = "_egps_photo"


def _photo_roads(f):
    """The roads layer f as the ground's photo is to show it (without the stretches drawn as the ground itself)."""
    d = getattr(f, "__dict__", None)
    return d.get(PHOTO_KEY, f) if d else f


def install():
    """Hook BeamNG.Earth's map data (idempotent). Returns True when installed."""
    global _state
    if _state is not None:
        return True
    import dem as demmod
    import geodesy
    import mapcells
    import mapdata
    import mapgeom
    import roads as roadsmod

    orig_cell = mapdata.MapData.cell
    orig_dem_init = demmod.Dem.__init__
    st = _State(mapdata, mapcells, mapgeom, roadsmod, geodesy, demmod, orig_cell)

    def dem_init(self, *a, **kw):
        orig_dem_init(self, *a, **kw)
        st.dems.append(self)
        if st.cache_dir is None and a and isinstance(a[0], str):
            st.cache_dir = os.path.dirname(os.path.abspath(a[0]))        # (Dem(<cache>/dem))

    def cell(self, key, layers=mapdata.LAYERS, kind="demand", *args, **kwargs):
        if st.cache_dir is None and getattr(self, "cache_dir", None):
            st.cache_dir = self.cache_dir
        st.md = self                        # (the map data the block's surfaces read the course's windows with)
        cd = orig_cell(self, key, layers, kind, *args, **kwargs)
        if _for_gradesep():
            return cd                       # (BeamNG.Earth's own neighbours' roads: _for_gradesep)
        for layer in ("buildings", "building_parts"):
            if layer in layers and cd.layers.get(layer) is not None:
                try:
                    cd.layers[layer] = _buildings_for(st, self, mapdata._key(key), cd.layers[layer], layer)
                except Exception as e:
                    st.stats["errors"] += 1
                    log.warning("course painter: buildings of %s: %s: %s", key, type(e).__name__, e)
        if "roads" in layers:
            try:
                base = cd.layers.get("roads")
                cd.layers["roads"] = st.roads_for(self, mapdata._key(key), base, kind)
            except Exception as e:              # never break BeamNG.Earth: its own roads then
                st.stats["errors"] += 1
                log.warning("course painter: cell %s: %s: %s", key, type(e).__name__, e)
        return cd

    orig_walls = roadsmod.retaining_walls

    def retaining_walls(frame, roads, elev, exact, *args, **kwargs):
        # (whatever else BeamNG.Earth passes goes along: 1.5.5 added decks=, and a wrapper that refused it failed
        # every road tile with walls)
        walls = orig_walls(frame, roads, elev, exact, *args, **kwargs)
        try:
            plan = st.current()
            if walls and plan is not None and plan.clearing:
                x0, y0, x1, y1 = exact
                la, lo, _ = frame.enu_to_geodetic(np.array([x0, x1, x0, x1]), np.array([y0, y0, y1, y1]), 0.0)
                lines = []
                for c in plan.clearing:
                    lines += corridor.course_lines(c, (float(np.min(lo)), float(np.min(la)), float(np.max(lo)),
                                                       float(np.max(la))), 60.0)
                if lines:
                    xy = []
                    for ln in lines:
                        e, n, _ = frame.geodetic_to_enu(ln[:, 1], ln[:, 0], 0.0)
                        xy.append(np.stack([np.asarray(e), np.asarray(n)], axis=1))
                    cut = corridor.cut_walls(walls, xy, on_roads=_followed_roads(roads, xy))
                    if len(cut) != len(walls) or sum(len(w["base"]) for w in cut) != sum(len(w["base"]) for w in walls):
                        st.stats["walls_cut"] += 1
                    return cut
        except Exception as e:
            st.stats["errors"] += 1
            log.warning("course painter: walls: %s: %s", type(e).__name__, e)
        return walls

    roadsmod.retaining_walls = retaining_walls

    # wheel ruts where the dirt track blends into the ground (ruts.py): extra pieces of the road tile, drawn over the
    # dirt like the road markings (roadmesh's "mark" layer)
    orig_build = roadsmod.build_tile

    def build_tile(frame, tx, ty, cells, elev, *a, **kw):
        chunks = orig_build(frame, tx, ty, cells, elev, *a, **kw)
        try:
            plan = st.current()
            c = plan.paint if plan is not None else None
            if c is not None and getattr(c, "ruts", "auto") != "off":
                # BeamNG.Earth 1.6 paints the carriageways into the ground's photo (roads.ROADS_IN_GROUND): the tile
                # has no dirt pieces of its own any more, so the ruts follow the dirt roads' centrelines as the
                # tile would have laid them
                # (1.8: a dirt or gravel road gets a rutted strip of its own over the ground again, roads.DIRT_STRIPS:
                # the ruts follow the track's strip, BeamNG.Earth's own pieces, its bends rounded as it rounds them)
                mats = track_materials(roadsmod)
                strips = [ch for ch in chunks if ch.get("m") in mats and not ch.get("deck")] \
                    if getattr(roadsmod, "DIRT_STRIPS", False) else []
                track = strips or (dirt_chunks(roadsmod, frame, tx, ty, cells, elev, *a, **kw)
                                   if getattr(roadsmod, "ROADS_IN_GROUND", False) else chunks)
                def rutted(xy):         # (terrain 5: the rutted sections, relief.ruts_at)
                    la, lo, _ = frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
                    return st.ruts_at(np.atleast_1d(la), np.atleast_1d(lo))
                extra = ruts.rut_chunks(track, frame, st.imagery(), c.ruts, _course_in_frame(c, frame, track),
                                        track_material=mats,
                                        rutted_fn=rutted if getattr(c, "tv", 1) >= relief.RUTS_TV else None) \
                    if track else []
                if extra:
                    chunks = list(chunks) + extra
                    with st.lock:
                        st.stats["ruts"] += len(extra)
        except Exception as e:
            st.stats["errors"] += 1
            log.warning("course painter: ruts: %s: %s", type(e).__name__, e)
        return chunks

    roadsmod.build_tile = build_tile
    try:
        import roadmesh
        orig_layer = roadmesh.layer_of

        def layer_of(chunk):
            return "mark" if chunk.get("m") == ruts.RUT_MATERIAL else orig_layer(chunk)
        roadmesh.layer_of = layer_of
    except Exception:                       # (an older BeamNG.Earth: DecalRoads, render priority orders them)
        pass
    # BeamNG.Earth 1.8's mapped props on the road tiles (fences, noise walls, containers, barns, billboards, towers,
    # picnic tables, bus shelters): none in the course's way (corridor.props_off)
    try:
        install_props(st)
    except Exception as e:                  # (no blockworker._tile_parts: BeamNG.Earth before 1.7)
        log.debug("course painter: no props hook (%s: %s)", type(e).__name__, e)
    # the ground's surfaces along the course (surfaces.py, terrain version 3): sand, mud, loose and packed dirt, gravel
    # in BeamNG.Earth's per-sample ground models of the physics block, after its land cover, roads and lots
    try:
        install_surfaces(st)
    except Exception as e:
        log.warning("course painter: no course surfaces (%s: %s)", type(e).__name__, e)
    # the track's relief (relief.py): added to the graded heights everything takes (the physics block, the road tiles'
    # mesh, the near ground tiles, the vegetation's ground), so they agree; before it, a sloping cut bank where the
    # grading stood a bare step of ground beside the dirt track (banks.py)
    try:
        import grading as gradingmod
        orig_apply = gradingmod.Grader.apply

        def apply(self, lat, lon, base, lift=0.0, roads_only=False, *args, **kwargs):
            # (whatever else BeamNG.Earth passes goes along: 1.6.3 added planned_only=, the AI road graph's heights)
            out = orig_apply(self, lat, lon, base, lift, roads_only, *args, **kwargs)
            if roads_only:                  # (a tunnel's ends)
                return out
            try:
                ctx = st.course_near(self.md, lat, lon)
                if ctx is None:
                    return out
                near = relief.nearest(ctx[0], ctx[1], np.ravel(lat), np.ravel(lon))
                if not (kwargs.get("planned_only") or (args and args[0])):
                    # (not for the AI road graph's heights: only cells planned already, on the roads themselves)
                    def grade_fn(la, lo, z):
                        return orig_apply(self, la, lo, z, lift)
                    try:
                        out = st.banks_at(self, grade_fn, lat, lon, base, out, ctx, near)
                    except Exception as e:  # (BeamNG.Earth's step then)
                        st.stats["errors"] += 1
                        log.warning("course painter: banks: %s: %s", type(e).__name__, e)
                dz = st.relief_at(self.md, lat, lon, near=near, ctx=ctx)
                if dz is not None:
                    out = np.asarray(out, np.float64) + dz.reshape(np.shape(out))
            except Exception as e:          # never break BeamNG.Earth: its own heights then
                st.stats["errors"] += 1
                log.warning("course painter: relief: %s: %s", type(e).__name__, e)
            return out
        apply._earthgps = True
        gradingmod.Grader.apply = apply
    except Exception as e:
        log.warning("course painter: no track relief (%s: %s)", type(e).__name__, e)
    # BeamNG.Earth 1.8.2's worn dirt roads (grading.dirt_bumps, dirt_bank, profile_sigma): not on the course's track
    try:
        install_course_grade(st)
    except Exception as e:                  # (BeamNG.Earth before 1.8.2: nothing to keep off)
        log.debug("course painter: no dirt road wear hook (%s: %s)", type(e).__name__, e)
    # boulders beside the track in canyons: BeamNG.Earth's own vegetation rocks (--trees on)
    try:
        import vegetation as vegmod
        orig_veg_cell = vegmod.Vegetation.cell

        def veg_cell(self, key):
            try:
                pk = st.current().key if st.current() is not None else None
                if pk != st.veg_plan:       # (another course: the cells this process remembers were made for the old)
                    st.veg_plan = pk
                    with self._lock:
                        self._mem.clear()
            except Exception:
                pass
            items = orig_veg_cell(self, key)
            try:
                items = st.off_track(key, items, vegmod, self.md)
            except Exception as e:
                st.stats["errors"] += 1
                log.warning("course painter: trees off the track: %s: %s", type(e).__name__, e)
            try:
                return st.rocks_for(key, items, vegmod, self.md)
            except Exception as e:
                st.stats["errors"] += 1
                log.warning("course painter: rocks: %s: %s", type(e).__name__, e)
                return items
        vegmod.Vegetation.cell = veg_cell
        # its cells kept on disk per GPS ground too (as the plan and revisit caches): one built with another course's
        # track (or none) would keep its trees on this one's
        orig_veg_path = vegmod.Vegetation._path

        def veg_path(self, x, y):
            p = orig_veg_path(self, x, y)
            tag = share_tag(st)
            if not p or tag == "-":
                return p
            d, f = os.path.split(p)
            return os.path.join(d, "egps-" + tag, f)
        vegmod.Vegetation._path = veg_path
    except Exception as e:
        log.warning("course painter: no rocks by the track (%s: %s)", type(e).__name__, e)
    # BeamNG.Earth 1.6's compute sharing (peerwork.py): far tiles built by other players' servers (a BeamMP group) or
    # helpers. Its "same code" check hashes BeamNG.Earth's own sources only, so a server with the course painter
    # passed for one without, and two with different courses for the same: tiles of another ground would be swapped.
    # Every job and reply now carries the GPS ground's tag (share_tag): a server answers only jobs of its own ground,
    # and a reply of another ground (or of a server without the painter) is refused (built here instead).
    try:
        install_sharing(st)
    except Exception as e:                  # (no peerwork: BeamNG.Earth before 1.6)
        log.debug("course painter: no compute sharing hook (%s: %s)", type(e).__name__, e)
    # BeamNG.Earth 1.6.1's plan cache (plancache.py): a cell's road plans, the dirt track's among them, shared between
    # its processes on disk per anchor and grading settings. Ours go in a folder of their own per GPS ground, so ground
    # built again at the same anchor with another course, size or a replay's recorded ground never takes old plans.
    try:
        install_plancache(st)
    except Exception as e:                  # (no plancache: BeamNG.Earth before 1.6.1)
        log.debug("course painter: no plan cache hook (%s: %s)", type(e).__name__, e)
    # BeamNG.Earth 1.6.3's revisit cache (revisit.py): what a place was built with, kept for the next visit, keyed by
    # the GPS ground too (and a build the painter could not finish is not kept)
    try:
        install_revisit(st)
    except Exception as e:                  # (no revisit cache: BeamNG.Earth before 1.6.3)
        log.debug("course painter: no revisit cache hook (%s: %s)", type(e).__name__, e)
    demmod.Dem.__init__ = dem_init
    mapdata.MapData.cell = cell
    _state = st
    mark = os.environ.get("EARTHGPS_MARK_DIR")           # (tests: which processes have the hook)
    if mark:
        os.makedirs(mark, exist_ok=True)
        with open(os.path.join(mark, f"{os.getpid()}-{multiprocessing.current_process().name}"), "w"):
            pass
    # (the heartbeat and the planner ahead of the car: the server's main process only. Not decided by the name here:
    # in the .exe every worker is the program started again, and runs this before multiprocessing takes over, named
    # "MainProcess" with no parent: every worker started its own planner, ten of them fetching and planning at once,
    # and the road tiles and the ground waited behind them, the user 2026-10-29, "it still stalls on the loading".
    # _heartbeat asks _is_server_main once the process is what it is)
    threading.Thread(target=_heartbeat, name="offroad-heartbeat", daemon=True).start()
    return True


_GPS_CODE = None


def gps_code_id():
    """A fingerprint of the painter's own code (gpsd/*.py): two servers with it the same build the same ground."""
    global _GPS_CODE
    if _GPS_CODE is None:
        import hashlib as _h
        here = os.path.dirname(os.path.abspath(__file__))
        h = _h.sha256()
        for name in sorted(os.listdir(here)):
            if name.endswith(".py"):
                with open(os.path.join(here, name), "rb") as f:
                    h.update(name.encode() + b"\0" + f.read())
        _GPS_CODE = h.hexdigest()[:12]
    return _GPS_CODE


def share_tag(st):
    """The GPS ground this server builds (its plan and the painter's code), "-" when it paints and clears nothing (as
    BeamNG.Earth's own tiles)."""
    plan = st.current() if st is not None else None
    if plan is None:
        return "-"
    return hashlib.sha1(f"{plan.key}|{gps_code_id()}".encode()).hexdigest()[:12]


def _check_reply(st, head):
    """Raises for a far tile (a reply with "built") of another GPS ground than this server's, or from a server without
    the painter (no tag) while this one paints a course."""
    if isinstance(head, dict) and head.get("ok") and "built" in head and head.get("egps", "-") != share_tag(st):
        with st.lock:
            st.stats["share_refused"] = st.stats.get("share_refused", 0) + 1
        raise RuntimeError("a tile of another course's ground (Offroad Companion)")


def install_revisit(st):
    """Hooks revisit.key (BeamNG.Earth 1.6.3+): what BeamNG.Earth keeps of a place to load again on the next visit (road
    tiles, far tiles and their buildings, road plans, a cell's road facts: its revisit cache) keyed by the GPS ground too.
    Its own key holds its code and settings, not the course painter's: a place built with one course's track, size or
    terrain came back under another, or with none (and BeamNG.Earth's own, painted with nothing, under a course). No
    GPS ground ("-"): BeamNG.Earth's own key, so its cache is shared as it is."""
    import revisit as rv
    orig = rv.key
    if getattr(orig, "_earthgps", False):
        return True

    def key(kind, *parts):
        tag = share_tag(st)
        if tag == "-":
            return orig(kind, *parts)
        return orig(kind, *parts, ("egps", tag))
    key._earthgps = True
    rv.key = key
    # (1.8: the items kept across updates, by their output's format: a cell's road plans (the track's among them) by
    # the GPS ground too; its road facts are by their layer's cell id, which a layer with the track has its own of)
    of = getattr(rv, "format_key", None)
    if of is not None and not getattr(of, "_earthgps", False):
        def format_key(kind, fmt, *parts):
            tag = share_tag(st)
            if tag == "-" or kind != "plans":
                return of(kind, fmt, *parts)
            return of(kind, fmt, *parts, ("egps", tag))
        format_key._earthgps = True
        format_key._orig = of
        rv.format_key = format_key
    return True


def _fault():
    """The course painter left something out for want of its data (a window not planned yet): BeamNG.Earth's builds
    running now are not kept in its revisit cache (1.6.3+; they would come back without the track), as when its own
    downloads fail."""
    try:
        import revisit as rv
        rv.fault()
    except Exception:
        pass


def install_plancache(st):
    """Hooks plancache.for_grader (BeamNG.Earth 1.6.1+): each GPS ground's road plans in a folder of their own (beside
    BeamNG.Earth's, the signature its last part as BeamNG.Earth names it: 1.8's world bundles export a folder by that
    name). 1.8 keeps a cell's plans across updates in its revisit cache (format_key, not key: install_revisit's) and
    shares them with the BeamMP server's other players (mpshare: matched by PlanCache._bake_expect) and baked packs
    (bakepack: by the same expect): both get the GPS ground's tag, so plans with one course's track never come back
    for another course or none, nor BeamNG.Earth's own for a course. A pinned world bundle (1.8, BNGE_WORLD_BUNDLE:
    plans made elsewhere, BeamNG.Earth's own) is not used while a course is painted: its cells are planned here."""
    import plancache as pc
    orig = pc.for_grader
    if getattr(orig, "_earthgps", False):
        return True

    def for_grader(cache_dir, grader, widths, wet):
        got = orig(cache_dir, grader, widths, wet)
        tag = share_tag(st)
        if got is None or tag == "-":
            return got
        if not getattr(got, "dir", None):       # (a pinned bundle's: another machine's plans, without the track)
            return None
        head, sig = os.path.split(got.dir)
        frames, base = os.path.basename(head), os.path.dirname(head)
        got.dir = os.path.join(base, "egps-" + tag, frames, sig)
        return got
    for_grader._earthgps = True
    pc.for_grader = for_grader
    be = getattr(getattr(pc, "PlanCache", None), "_bake_expect", None)
    if be is not None and not getattr(be, "_earthgps", False):
        def _bake_expect(self):
            out = be(self)
            tag = share_tag(st)
            if tag != "-":
                out = dict(out, egps=tag)
            return out
        _bake_expect._earthgps = True
        pc.PlanCache._bake_expect = _bake_expect
    return True


def install_sharing(st):
    """Hooks peerwork (BeamNG.Earth 1.6+) so far tiles are shared only between servers building the same GPS ground."""
    import peerwork as pw
    orig_header, orig_check, orig_reply = pw.job_header, pw.check_job, pw.reply_of
    orig_call = pw._Conn.call

    def job_header(fn_name, args, settings):
        h = orig_header(fn_name, args, settings)
        h["settings"] = dict(h.get("settings") or {}, egps=share_tag(st))     # (in the job's key too: ReplyCache)
        return h

    def check_job(h):
        out = orig_check(h)
        theirs = (h.get("settings") or {}).get("egps", "-")
        if theirs != share_tag(st):
            raise ValueError("another course's ground (Offroad Companion)")
        return out

    def reply_of(name, result, tex=None):
        head, blobs = orig_reply(name, result, tex)
        head["egps"] = share_tag(st)
        return head, blobs

    def call(self, header):
        head, blobs = orig_call(self, header)
        _check_reply(st, head)
        return head, blobs

    pw.job_header, pw.check_job, pw.reply_of = job_header, check_job, reply_of
    pw._Conn.call = call
    return True


def _followed_roads(roads, course_xy):
    """The ground roads (BeamNG.Earth's retaining_walls input: (fid, spec, pts (n, 3) frame m, _)) the clearing lines
    run along, as segments (a, b, half widths) in the frame: a wall standing on one is in the way."""
    A, B, H = [], [], []
    for item in roads:
        try:
            fid, spec, pts = item[0], item[1], np.asarray(item[2], np.float64)
        except (TypeError, IndexError, ValueError):
            continue
        if spec is None or len(pts) < 2 or str(fid).startswith(courseroads.ID_PREFIX):
            continue
        A.append(pts[:-1, :2])
        B.append(pts[1:, :2])
        H.append(np.full(len(pts) - 1, float(getattr(spec, "width", 6.0)) / 2.0))
    if not A:
        return None
    a, b, h = np.concatenate(A), np.concatenate(B), np.concatenate(H)
    allc = np.concatenate(course_xy)
    lo, hi = allc.min(axis=0) - 80.0, allc.max(axis=0) + 80.0
    near = (np.maximum(a, b) >= lo).all(axis=1) & (np.minimum(a, b) <= hi).all(axis=1)
    a, b, h = a[near], b[near], h[near]
    m = corridor.followed((a, b, h), course_xy)
    return (a[m], b[m], h[m]) if m.any() else None


DIRT_KINDS = ("dirt", "gravel")


def install_props(st):
    """Hooks blockworker._tile_parts (a road tile's parts, in the road tiles' processes): its props (P.props: Forest
    rows in the tile's frame) without those standing in the course's way (props_off_course)."""
    import blockworker as bw
    orig = bw._tile_parts
    if getattr(orig, "_earthgps", False):
        return True

    def _tile_parts(mark, frame, *a, **kw):
        P = orig(mark, frame, *a, **kw)
        try:
            if getattr(P, "props", None):
                n = len(P.props)
                P.props = props_off_course(st, frame, P.props)
                if len(P.props) < n:
                    with st.lock:
                        st.stats["props_off"] = st.stats.get("props_off", 0) + n - len(P.props)
        except Exception as e:              # (never break BeamNG.Earth's tile: its props as they were)
            st.stats["errors"] += 1
            log.warning("course painter: props: %s: %s", type(e).__name__, e)
        try:
            if getattr(P, "guardrail_rows", None):
                n = len(P.guardrail_rows)
                P.guardrail_rows = rails_off_course(st, frame, P.guardrail_rows)
                if len(P.guardrail_rows) < n:
                    with st.lock:
                        st.stats["rails_off"] = st.stats.get("rails_off", 0) + n - len(P.guardrail_rows)
        except Exception as e:              # (its guard rails as they were)
            st.stats["errors"] += 1
            log.warning("course painter: guard rails: %s: %s", type(e).__name__, e)
        return P
    _tile_parts._earthgps = True
    bw._tile_parts = _tile_parts
    return True


def course_lines_frame(plan, frame, rows, pad_m=60.0):
    """[(course, [(n, 2) lines in frame])] of the plan's clearing lines near rows ([_, x, y, ...] in frame)."""
    xy = np.array([[float(r[1]), float(r[2])] for r in rows if len(r) >= 3], np.float64)
    if not len(xy):
        return []
    la, lo, _ = frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
    la, lo = np.atleast_1d(la), np.atleast_1d(lo)
    bounds = (float(lo.min()), float(la.min()), float(lo.max()), float(la.max()))
    out = []
    for c in plan.clearing:
        lines = []
        for ln in corridor.course_lines(c, bounds, pad_m):
            e, n, _ = frame.geodetic_to_enu(ln[:, 1], ln[:, 0], np.zeros(len(ln)))
            lines.append(np.stack([np.asarray(e), np.asarray(n)], axis=1))
        if lines:
            out.append((c, lines))
    return out


def rails_off_course(st, frame, rows):
    """rows (a road tile's guard rail rows in frame, P.guardrail_rows) with corridor.rails_off's gaps where the
    course lines go through them (the race course only: a GPS route runs along its roads)."""
    plan = st.current()
    if plan is None or not plan.clearing or not rows:
        return rows
    for c, lines in course_lines_frame(plan, frame, rows):
        if getattr(c, "kind", "course") == "course":
            rows = corridor.rails_off(rows, lines)
    return rows


def props_off_course(st, frame, rows):
    """rows (a road tile's prop rows in frame) without corridor.props_off's near any line the plan clears."""
    plan = st.current()
    if plan is None or not plan.clearing or not rows:
        return rows
    xy = np.array([[float(r[1]), float(r[2])] for r in rows if len(r) >= 3], np.float64)
    if not len(xy):
        return rows
    la, lo, _ = frame.enu_to_geodetic(xy[:, 0], xy[:, 1], np.zeros(len(xy)))
    la, lo = np.atleast_1d(la), np.atleast_1d(lo)
    bounds = (float(lo.min()), float(la.min()), float(lo.max()), float(la.max()))
    for c in plan.clearing:
        lines = []
        for ln in corridor.course_lines(c, bounds, 60.0):
            e, n, _ = frame.geodetic_to_enu(ln[:, 1], ln[:, 0], np.zeros(len(ln)))
            lines.append(np.stack([np.asarray(e), np.asarray(n)], axis=1))
        if lines:
            rows = corridor.props_off(rows, lines, c.clear_m)
    return rows


def track_materials(roadsmod):
    """The materials the dirt track's pieces are drawn with in this BeamNG.Earth: Johnson Valley's dirt road, and (1.8)
    its dirt and gravel strips (roads.DIRT_MATERIALS)."""
    return frozenset(("m_dirt_road",) + tuple(getattr(roadsmod, "DIRT_MATERIALS", ())))


def dirt_chunks(roadsmod, frame, tx, ty, cells, elev, urban_fn=None, walks=None, bridges=None, widths=None, *a,
                left_hand=False, **kw):
    """The dirt and gravel carriageways of a road tile as BeamNG.Earth laid them as pieces before it painted them into
    the ground (roads.build_tile with ROADS_IN_GROUND off: the same specs, rings, heights, clipping and splitting):
    what the ruts follow. Not drawn themselves."""
    x0, y0, x1, y1 = roadsmod.tile_bbox(tx, ty)
    ov, nm = roadsmod.OVERLAP, roadsmod.NEAR_M
    box = (x0 - ov, y0 - ov, x1 + ov, y1 + ov)
    near = (x0 - nm, y0 - nm, x1 + nm, y1 + nm)
    seen = {}
    for feats in cells:
        if feats is None or len(feats) == 0:
            continue
        specs = roadsmod.road_specs(feats, urban_fn, widths, left_hand)
        for i in range(len(feats)):
            sp = specs[i]
            if sp is None or sp.kind not in DIRT_KINDS or str(feats.ids[i]) in seen:
                continue
            seen[str(feats.ids[i])] = (feats, i, sp)
    rings = []
    for fid in sorted(seen):
        feats, i, sp = seen[fid]
        fb = feats.boxes(frame)[i]
        if fb[2] < near[0] or fb[0] > near[2] or fb[3] < near[1] or fb[1] > near[3]:
            continue
        for ring in roadsmod.ground_parts(feats, i):
            rings.append((sp, ring))
    if not rings:
        return []
    lon = np.concatenate([r[:, 0] for _, r in rings])
    lat = np.concatenate([r[:, 1] for _, r in rings])
    e, n, u = frame.geodetic_to_enu(lat, lon, np.asarray(elev(lat, lon), np.float64))
    out, k = [], 0
    for sp, ring in rings:
        m = len(ring)
        pts = np.stack([e[k:k + m], n[k:k + m], u[k:k + m]], axis=1)
        k += m
        look = roadsmod.look_of(sp) if hasattr(roadsmod, "look_of") else roadsmod.LOOK[sp.kind]
        for piece in roadsmod.clip_polyline(pts, *box):
            for c in roadsmod.split(roadsmod.densify(roadsmod.simplify(piece))):
                if len(c) >= 2:
                    out.append(roadsmod._chunk(look, sp.width, c))
    return out


def _course_in_frame(course, frame, chunks, pad=60.0):
    """The course's line(s) near the chunks, in the frame: [(k, 2)]."""
    pts = np.concatenate([np.asarray(c["n"], np.float64)[:, :2] for c in chunks if c.get("n")])
    x0, y0 = pts.min(axis=0) - pad
    x1, y1 = pts.max(axis=0) + pad
    la, lo, _ = frame.enu_to_geodetic(np.array([x0, x1, x0, x1]), np.array([y0, y0, y1, y1]), np.zeros(4))
    lines = corridor.course_lines(course, (float(np.min(lo)), float(np.min(la)), float(np.max(lo)),
                                           float(np.max(la))), pad)
    out = []
    for ln in lines:
        e, n, _ = frame.geodetic_to_enu(ln[:, 1], ln[:, 0], np.zeros(len(ln)))
        out.append(np.stack([np.asarray(e), np.asarray(n)], axis=1))
    return out


# -- planning the track ahead of the car (a process of its own) ------------------------------------------------------
# A map cell's road data is on BeamNG.Earth's critical path: its terrain blocks and near tiles are graded from the
# road plans, and a tile built before them shows the ungraded ground over the road (non-colliding, until it is built
# again; the user 2026-10-21: "non collidable terrain on top of the actual street road ... when racing"). The dirt
# track's windows (1 km each: roads, terrain, tree cover along it) were planned the first time a cell asked, in its
# path. This process plans them around the car first (the game's pose, through the companion: pose.json), nearest
# and ahead first, and writes them where every process reads them. Its own process at low priority: the planning is
# mostly pure Python, and a thread would hold the server's event loop.
PREFETCH_S = 2.0
# (1.7.10, the user 2026-11-10: "sometimes it takes too long to change the track into how it's supposed to be"; at 150
# km/h the planner's 25 s ahead in a straight line was the next km, and the windows its background downloads waited
# for were planned by the builds themselves, with the car on them) The windows along the course from the car's place on
# it: PREFETCH_AHEAD_M ahead (in the course's order: round the bends), PREFETCH_BEHIND_M behind, and every other pass
# of the course within PREFETCH_NEAR_M; the first PREFETCH_URGENT_M ahead with the builds' own download priority.
PREFETCH_AHEAD_M = 10000.0
PREFETCH_BEHIND_M = 1000.0
PREFETCH_NEAR_M = 2500.0
PREFETCH_URGENT_M = 4000.0
PREFETCH_R_M = 5000.0       # (the car this near the course at most: farther, nothing is planned ahead)
PREFETCH_PASS_S = 20.0      # a pass plans for this long at most before the car's place is read again
POSE_MAX_AGE_S = 60.0


def _low_priority():
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        else:
            os.nice(10)
    except Exception:
        pass


def course_position(course, pose, radius=PREFETCH_R_M):
    """The course's sample index nearest the pose ({lat, lon, speed, heading}) within radius, preferring one whose
    course runs the car's way when it is moving (a course out and back along one road), or None. Pure."""
    lat, lon = float(pose["lat"]), float(pose["lon"])
    kx = 111320.0 * max(0.05, math.cos(math.radians(lat)))
    ks = course.windows_near(lat, lon, radius)
    if not ks:
        return None
    sp, hd = float(pose.get("speed") or 0.0), pose.get("heading")
    hx = hy = None
    if hd is not None and sp > 3.0:
        hx, hy = math.sin(math.radians(float(hd))), math.cos(math.radians(float(hd)))
    best = None
    for k in ks:
        a, b = course.inner(k)
        for i in range(a, b + 1):
            dx, dy = (course.lon[i] - lon) * kx, (course.lat[i] - lat) * 111320.0
            d = math.hypot(dx, dy)
            if d > radius:
                continue
            pen = 0.0
            if hx is not None:
                j = min(i + 1, course.n - 1)
                i0 = j - 1
                tx, ty = (course.lon[j] - course.lon[i0]) * kx, (course.lat[j] - course.lat[i0]) * 111320.0
                if tx * hx + ty * hy < 0:
                    pen = 200.0                 # (the other way: another pass, unless much nearer)
            key = (d + pen, i)
            if best is None or key < best:
                best = key
    return best[1] if best else None


def prefetch_plan(course, pose):
    """[(window, urgent)] to plan for the car at pose, in order: along the course ahead of its place on it, then just
    behind it, then the other passes of the course near it. Pure."""
    i = course_position(course, pose)
    if i is None:
        return []
    out, seen = [], set()

    def add(k, urgent):
        if 0 <= k < course.nwin and k not in seen:
            seen.add(k)
            out.append((k, urgent))
    k0 = min(course.nwin - 1, i // courseroads.WINDOW)
    step = courseroads.WINDOW * courseroads.STEP_M
    ahead = int(math.ceil(PREFETCH_AHEAD_M / step))
    for j in range(ahead + 1):
        add(k0 + j, j * step <= PREFETCH_URGENT_M)
    for j in range(1, int(math.ceil(PREFETCH_BEHIND_M / step)) + 1):
        add(k0 - j, True)
    lat, lon = float(pose["lat"]), float(pose["lon"])
    kx = 111320.0 * max(0.05, math.cos(math.radians(lat)))
    near = []
    for k in course.windows_near(lat, lon, PREFETCH_NEAR_M):
        x0, y0, x1, y1 = course.boxes[k]
        nx, ny = min(max(lon, x0), x1), min(max(lat, y0), y1)
        near.append((math.hypot((nx - lon) * kx, (ny - lat) * 111320.0), k))
    for _, k in sorted(near):
        add(k, True)
    return out


def prefetch_order(course, pose, radius=PREFETCH_R_M, ahead_s=None):
    """Window indices prefetch_plan plans, in its order. Pure."""
    return [k for k, _ in prefetch_plan(course, pose)]


def _prefetcher(cache_dir):
    """The prefetch process: BeamNG.Earth's MapData of its own (same cache folder), the painter's windows planned
    along the course ahead of the car and written to disk."""
    _low_priority()
    try:
        import mapdata as mdmod
        import netfetch
        md = mdmod.MapData(cache_dir, fetcher=netfetch.Fetcher())
    except Exception as e:
        print(f"Offroad Companion: track prefetch unavailable ({type(e).__name__}: {e})", file=sys.stderr)
        return
    said = 0.0
    while True:
        try:
            made = prefetch_once(_state, md)
        except Exception:
            made = []
        if time.monotonic() - said > PREFETCH_SAY_S:
            said = time.monotonic()
            try:
                got = ready_ahead(_state)
                if got is not None:
                    print(f"Offroad Companion: the track is planned {got[0]:.1f} km ahead of the car (km {got[1]:.1f} "
                          f"of the course)", file=sys.stderr, flush=True)
            except Exception:
                pass
        if not made:
            time.sleep(PREFETCH_S)


PREFETCH_SAY_S = 60.0


def ready_ahead(st):
    """(km of the course planned without a gap from the car's place on it, the car's km on the course), or None."""
    plan = st.current() if st else None
    course = plan.paint if plan is not None else None
    pose = paintfile.read_json(paintfile.pose_path())
    if course is None or not isinstance(pose, dict):
        return None
    i = course_position(course, pose)
    if i is None:
        return None
    wdir = paintfile.windows_dir(course.cid)
    rough = ROUGH.get(getattr(course, "rough", "on"), 1.0)
    k = i // courseroads.WINDOW
    end = k
    while end < course.nwin and os.path.exists(os.path.join(wdir, f"w{end:06d}.json")) and \
            (not rough or os.path.exists(os.path.join(wdir, f"r{end:06d}.json"))):
        end += 1
    ahead = max(0.0, (min(course.n - 1, end * courseroads.WINDOW) - i) * courseroads.STEP_M / 1000.0)
    return ahead, i * courseroads.STEP_M / 1000.0


def prefetch_once(st, md, limit=None):
    """One pass: the windows prefetch_plan names that are not planned yet, planned (the urgent ones with the builds'
    download priority, without waiting on another process planning one), for PREFETCH_PASS_S at most or `limit`
    windows. Returns their indices."""
    plan = st.current() if st else None
    course = plan.paint if plan is not None else None
    pose = paintfile.read_json(paintfile.pose_path())
    if course is None or not isinstance(pose, dict) or time.time() - float(pose.get("t") or 0) > POSE_MAX_AGE_S:
        return []
    made = []
    t0 = time.monotonic()
    rough = ROUGH.get(getattr(course, "rough", "on"), 1.0)
    wdir = paintfile.windows_dir(course.cid)
    for k, urgent in prefetch_plan(course, pose):
        if (limit is not None and len(made) >= limit) or time.monotonic() - t0 > PREFETCH_PASS_S:
            break
        kind = "demand" if urgent else "background"
        did = False
        with st.lock:
            done = k in st.wins
        if not done and not os.path.exists(os.path.join(wdir, f"w{k:06d}.json")):
            did = st.window(md, course, k, kind, wait=False) is not None
        if rough:
            with st.lock:
                rdone = k in st.rwins
            if not rdone and not os.path.exists(os.path.join(wdir, f"r{k:06d}.json")):
                did = (st.relief_window(md, course, k, kind, wait=False) is not None) or did
        if did:
            made.append(k)
    if made:
        with st.lock:
            st.stats["prefetched"] = st.stats.get("prefetched", 0) + len(made)
    return made


def _for_gradesep():
    """Is this BeamNG.Earth 1.7's grade separation reading a cell's neighbours (gradesep._neighbours: its own threads)?
    They get BeamNG.Earth's roads as they are, never the course's track merged in: that plans the course's windows, and
    planning a window reads its cells' road specs, whose level ranges ask gradesep for the neighbours again, through
    these same threads. A window's planner then waited on its neighbours' reads, which waited on the window: the road
    tiles stuck at 0 for good (Ensenada's cells, which have short tunnels: the user's server.log, 2026-10-29, every
    road worker in window -> cell_roads -> road_specs -> _level_ranges -> gradesep -> cell -> window). The grade
    separations are found among the map's roads and railways; the dirt track takes no part in them."""
    return threading.current_thread().name.startswith(GRADESEP_THREADS)


GRADESEP_THREADS = "gradesep-cells"     # (gradesep.py's ThreadPoolExecutor thread_name_prefix)


def _is_server_main():
    """This process is the server's own (not a worker it started, nor the planner): asked after the process has
    started (a spawned worker is named after its parent until then). Its parent, if any, is not a multiprocessing one:
    the .exe starts the server as a program of its own."""
    if any(a == "--multiprocessing-fork" or a.startswith("--multiprocessing-fork") for a in sys.argv[1:]):
        return False                # (a worker of the .exe: started as the program again, its main runs before
                                    # multiprocessing takes over, so it is "MainProcess" with no parent until then)
    me = multiprocessing.current_process()
    return (multiprocessing.parent_process() is None and not me.daemon and me.name == "MainProcess"
            and not getattr(me, "_inheriting", False))


def _start_prefetch(st):
    if not _is_server_main():           # (never more than the one planner; a daemonic process can't start one)
        return
    p = getattr(st, "prefetch_proc", None)
    if p is not None and p.is_alive():
        return
    if not st.cache_dir or os.environ.get("EARTHGPS_PREFETCH", "on") == "off":
        return
    try:
        ctx = multiprocessing.get_context("spawn")
        p = ctx.Process(target=_prefetcher, args=(st.cache_dir,), name="offroad-prefetch", daemon=True)
        p.start()
        st.prefetch_proc = p
        log.info("course painter: planning the track ahead of the car (process %s)", p.pid)
    except Exception as e:
        st.prefetch_proc = None
        log.warning("course painter: no track prefetch: %s: %s", type(e).__name__, e)


def _heartbeat():
    started = time.time()
    time.sleep(3.0)                 # (after BeamNG.Earth has set up its logging)
    if not _is_server_main():       # (a worker: by now it knows it is one)
        return
    log.info("Offroad Companion course painter ready: dirt tracks along the course in %s", paintfile.course_path())
    geo_reset = False
    while True:
        if not geo_reset:                   # (BeamNG.Earth's server module: imported by now, or on a later beat)
            try:
                geo_reset = _install_geo_reset()
            except Exception as e:
                geo_reset = True
                log.warning("course painter: no geotile reset: %s: %s", type(e).__name__, e)
        st = _state
        c = st.current() if st else None
        if st is not None and c is not None and c.paint is not None:
            _start_prefetch(st)
        try:
            paintfile.write_json(paintfile.heartbeat_path(), {
                "pid": os.getpid(), "t": time.time(), "started": started, "version": paintfile.VERSION,
                "algo": courseroads.ALGO, "course": c.name if c else None,
                "cid": c.paint.cid if c and c.paint else None, "lines": [l.kind for l in c.lines] if c else [],
                "seal": c.paint.seal if c and c.paint else None, "terrain": terrain.VERSION,
                "stats": dict(st.stats) if st else {}})
        except OSError:
            pass
        time.sleep(HEARTBEAT_S)


# -- BeamNG.Earth 1.7.2's geotiles: what the game keeps across rebases and teleports, sent again for a new course ------
# BeamNG.Earth 1.7.2 builds the road tiles' content, the vegetation and the far buildings once per tile of a global grid
# ("g17_x_y"), and the game keeps them across rebases and teleports near: a place built before a course was loaded (or
# with another course, size or terrain) kept its buildings and trees on the new track. The game asks for them again
# (main.lua refreshRoads, once every process reads the new course): it drops its roads (BeamNG.Earth's roads off and
# on: roads_reset, the road tiles' trackers made anew) and its trees (trees.clear), then sends GEO_RESET, and this
# server makes the vegetation's and far buildings' trackers anew, so everything round the car comes again from the new
# ground into a game that has nothing of it.
# (1.6.8 made the trackers anew from here, without the game dropping its tiles: a tile sent again went into the one the
# game kept, its trees made at the old one's placement, and the tiles the old trackers had sent were never dropped:
# trees hanging in the sky far off, the user 2026-10-31.)
GEO_RESET = "offroad_geo_reset"


def refresh_geo(conn):
    """On the connection's event loop, after the game dropped its trees and roads (GEO_RESET): its vegetation and far
    buildings' trackers made anew (the roads': roads_reset, before it), so the tiles round it are sent again. Only the
    geotile ones (BeamNG.Earth 1.7.2+): an anchor's own tiles go with the next world shift as before. Returns what was
    made anew."""
    done = []
    veg = getattr(conn, "veg", None)
    if veg is not None and getattr(veg, "geo", False):
        import vegetation as vegmod
        veg.close()
        conn.veg = vegmod.Tracker(veg.send_m, veg.drop_m, geo=True)
        done.append("vegetation")
    if getattr(conn, "far_geo", False) and hasattr(conn, "make_far_trackers"):
        conn.make_far_trackers(True)
        done.append("far buildings")
    return done


def _install_geo_reset():
    """BeamNG.Earth's connections (earthd.Connection, this server process) answer GEO_RESET (refresh_geo); every other
    message as before."""
    em = sys.modules.get("earthd")
    if em is None or not hasattr(em, "Connection"):
        return False                        # (not imported yet: asked again on the next beat)
    if getattr(em.Connection.dispatch, "_earthgps", False):
        return True
    orig = em.Connection.dispatch

    def dispatch(self, msg, *a, **kw):
        if isinstance(msg, dict) and msg.get("type") == GEO_RESET:
            try:
                done = refresh_geo(self)
                if done:
                    log.info("course painter: the game dropped its tiles for the course's ground: %s sent again",
                             ", ".join(done))
            except Exception as e:
                log.warning("course painter: tiles not sent again: %s: %s", type(e).__name__, e)
            return None
        return orig(self, msg, *a, **kw)
    dispatch._earthgps = True
    em.Connection.dispatch = dispatch
    return True


def state():
    return _state
