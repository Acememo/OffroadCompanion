"""The golden test of the course's ground (gpsd/terrain.py): for every terrain version this code still makes, the dirt
track's pieces, the relief profiles, the heights (every track terrain setting) and the boulders of a fixed course are
computed and compared with the fingerprints stored in terrain_golden.json. A change to the code that would move a single
bump fails here: then it gets a new terrain version (the old one kept as it was) and its own fingerprint.

    python -m unittest tests.test_terrain                 (compare)
    EGPS_GOLDEN_WRITE=1 python -m unittest tests.test_terrain   (store a NEW version's fingerprint; never an old one's)
"""
import hashlib
import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

try:
    import numpy as np
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

if HAVE_NP:
    from gpsd import courseroads as cr
    from gpsd import relief as rf
    from gpsd import terrain

GOLDEN = os.path.join(HERE, "terrain_golden.json")
LAT0, LON0 = 31.02, -115.43
MODES = {"mild": 0.55, "on": 1.0, "extra": 1.6}     # (earthpatch.ROUGH)


def frame():
    kx = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0))
    ky = math.radians(1) * cr.R_EARTH

    def ll(x, y):
        return LAT0 + np.asarray(y, np.float64) / ky, LON0 + np.asarray(x, np.float64) / kx

    def xy(lat, lon):
        return (np.asarray(lon) - LON0) * kx, (np.asarray(lat) - LAT0) * ky
    return ll, xy


WORLD_ROADS = [((2000 + 50 * i, 22.0), (2050 + 50 * i, 22.0), 2.0, 0) for i in range(20)]       # dirt, beside
WORLD_ROADS += [((3500, -400), (3500, 400), 4.0, 1)]                                              # paved, across


def world():
    """A fixed 8 km course: open desert, a dirt road beside it, a paved road across, hills, a canyon, a dry lake,
    trees, a DANGER waypoint."""
    ll, xy = frame()
    pts = [tuple(map(float, ll(x, 40.0 * math.sin(x / 400.0) + 15.0 * math.sin(x / 97.0)))) for x in range(0, 8001, 20)]

    def road_fn(lat0, lon0, lat1, lon1, plane):
        out = []
        for (xa, ya), (xb, yb), hw, paved in WORLD_ROADS:
            (la, lo), (lb, lob) = ll(xa, ya), ll(xb, yb)
            ax, ay = plane.xy(float(la), float(lo))
            bx, by = plane.xy(float(lb), float(lob))
            out.append((ax, ay, bx, by, hw, paved))
        return out

    def elev(lat, lon):
        x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        z = 0.002 * x + 3.0 * np.sin(x / 300.0)
        z = np.where((x > 4000) & (x < 5000), z + np.maximum(0.0, np.abs(y) - 7.0) * 1.5, z)      # canyon
        z = np.where((x > 5200) & (x < 6000), z + 0.25 * y, z)                                     # hillside
        return z.tolist()

    def canopy(lat, lon):
        x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        return np.where((x > 6500) & (x < 7000) & (np.abs(y) > 6.0), 12.0, 0.0).tolist()

    def water(lat, lon):
        x, _ = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        return ((x > 7200) & (x < 7700)).astype(float).tolist()
    danger = [tuple(map(float, ll(1500.0, 40.0 * math.sin(1500 / 400.0) + 15.0 * math.sin(1500 / 97.0))))]
    return ll, xy, pts, road_fn, elev, canopy, water, danger


def _h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def fingerprint(tv):
    ll, xy, pts, road_fn, elev, canopy, water, danger = world()
    c = cr.Course(pts, 1.0, "Golden", tv)
    c.dangers = rf.danger_s(c, danger)
    pieces = {k: cr.window_pieces(c, k, road_fn, elev, canopy) for k in range(c.nwin)}
    profs = {k: rf.window_profile(c, k, pieces[k], road_fn, elev, water) for k in range(c.nwin)}
    # heights on a grid along the course (every 1.3 m along, every 1.7 m across): to the millimetre
    gx, gy = np.meshgrid(np.arange(0.0, 8000.0, 1.3), np.arange(-45.0, 45.0, 1.7))
    gla, glo = ll(gx.ravel(), gy.ravel())
    heights = {}
    for mode, scale in MODES.items():
        heights[mode] = _h(np.round(rf.relief(c, profs, gla, glo, scale) * 1000).astype(int).tolist())
    heights["auto"] = _h(np.round(rf.relief(c, profs, gla, glo, 1.0, auto=True) * 1000).astype(int).tolist())
    b = (LON0 - 0.2, LAT0 - 0.2, LON0 + 0.2, LAT0 + 0.2)
    rocks = {}
    for name, auto in (("plain", False), ("auto", True)):
        r = rf.rocks(c, profs, b, auto=auto)
        rocks[name] = _h([[round(float(v), 7) if k in ("lon", "lat") else round(float(v), 3) for v in r[k]]
                          for k in sorted(r)])
        rocks[name + "_n"] = len(r["lon"])
    out = {
        "cid": c.cid,
        "pieces": _h(pieces), "pieces_n": sum(len(v) for v in pieces.values()),
        "profiles": _h(profs),
        "heights": heights,
        "rocks": rocks,
        "seal": terrain.seal(c.cid, True, True, "auto", "auto", danger, tv),
    }
    if tv >= rf.ROCKS_OFF_ROADS_TV:     # no boulder on a road (earthpatch.rocks_off_roads), the world's roads
        ends, hws, pv = [], [], []
        for (xa, ya), (xb, yb), hw, paved in WORLD_ROADS + [((4200, -30), (4800, -30), 3.0, 1)]:
            (la, lo), (lb, lob) = ll(xa, ya), ll(xb, yb)
            ends.append([float(lo), float(la), float(lob), float(lb)])
            hws.append(hw)
            pv.append(bool(paved))
        r = rf.rocks_off_roads(rf.rocks(c, profs, b, auto=True), np.asarray(ends), np.asarray(hws), np.asarray(pv))
        out["rocks_off_roads"] = [_h([[round(float(v), 7) if k in ("lon", "lat") else round(float(v), 3)
                                      for v in r[k]] for k in sorted(r)]), len(r["lon"])]
    if tv >= cr.PAVED_EDGE_TV:          # a run leaving and joining a paved road beside the course: at its edge
        out["paved_join"] = paved_join_fingerprint(tv)
    if tv >= 2:                     # the cut banks (banks.py), on test_banks' hillside under its stand-in grading
        out["banks"] = banks_fingerprint(tv)
    if tv >= 3:                     # the ground's surfaces (surfaces.py), on test_surfaces' course
        out["surfaces"] = surfaces_fingerprint(tv)
    if tv >= 7:                     # the track's sections (variety.py), on test_variety's course
        out["variety"] = variety_fingerprint(tv)
    if tv >= 5:                     # where the drawn ruts braid (relief.ruts_at), on the track
        out["ruts"] = {mode: _h(np.round(rf.ruts_at(c, profs, gla, glo, scale) * 1000).astype(int).tolist())
                       for mode, scale in MODES.items()}
        out["ruts"]["auto"] = _h(np.round(rf.ruts_at(c, profs, gla, glo, 1.0, auto=True) * 1000).astype(int).tolist())
    return out


def paved_join_fingerprint(tv):
    ll, _xy = frame()
    pts = [tuple(map(float, ll(x, 3.0 * math.sin(x / 150.0)))) for x in range(0, 3001, 20)]

    def road_fn(lat0, lon0, lat1, lon1, plane):
        out = []
        for x0 in range(1000, 2000, 40):
            (la, lo), (lb, lob) = ll(x0, 8.0), ll(x0 + 40, 8.0)
            ax, ay = plane.xy(float(la), float(lo))
            bx, by = plane.xy(float(lb), float(lob))
            out.append((ax, ay, bx, by, 3.5, 1))
        return out

    def flat(lat, lon):
        return np.zeros(len(lat)).tolist()
    c = cr.Course(pts, 1.0, "Paved", tv)
    return _h([cr.window_pieces(c, k, road_fn, flat) for k in range(c.nwin)])


def variety_fingerprint(tv):
    sys.path.append(HERE)
    import test_variety as tv_
    from gpsd import surfaces, variety
    ll, _xy, c, profs, pcs, _g, land = tv_.world(tv)
    gx, gy = np.meshgrid(np.arange(0.0, 7200.0, 1.9), np.arange(-24.0, 24.0, 1.7))
    la, lo = ll(gx.ravel(), gy.ravel())
    out = {"profiles": _h(profs)}
    for mode, scale in MODES.items():
        c.rough = mode
        out[mode] = _h(np.round(rf.relief(c, profs, la, lo, scale) * 1000).astype(int).tolist())
    c.rough = "auto"
    out["auto"] = _h(np.round(rf.relief(c, profs, la, lo, 1.0, auto=True) * 1000).astype(int).tolist())
    cls_ = np.asarray(land(la, lo))
    idx = np.where(cls_ == 30, tv_.MATS["GRASS"], tv_.MATS["LOOSE"]).astype(np.uint8)
    idx = np.where(np.abs(gy.ravel()) <= 3.5, tv_.MATS["DIRT"], idx).astype(np.uint8)
    out["surfaces"] = _h(surfaces.course_surfaces(idx, la, lo, c, profs, tv_.MATS).astype(int).tolist())
    ps, _done = variety.split_bare(c, profs, [p for k in sorted(pcs) for p in pcs[k]])
    out["pieces"] = _h(ps)
    b = (tv_.LON0 - 0.3, tv_.LAT0 - 0.3, tv_.LON0 + 0.3, tv_.LAT0 + 0.3)
    r = rf.rocks(c, profs, b, auto=True)
    out["rocks"] = _h([[round(float(v), 7) if k in ("lon", "lat") else round(float(v), 3) for v in r[k]]
                       for k in sorted(r)])
    out["ruts"] = _h(np.round(rf.ruts_at(c, profs, la, lo, 1.0, auto=True) * 1000).astype(int).tolist())
    return out


def surfaces_fingerprint(tv):
    sys.path.append(HERE)
    import test_surfaces as ts
    from gpsd import surfaces
    _ll, _xy, c, profs, land = ts.world(tv)
    gx, gy = np.meshgrid(np.arange(0.0, 6000.0, 2.1), np.arange(-30.0, 30.0, 1.9))
    idx, la, lo = ts.earth_idx(gx.ravel(), gy.ravel(), land)
    return [_h(profs), _h(surfaces.course_surfaces(idx, la, lo, c, profs, ts.MATS).astype(int).tolist())]


def banks_fingerprint(tv):
    sys.path.append(HERE)
    import test_banks
    from gpsd import banks
    ll, _xy, c, profs, ground, grade = test_banks.world(tv)
    gx, gy = np.meshgrid(np.arange(0.0, 3000.0, 1.3), np.arange(-25.0, 25.0, 0.7))
    la, lo = ll(gx.ravel(), gy.ravel())
    nat = ground(la, lo)
    g = grade(la, lo, nat)
    return _h(np.round(banks.banks(c, profs, la, lo, nat, g, grade, ground) * 1000).astype(int).tolist())


@unittest.skipUnless(HAVE_NP, "numpy")
class TestGoldenTerrain(unittest.TestCase):
    def test_every_version_makes_the_ground_it_always_made(self):
        try:
            with open(GOLDEN, encoding="utf-8") as f:
                golden = json.load(f)
        except FileNotFoundError:
            golden = {}
        write = os.environ.get("EGPS_GOLDEN_WRITE") == "1"
        for tv in terrain.VERSIONS:
            got = fingerprint(tv)
            want = golden.get(str(tv))
            if want is None:
                if not write:
                    self.fail(f"terrain version {tv} has no stored fingerprint (EGPS_GOLDEN_WRITE=1 stores it)")
                golden[str(tv)] = got
                with open(GOLDEN, "w", encoding="utf-8") as f:
                    json.dump(golden, f, indent=1, sort_keys=True)
                continue
            self.assertEqual(got, want, f"terrain version {tv}: its ground changed. A change to the ground is a new "
                                        "terrain version (gpsd/terrain.py), the old one kept as it was")

    def test_the_same_whoever_computes_it(self):
        # window by window in another order, and by a fresh course: the same
        ll, xy, pts, road_fn, elev, canopy, water, danger = world()
        c = cr.Course(pts, 1.0, "Golden")
        fwd = [cr.window_pieces(c, k, road_fn, elev, canopy) for k in range(c.nwin)]
        back = [cr.window_pieces(c, k, road_fn, elev, canopy) for k in reversed(range(c.nwin))][::-1]
        self.assertEqual(fwd, back)
        c2 = cr.Course(pts, 1.0, "Golden")
        c2.dangers = c.dangers = rf.danger_s(c, danger)
        profs = {k: rf.window_profile(c, k, fwd[k], road_fn, elev, water) for k in range(c.nwin)}
        la, lo = ll(np.arange(0.0, 8000.0, 3.0), np.zeros(2667))
        self.assertTrue(np.array_equal(rf.relief(c, profs, la, lo, 1.0, auto=True),
                                       rf.relief(c2, dict(reversed(list(profs.items()))), la, lo, 1.0, auto=True)))

    def test_the_seal_names_the_ground(self):
        cid = "abc"
        s = terrain.seal(cid, True, True, "on", "auto")
        self.assertRegex(s, r"^T\d+-[0-9a-f]{6}$")
        self.assertEqual(s, terrain.seal(cid, True, True, "on", "auto", [(1.0, 2.0)]), "dangers only count for auto")
        self.assertNotEqual(s, terrain.seal(cid, True, True, "extra", "auto"))
        self.assertNotEqual(terrain.seal(cid, rough="auto"), terrain.seal(cid, rough="auto", dangers=[(1.0, 2.0)]))
        self.assertNotEqual(terrain.seal(cid, earth="1.5.5-beta"), terrain.seal(cid, earth="1.6.0-beta"),
                            "BeamNG.Earth's own ground changes between its versions")
        self.assertEqual(terrain.seal(cid), terrain.seal(cid, earth=None))
        self.assertNotEqual(cr.course_id([(1.0, 2.0), (1.1, 2.0)], 1.0, 1), cr.course_id([(1.0, 2.0), (1.1, 2.0)], 1.0, 2))


if __name__ == "__main__":
    unittest.main()
