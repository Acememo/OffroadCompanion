"""The course painter: pure parts, and the whole thing inside BeamNG.Earth's real map data, road tiles and grading.

Needs numpy and a BeamNG.Earth checkout: EARTH_ROOT (default ../../../ref, else skipped).
"""
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANION = os.path.dirname(HERE)
EARTH_ROOT = os.environ.get("EARTH_ROOT") or os.path.abspath(os.path.join(COMPANION, "..", "..", "ref"))
SERVER = os.path.join(EARTH_ROOT, "server")
sys.path.insert(0, SERVER)
sys.path.append(COMPANION)

try:
    import numpy as np
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

os.environ["EARTHGPS_DIR"] = tempfile.mkdtemp(prefix="egps-")

if HAVE_NP:
    from gpsd import courseroads as cr

LAT0, LON0 = 31.0, -115.5
KX = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0)) if HAVE_NP else 1
KY = math.radians(1) * cr.R_EARTH if HAVE_NP else 1


def corridor_clear():
    from gpsd import corridor
    return corridor.CLEAR_M


def route_clear():
    from gpsd import corridor
    return corridor.ROUTE_CLEAR_M


def ll(x, y):
    return LAT0 + y / KY, LON0 + x / KX


def xy(lat, lon):
    return (np.asarray(lon) - LON0) * KX, (np.asarray(lat) - LAT0) * KY


# the test world: a course 6 km due east along y = 0; the ground (east x, north y):
#   x < 2000   flat open desert
#   2000-3000  a mapped dirt road runs along the course (no track wanted)
#   3500-4800  a hillside: 30 % side slope across the course
#   5000-6000  a canyon floor 10 m wide between steep walls
def ground(lat, lon):
    x, y = xy(lat, lon)
    z = np.zeros_like(x, dtype=np.float64)
    hill = (x >= 3500) & (x < 4800)
    z = np.where(hill, 0.30 * y, z)
    canyon = x >= 5000
    z = np.where(canyon, np.where(np.abs(y) > 5, (np.abs(y) - 5) * 1.5, 0.0), z)
    # the overpass at x 2500: a long flyover on 7 m embankments (a real overpass with headroom over the mapped road)
    emb = (np.abs(x - 2500) < 15) & (np.abs(y) >= 40) & (np.abs(y) <= 200)
    z = np.where(emb, 7.0, z)
    # the overpass at x 2700 over the same road in a cutting: a 60 m bridge whose ends stand at the cutting's top
    # edge, 8 m up (the user's Carretera Tijuana - Ensenada): BeamNG.Earth's road profile through each end takes in
    # the low ground of the cutting, so the deck stays a metre or so over the road
    cut = (np.abs(x - 2700) < 15) & (np.abs(y) >= 30) & (np.abs(y) <= 200)
    z = np.where(cut, 8.0, z)
    return z


@unittest.skipUnless(HAVE_NP, "numpy (the test world)")
class TestPure(unittest.TestCase):
    def test_ruts_follow_the_track_surface(self):
        """Ruts take the track's own nodes and heights (not every 8 m in straight lines: they cut into crests and
        floated over dips)."""
        from gpsd import ruts
        xs = np.arange(0.0, 200.1, 2.0)
        zs = 3.0 * np.sin(xs / 9.0)                         # rolling ground, a crest every ~57 m
        chunk = {"m": "m_dirt_road", "w": 6.0, "n": [[float(x), 0.0, float(z)] for x, z in zip(xs, zs)]}

        class Frame:
            def enu_to_geodetic(self, e, n_, u):
                return np.asarray(n_) / 111000.0, np.asarray(e) / 111000.0, u
        out = ruts.rut_chunks([chunk], Frame(), None, "on", [np.array([[-10.0, 0.0], [210.0, 0.0]])])
        self.assertEqual(len(out), 2, "a pair")
        for r in out:
            p = np.array(r["n"])
            self.assertGreaterEqual(len(p), len(xs) - 2, "the track's node density")
            want = np.interp(p[:, 0], xs, zs)
            self.assertLess(np.abs(p[:, 2] - want).max(), 0.01, "on the track's surface")
            self.assertAlmostEqual(abs(p[5, 1]), 0.95, places=2)
            self.assertNotIn("fixed", r, "draped on the ground like the track (not at its nodes' heights)")
        deck = dict(chunk, fixed=True)
        self.assertTrue(all(r.get("fixed") for r in ruts.rut_chunks([deck], Frame(), None, "on",
                                                                    [np.array([[-10.0, 0.0], [210.0, 0.0]])])),
                        "on a deck: its heights")

    def test_rutted_sections_braid(self):
        """Terrain 5's rutted sections (relief.ruts_at): the ruts there whatever the contrast, with braids beside the
        main pair that wander, the same wherever the world's frame is."""
        from gpsd import ruts
        xs = np.arange(0.0, 600.1, 2.0)
        chunk = {"m": "m_dirt_road", "w": 6.0, "n": [[float(x), 0.0, 0.0] for x in xs]}

        def make_frame(ox):
            class Frame:
                def enu_to_geodetic(self, e, n_, u):
                    return 31.0 + np.asarray(n_) / 111000.0, -115.0 + (np.asarray(e) + ox) / 95000.0, u
            return Frame()
        line = [np.array([[-10.0, 0.0], [610.0, 0.0]])]
        rutted = lambda xy: np.where(xy[:, 0] > 200.0, 1.0, 0.0)
        out = ruts.rut_chunks([chunk], make_frame(0.0), None, "auto", line, rutted_fn=rutted)
        self.assertGreaterEqual(len(out), 4, "the main pair over the rutted run, and braids")
        ys = [np.array(r["n"])[:, 1] for r in out]
        self.assertTrue(all(np.array(r["n"])[:, 0].min() >= 195.0 for r in out), "only over the rutted section")
        braids = [y for y in ys if np.ptp(y) > 0.05]
        self.assertTrue(braids, "braids wander")
        self.assertTrue(all(np.abs(y).max() < 0.95 + 0.4 + 0.31 for y in ys), "within the track")
        self.assertEqual(ruts.rut_chunks([chunk], make_frame(0.0), None, "auto", line), [],
                         "no rutted sections, no imagery: none")
        self.assertEqual(ruts.rut_chunks([chunk], make_frame(0.0), None, "off", line, rutted_fn=rutted), [], "Off")
        # the same chunk in another frame, 300 m on: the same braids at the same places on the Earth
        moved = dict(chunk, n=[[x - 300.0, 0.0, 0.0] for x in xs])
        out2 = ruts.rut_chunks([moved], make_frame(300.0), None, "auto", [line[0] - [300.0, 0.0]],
                               rutted_fn=lambda xy: rutted(xy + [300.0, 0.0]))
        key = lambda rs: sorted((round(p[0], 1), round(p[1], 2)) for r in rs for p in r["n"])
        self.assertEqual(key(out), key([dict(r, n=[[p[0] + 300.0, p[1], p[2]] for p in r["n"]]) for r in out2]))

    def test_ruts_never_wait_on_the_ground(self):
        """The road tiles' workers ask where the rutted sections are (State.ruts_at): only from relief windows
        already planned, never planning one (that asks for elevation from the block process, which may be waiting on
        those road tiles: 1.6.4's first build hung so, "roads & buildings 0/32", the user 2026-10-29)."""
        from gpsd import earthpatch as ep, courseroads as cr, relief as rf, paintfile
        was = os.environ.get("EARTHGPS_DIR")
        os.environ["EARTHGPS_DIR"] = tempfile.mkdtemp(prefix="egps-ruts-")     # (other tests drop it: a fresh folder)
        self.addCleanup(lambda: os.environ.__setitem__("EARTHGPS_DIR", was) if was is not None
                        else os.environ.pop("EARTHGPS_DIR", None))
        st = ep._State(None, None, None, None, None, None, None)
        c = cr.Course([(31.0 + i * 0.0009, -115.4) for i in range(40)], 1.0, "Hang", rf.RUTS_TV)
        c.rough = "extra"

        class P:
            paint = c
        st.current = lambda: P

        def never(*a, **k):
            raise AssertionError("planned a window from a road tile")
        st.window = st.elev = never
        st.md = object()                # (a road worker reads the map data too)
        la = np.array([31.001, 31.01]); lo = np.array([-115.4, -115.4])
        self.assertFalse(st.ruts_at(la, lo).any(), "nothing planned yet: none, at once")
        self.assertEqual(st.rwins, {})
        # planned (by the ground's own process, or the planner ahead of the car): read from disk
        pieces = lambda k: [{"w": 6.0, "ll": [[c.lon[i], c.lat[i]] for i in range(*c.inner(k))]}]
        os.makedirs(paintfile.windows_dir(c.cid), exist_ok=True)
        for k in range(c.nwin):
            prof = rf.window_profile(c, k, pieces(k), lambda *a: [], lambda la_, lo_: [0.0] * len(la_),
                                     lambda la_, lo_: [0.0] * len(la_))
            with open(os.path.join(paintfile.windows_dir(c.cid), f"r{k:06d}.json"), "w") as f:
                json.dump(prof, f)
        st.ruts_at(la, lo)
        self.assertTrue(st.rwins, "the planned windows used")

    def test_one_planner_for_the_whole_server(self):
        """The heartbeat and the planner ahead of the car run in the server's own process only: a worker it spawns
        (which installs the painter while still named after its parent) never starts one (1.6.x on BeamNG.Earth 1.7:
        ten planners at once, roads & buildings stalled at 0, the user 2026-10-29)."""
        import multiprocessing
        from gpsd import earthpatch as ep
        self.assertTrue(ep._is_server_main(), "the server itself")
        with multiprocessing.get_context("spawn").Pool(1) as pool:
            self.assertFalse(pool.apply(ep._is_server_main), "a worker it started")

        class St:
            cache_dir = "x"
            prefetch_proc = None
        real = multiprocessing.current_process().name
        try:
            multiprocessing.current_process().name = "SpawnProcess-3"
            ep._start_prefetch(St())
        finally:
            multiprocessing.current_process().name = real
        self.assertIsNone(St.prefetch_proc, "a worker starts no planner")

    def test_kept_geotiles_sent_again_for_a_new_course(self):
        """BeamNG.Earth 1.7.2 keeps vegetation and far building geotiles in the game across rebases and teleports. For
        a new course the game drops its roads and trees and sends GEO_RESET (main.lua refreshRoads): BeamNG.Earth's
        connection then makes its vegetation and far buildings' trackers anew, so they are sent again into a game that
        has none of them (1.6.8-1.6.11 sent them again into the trees the game kept: trees in the sky, 2026-10-31).
        Every other message goes to BeamNG.Earth as before; an anchor's own tiles are left to the next world shift."""
        import sys
        import types
        from gpsd import earthpatch as ep

        class Tr:
            def __init__(self, *a, **kw):
                self.a, self.kw, self.closed = a, kw, False
                self.send_m, self.drop_m, self.geo = 100.0, 150.0, kw.get("geo", False)

            def close(self):
                self.closed = True

        class Conn:
            def __init__(self, geo):
                self.road_geo, self.far_geo = geo, geo
                self.roads, self.veg = Tr(), Tr(geo=geo)
                self.far, self.got = 0, []

            def make_far_trackers(self, geo):
                self.far += 1

            def dispatch(self, msg):
                self.got.append(msg["type"])
                return "theirs"
        earthd = types.ModuleType("earthd")
        earthd.Connection = Conn
        veg = types.ModuleType("vegetation")
        veg.Tracker = Tr
        was = {k: sys.modules.get(k) for k in ("earthd", "vegetation")}
        sys.modules["earthd"], sys.modules["vegetation"] = earthd, veg
        try:
            geo, plain = Conn(True), Conn(False)
            r0, v0 = geo.roads, geo.veg
            self.assertEqual(ep.refresh_geo(geo), ["vegetation", "far buildings"])
            self.assertTrue(v0.closed and geo.veg is not v0 and geo.veg.geo and geo.far == 1)
            self.assertEqual((geo.veg.a, geo.veg.kw), ((100.0, 150.0), {"geo": True}), "the same reach")
            self.assertIs(geo.roads, r0, "the roads: BeamNG.Earth's own roads_reset, just before")
            p0 = plain.veg
            self.assertEqual(ep.refresh_geo(plain), [], "an anchor's tiles: left to the next world shift")
            self.assertIs(plain.veg, p0)
            # the message
            self.assertTrue(ep._install_geo_reset())
            self.assertTrue(ep._install_geo_reset(), "once")
            c = Conn(True)
            v1 = c.veg
            self.assertEqual(c.dispatch({"type": "hello"}), "theirs")
            self.assertEqual(c.got, ["hello"], "BeamNG.Earth's messages as before")
            self.assertIsNone(c.dispatch({"type": ep.GEO_RESET}))
            self.assertEqual(c.got, ["hello"], "ours answered here")
            self.assertTrue(v1.closed and c.veg is not v1 and c.far == 1)
            self.assertEqual(ep.GEO_RESET, "offroad_geo_reset", "main.lua's M.GEO_RESET")
        finally:
            for k, v in was.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_rut_contrast_and_runs(self):
        from gpsd import ruts
        de = ruts.delta_e(np.array([[214, 188, 150], [166, 143, 113], [92, 104, 60], [60, 60, 62]], float))
        self.assertLess(de[0], ruts.DE_MAX, "light desert sand: the track blends in")
        self.assertLess(de[1], 1.0)
        self.assertGreater(de[2], ruts.DE_MAX, "green scrub: the track shows")
        self.assertGreater(de[3], ruts.DE_MAX, "dark rock")
        s = np.arange(0.0, 400.0, 8.0)
        low = (s < 100) | ((s >= 116) & (s < 200)) | ((s >= 300) & (s < 320))
        self.assertEqual(ruts.runs(low, s), [(0, 24)], "a 16 m gap closed, a 20 m stretch dropped")
        xy = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
        self.assertTrue(np.allclose(ruts.offset(xy, 1.0)[:, 1], 1.0), "offset to the left")

    def test_walls_on_the_followed_road_cut(self):
        """A divided highway along x (carriageways at y = +-8, 12 m wide), the GPS route on the north one, near its
        edge: a crossing road's wall reaching across it is cut over the whole carriageway (not only near the line),
        the highway's own walls beside it stay."""
        from gpsd import corridor
        xs = np.arange(-200.0, 201.0, 20.0)
        road = (np.concatenate([np.stack([xs[:-1], np.full(len(xs) - 1, y)], 1) for y in (8.0, -8.0)]),
                np.concatenate([np.stack([xs[1:], np.full(len(xs) - 1, y)], 1) for y in (8.0, -8.0)]),
                np.full(2 * (len(xs) - 1), 6.0))
        route = [np.stack([xs, np.full(len(xs), 12.0)], 1)]
        m = corridor.followed(road, route)
        self.assertTrue(m[:len(xs) - 1].all() and not m[len(xs) - 1:].any(), "the north carriageway followed")
        ys = np.arange(-40.0, 40.1, 2.0)
        across = {"base": np.stack([np.full(len(ys), 50.0), ys], 1), "top": ys * 0 + 3, "foot": ys * 0,
                  "toward": np.tile([1.0, 0.0], (len(ys), 1))}
        own = {"base": np.stack([xs, np.full(len(xs), 8.0 + 6.0 + 1.0 + 2.8)], 1), "top": xs * 0 + 3, "foot": xs * 0,
               "toward": np.tile([0.0, -1.0], (len(xs), 1))}
        out = corridor.cut_walls([across, own], route, clear_m=corridor.ROUTE_CLEAR_M + corridor.WALL_PAD_M,
                                 on_roads=tuple(v[m] for v in road))
        left = np.concatenate([w["base"] for w in out if abs(w["base"][0, 0] - 50.0) < 1e-6 and w["base"][-1, 0] == 50.0])
        self.assertFalse((np.abs(left[:, 1] - 8) <= 7).any(), f"nothing left on the carriageway: {sorted(left[:, 1])}")
        self.assertTrue((left[:, 1] > 25).any() and (left[:, 1] < -10).any(), "the wall stays off it")
        kept = [w for w in out if np.allclose(w["base"][:, 1], 17.8)]
        self.assertEqual(sum(len(w["base"]) for w in kept), len(xs), "the highway's own wall stays whole")

    def test_paint_mask(self):
        cov = [bool(v) for v in [0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1]]
        m = cr.paint_mask(cov)
        self.assertTrue(m[7] and m[8], "a 2-sample covered gap is painted through")
        self.assertTrue(m[15], "the run reaches one sample onto the road")
        self.assertFalse(m[17])
        self.assertFalse(any(m[21:24]), "a 3-sample painted run is dropped")

    def test_clearance_and_widths(self):
        off = cr.side_offsets()
        n = 30
        zc = [0.0] * n
        flat = [[0.0] * len(off) for _ in range(n)]
        room_flat = cr.clearance(zc, flat, flat)
        self.assertAlmostEqual(room_flat[0], 2 * (cr.SIDE_M + 1), places=6)
        up = [[0.3 * d for d in off] for _ in range(n)]
        down = [[-0.3 * d for d in off] for _ in range(n)]
        room_hill = cr.clearance(zc, up, down)
        self.assertLessEqual(room_hill[0], 10)
        trees = [[10.0 if d >= 6 else 0.0 for d in off] for _ in range(n)]
        room_trees = cr.clearance(zc, flat, flat, trees, trees)
        self.assertAlmostEqual(room_trees[0], 2 * 5.0, places=6)
        self.assertEqual(cr.widths(room_flat)[0], cr.WIDTH_MAX)
        self.assertLessEqual(cr.widths(room_hill)[0], 4.0)
        self.assertEqual(cr.widths(room_flat, 0.75)[0], 7.0)            # 9 x 0.75 = 6.75 -> 7.0 (0.5 steps)

    def test_pieces_share_samples_at_width_steps(self):
        lat = [i * 0.0001 for i in range(11)]
        lon = [0.0] * 11
        paint = [bool(v) for v in [0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0]]
        w = [0, 4, 4, 4, 5, 5, 5, 5, 0, 0, 0]
        ps = cr.pieces("abc", 0, lat, lon, paint, w, 0, 10, z=[float(i) for i in range(11)])
        self.assertEqual([len(p["ll"]) for p in ps], [4, 4])
        self.assertEqual(ps[0]["ll"][-1], ps[1]["ll"][0])
        self.assertEqual([p["w"] for p in ps], [4.0, 5.0])
        self.assertEqual(ps[1]["z"], [4.0, 5.0, 6.0, 7.0])

    def test_track_bends_onto_the_dirt_road_it_meets(self):
        # the course along y = 0; a dirt road 20 m north of it between x 1000 and 2000: the course takes the road
        # there, the track before it bends onto the road's middle (and leaves it the same way after), no stub beside it
        pts = [ll(x, 0.0) for x in range(0, 3001, 25)]
        c = cr.Course(pts)

        def segs(lat0, lon0, lat1, lon1, plane):
            out = []
            for x0 in range(1000, 2000, 50):
                ax, ay = plane.xy(*ll(x0, 20.0))
                bx, by = plane.xy(*ll(x0 + 50, 20.0))
                out.append((ax, ay, bx, by, 2.0, 0))
            return out

        def flat(lat, lon):
            return np.zeros(len(lat))
        got = sum((cr.window_pieces(c, k, segs, flat) for k in range(c.nwin)), [])
        pts_ = [(q, p) for p in got for q in p["ll"]]
        X, Y = xy([q[1] for q, _ in pts_], [q[0] for q, _ in pts_])
        on_road = (X > 1000) & (X < 2000)
        self.assertTrue(on_road.any(), "the track reaches onto the road")
        self.assertLess(np.abs(Y[on_road] - 20.0).min(), 0.05, "and ends on the road's middle")
        self.assertFalse(((X > 1100) & (X < 1900)).any(), "no second track beside the road")
        before = sorted((x_, y_) for x_, y_ in zip(X, Y) if 900 <= x_ <= 1100)
        after = sorted((x_, y_) for x_, y_ in zip(X, Y) if 1900 <= x_ <= 2100)
        for run in (before, after):
            for (x0, y0), (x1, y1) in zip(run, run[1:]):
                if x1 > x0:
                    self.assertLess(abs(y1 - y0) / (x1 - x0), 1.0, f"a smooth bend, not a jog: {run}")
        self.assertGreater(after[0][1], 19.9, "the track after the road starts on it")
        self.assertLess(after[-1][1], 0.1)
        # the relief profile knows where the bent ends lie (for the signs beside them and the whoops on them)
        from gpsd import relief
        k = c.windows_near(*ll(950, 0), 10)[0]
        prof = relief.window_profile(c, k, cr.window_pieces(c, k, segs, flat), segs, flat)
        a = prof["a"]
        i = int(round(1000 / cr.STEP_M)) - a
        self.assertGreater(prof["ctr"][i], 5.0, f"ctr follows the bend: {prof['ctr'][i - 6:i + 4]}")

    def test_windows_agree_with_one_long_window(self):
        pts = [ll(x, 30 * math.sin(x / 300)) for x in range(0, 3001, 25)]
        c = cr.Course(pts)

        def segs(lat0, lon0, lat1, lon1, plane):
            # a road along the course between x 800 and 1500
            out = []
            xs = list(range(800, 1500, 20))
            for x0, x1 in zip(xs, xs[1:]):
                a, b = ll(x0, 30 * math.sin(x0 / 300)), ll(x1, 30 * math.sin(x1 / 300))
                ax, ay = plane.xy(*a)
                bx, by = plane.xy(*b)
                out.append((ax, ay, bx, by, 2.5))
            return out
        got = [cr.window_pieces(c, k, segs, ground) for k in range(c.nwin)]
        for k in range(c.nwin - 1):
            if got[k] and got[k + 1] and got[k][-1]["ll"][-1] == got[k + 1][0]["ll"][0]:
                self.assertEqual(got[k][-1]["w"], got[k + 1][0]["w"])
        old = cr.WINDOW
        try:
            cr.WINDOW = 10 ** 6
            whole = cr.Course(pts)
            one = cr.window_pieces(whole, 0, segs, ground)
        finally:
            cr.WINDOW = old
        a = {tuple(q) for p in sum(got, []) for q in p["ll"]}
        b = {tuple(q) for p in one for q in p["ll"]}
        self.assertEqual(a, b)
        x, _ = xy([q[1] for q in a], [q[0] for q in a])
        self.assertFalse(((x > 830) & (x < 1470)).any(), "nothing painted on the road")


@unittest.skipUnless(HAVE_NP and os.path.isfile(os.path.join(SERVER, "earthd.py")), "BeamNG.Earth checkout")
class TestInsideEarth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import geodesy
        import mapcells
        import mapdata
        import mapgeom
        cls.geodesy, cls.mapcells, cls.mapdata, cls.mapgeom = geodesy, mapcells, mapdata, mapgeom

        # the mapped roads: a dirt road along the course (x 2000-3000) and a road across it at x 4200
        def road_arrays(key):
            lon0, lat0, lon1, lat1 = key.bounds()
            roads = []
            xs = np.arange(2000.0, 3001.0, 25.0)
            la, lo = ll(xs, np.zeros_like(xs))
            roads.append(("0aa1", np.stack([lo, la], 1), "unclassified", "dirt"))
            ys = np.arange(-600.0, 601.0, 50.0)
            la, lo = ll(np.full_like(ys, 4200.0), ys)
            roads.append(("0bb2", np.stack([lo, la], 1), "residential", "paved"))
            # a paved road over the creek the course runs along, on a 40 m bridge (the user's Ensenada crossing)
            ys = np.arange(-200.0, 201.0, 10.0)
            la, lo = ll(np.full_like(ys, 1500.0), ys)
            roads.append(("0cc3", np.stack([lo, la], 1), "residential", "paved", (0.45, 0.55)))
            # an overpass over the mapped dirt road the course follows: an underpass for the course, kept
            la, lo = ll(np.full_like(ys, 2500.0), ys)
            roads.append(("0dd4", np.stack([lo, la], 1), "residential", "paved", (0.35, 0.65)))
            # an overpass over the same road whose ends lie at the road's height: a wall across it (the user's
            # Libramiento de Ensenada): made a crossing at grade
            la, lo = ll(np.full_like(ys, 2200.0), ys)
            roads.append(("0ee5", np.stack([lo, la], 1), "residential", "paved", (0.45, 0.55)))
            la, lo = ll(np.full_like(ys, 2700.0), ys)
            roads.append(("0ff6", np.stack([lo, la], 1), "motorway", "paved", (0.425, 0.575)))
            # the toll road through the plaza at x 3300 (the course follows it there)
            xs = np.arange(3150.0, 3451.0, 25.0)
            la, lo = ll(xs, np.zeros_like(xs))
            roads.append(("0ff7", np.stack([lo, la], 1), "trunk", "paved"))
            # a motorway on a 40 m bridge over the course where it runs off the roads: over flat desert (a wash the
            # 30 m elevation filled in: the user's Libramiento de Ensenada) and over the canyon (a real gap)
            ys = np.arange(-200.0, 201.0, 10.0)
            la, lo = ll(np.full_like(ys, 1800.0), ys)
            roads.append(("0ff8", np.stack([lo, la], 1), "motorway", "paved", (0.45, 0.55)))
            la, lo = ll(np.full_like(ys, 5500.0), ys)
            roads.append(("0ff9", np.stack([lo, la], 1), "motorway", "paved", (0.45, 0.55)))
            keep = [r for r in roads if r[1][:, 0].max() >= lon0 and r[1][:, 0].min() <= lon1
                    and r[1][:, 1].max() >= lat0 and r[1][:, 1].min() <= lat1]
            f = mapgeom.build("roads", np.array([r[0] for r in keep]) if keep else np.array([], "<U4"),
                              [(mapgeom.LINE, [[r[1]]]) for r in keep])
            n = len(keep)
            f.attrs = {"subtype": np.array(["road"] * n, "<U8"), "class": np.array([r[2] for r in keep], "<U16"),
                       "subclass": np.array([""] * n, "<U8"), "name": np.array(["Camino"] * n, "<U16"),
                       "src_dataset": np.array(["OpenStreetMap"] * n, "<U16"),
                       "src_record": np.array([""] * n, "<U8")}
            br = [(j, r[4]) for j, r in enumerate(keep) if len(r) > 4]
            f.rules = {"surface": mapgeom.RuleTable(np.arange(n, dtype=np.int32), np.array([r[3] for r in keep]),
                                                    np.zeros(n, np.float32), np.ones(n, np.float32)),
                       "level": mapgeom.RuleTable(np.array([j for j, _ in br], np.int32),
                                                  np.array([1.0 for _ in br], np.float32),
                                                  np.array([a for _, (a, b) in br], np.float32),
                                                  np.array([b for _, (a, b) in br], np.float32)),
                       "width": mapgeom.RuleTable(np.zeros(0, np.int32), np.zeros(0, np.float32),
                                                  np.zeros(0, np.float32), np.zeros(0, np.float32))}
            f.own = np.ones(n, bool)
            f.clipped = np.zeros(n, bool)
            a = f.to_arrays("")
            a["provenance"] = np.array(json.dumps({"id": "overture", "datasets": []}))
            return a

        # footprints: id, centre x, y, half sizes along x, y, height. A house on the course (b1) and one 40 m off it
        # (b2); a toll plaza on the course at x 3300 (BeamNG.Earth draws it as West Coast USA's toll booths): its flat
        # footprint (t0), two islands 20 x 2 m, 0.2 m tall (t1, t2); a low square slab on the course (s1, no island)
        BLDS = [("b1", 800.0, 2.0, 5, 5, 6.0), ("b2", 800.0, 40.0, 5, 5, 6.0),
                ("s1", 3360.0, 0.0, 5, 5, 0.5), ("t0", 3300.0, 0.0, 20, 15, 0.05),
                ("t1", 3300.0, -3.0, 10, 1, 0.2), ("t2", 3300.0, 3.0, 10, 1, 0.2)]
        # building parts: the booths on the islands (p1, p2: 3 m tall, 3 x 2 m), and a kiosk on the course on no
        # island (k1)
        # (the booths are parts of the plaza's footprint, as the Golden Gate's are in OpenStreetMap)
        PARTS = [("k1", 3420.0, 0.0, 1.5, 1.0, 3.0, "s9"), ("p1", 3300.0, -3.0, 1.5, 1.0, 3.0, "t0"),
                 ("p2", 3300.0, 3.0, 1.5, 1.0, 3.0, "t0")]

        def feature_arrays(key, layer, rows):
            lon0, lat0, lon1, lat1 = key.bounds()
            keep, geoms, hs, bids = [], [], [], []
            for row in rows:
                bid, cx, cy, hx, hy, h = row[:6]
                ring = np.array([ll(cx - hx, cy - hy), ll(cx + hx, cy - hy), ll(cx + hx, cy + hy), ll(cx - hx, cy + hy),
                                 ll(cx - hx, cy - hy)])[:, ::-1]
                if ring[:, 0].max() >= lon0 and ring[:, 0].min() <= lon1 and ring[:, 1].max() >= lat0 and \
                        ring[:, 1].min() <= lat1:
                    keep.append(bid)
                    geoms.append((mapgeom.POLYGON, [[ring]]))
                    hs.append(h)
                    bids.append(row[6] if len(row) > 6 else "")
            f = mapgeom.build(layer, np.array(keep) if keep else np.array([], "<U4"), geoms)
            n = len(keep)
            f.attrs = {"class": np.array(["house"] * n, "<U8"), "height": np.array(hs, np.float32)}
            if layer == "building_parts":
                f.attrs["building_id"] = np.array(bids, "<U4")
            f.rules = {}
            f.own, f.clipped = np.ones(n, bool), np.zeros(n, bool)
            a = f.to_arrays("")
            a["provenance"] = np.array(json.dumps({"id": "overture", "datasets": []}))
            return a

        def building_arrays(key):
            return feature_arrays(key, "buildings", BLDS)

        def water_arrays(key):
            """A dry wash across the course at x 600 (a stream mapped intermittent): surfaces.py's ground."""
            lon0, lat0, lon1, lat1 = key.bounds()
            ys = np.arange(-300.0, 301.0, 20.0)
            la, lo = ll(np.full_like(ys, 600.0), ys)
            line = np.stack([lo, la], 1)
            keep = line[:, 0].max() >= lon0 and line[:, 0].min() <= lon1 and line[:, 1].max() >= lat0 and \
                line[:, 1].min() <= lat1
            f = mapgeom.build("water", np.array(["w1"] if keep else [], "<U4"),
                              [(mapgeom.LINE, [[line]])] if keep else [])
            n = 1 if keep else 0
            f.attrs = {"subtype": np.array(["stream"] * n, "<U8"), "class": np.array(["stream"] * n, "<U8"),
                       "is_intermittent": np.ones(n, bool), "is_salt": np.zeros(n, bool)}
            f.rules = {}
            f.own, f.clipped = np.ones(n, bool), np.zeros(n, bool)
            a = f.to_arrays("")
            a["provenance"] = np.array(json.dumps({"id": "overture", "datasets": []}))
            return a

        def layer_arrays(self, key, layer, kind="demand"):
            key = mapdata._key(key)
            if layer == "roads":
                return road_arrays(key), True
            if layer == "water":
                return water_arrays(key), True
            if layer == "buildings":
                return building_arrays(key), True
            if layer == "building_parts":
                return feature_arrays(key, "building_parts", PARTS), True
            if layer in mapdata.VECTOR_LAYERS:          # (an empty layer, as BeamNG.Earth's where there is none)
                return feature_arrays(key, layer, []), True
            return {"missing": np.array(True), "provenance": np.array("{}")}, True
        mapdata.MapData.layer_arrays = layer_arrays

        from gpsd import earthpatch, paintfile
        earthpatch.install()

        class FakeDem:
            def sample(self, lat, lon, zoom, progress=None):
                return ground(np.asarray(lat), np.asarray(lon))
        earthpatch.state().dems.insert(0, FakeDem())
        cls.paintfile, cls.earthpatch = paintfile, earthpatch
        cls.md = mapdata.MapData(tempfile.mkdtemp(prefix="egps-md-"), fetcher=object())
        pts = [list(ll(x, 0.0)) for x in range(0, 6001, 50)]
        paintfile.write_course(pts, "Test 1000", 1.0, True, "test:1")
        earthpatch.state().checked = -1e9

    def roads(self, lat, lon):
        return self.md.cell(self.mapcells.cell_of(lat, lon), layers=("roads",)).layers["roads"]

    def painted(self):
        """{x of every painted sample: width} over all the cells the course crosses."""
        keys = self.mapcells.cells_for_bbox(*ll(-100, -100), *ll(6100, 100))
        seen = {}
        for key in keys:
            f = self.md.cell(key, layers=("roads",)).layers["roads"]
            if f is None:
                continue
            w = f.rules["width"]
            for i in range(len(f)):
                fid = str(f.ids[i])
                if not fid.startswith(cr.ID_PREFIX) or fid in seen:
                    continue
                self.assertEqual(str(f.attrs["class"][i]), "track")
                ring = f.parts(i)[0][0]
                x, _ = xy(ring[:, 1], ring[:, 0])
                seen[fid] = (x, float(w.value[w.major(i)]))
        return seen

    def test_cells_keep_their_roads_and_get_the_track(self):
        f = self.roads(*ll(2500, 0))
        ids = [str(i) for i in f.ids]
        self.assertIn("0aa1", ids)
        self.assertTrue(all(ids[k] <= ids[k + 1] for k in range(len(ids) - 1)), "ids stay sorted")
        self.assertEqual(len(f.en), len(f.lonlat))

    def test_cells_keep_earths_extras(self):
        """BeamNG.Earth 1.7 hangs per-cell extras on a decoded roads layer (OpenStreetMap's railway nodes for the level
        crossings, the grade separations' hook): the layer made with the track keeps them, the latter for its own
        rows."""
        base = self.earthpatch.state().orig_cell(self.md, self.mapcells.cell_of(*ll(2500, 0)), ("roads",)).layers["roads"]
        f = self.roads(*ll(2500, 0))
        self.assertIsNot(f, base, "the track was added in this cell")
        if "_bnge_gradesep" in base.__dict__:
            hook = f.__dict__.get("_bnge_gradesep")
            self.assertTrue(callable(hook) and hook is not base.__dict__["_bnge_gradesep"])
            self.assertIsInstance(hook(f), dict)
        nodes = [(-116.6, 31.8, {"railway": "level_crossing", "crossing:barrier": "full"})]
        base.__dict__["_rail_nodes"], base.__dict__["_rails_built"] = nodes, "v9"
        base.__dict__["_lanes_built"] = "L3"            # (1.7.1: OpenStreetMap's lane tags)
        try:
            f2 = self.roads(*ll(2500, 0))
            self.assertEqual(f2.__dict__.get("_rail_nodes"), nodes, "the railway nodes go along")
            self.assertEqual(f2.__dict__.get("_rails_built"), "v9")
            self.assertEqual(f2.__dict__.get("_lanes_built"), "L3", "the lane tags' mark too")
        finally:
            base.__dict__.pop("_rail_nodes", None)
            base.__dict__.pop("_rails_built", None)
            base.__dict__.pop("_lanes_built", None)

    def test_track_only_where_no_road_and_width_from_terrain(self):
        seen = self.painted()
        self.assertTrue(seen, "something painted")
        xs = np.concatenate([x for x, _ in seen.values()])
        self.assertFalse(((xs > 2020) & (xs < 2980)).any(), "no track on top of the mapped road")
        self.assertTrue(((xs > 100) & (xs < 1900)).any() and ((xs > 3100) & (xs < 4100)).any() and (xs > 4300).any(),
                        "track where the course leaves the roads, and across the crossing road")

        def width_at(x0):
            ws = [w for x, w in seen.values() if x.min() <= x0 <= x.max()]
            return min(ws) if ws else None
        self.assertEqual(width_at(1000), cr.WIDTH_MAX, "open desert: wide")
        self.assertLessEqual(width_at(4000), 4.0, "hillside: narrow")
        self.assertTrue(4.0 <= width_at(5600) <= 6.5, f"canyon floor: medium ({width_at(5600)})")

    def drawn_dirt(self, frame, tx, ty, cells, chunks):
        """The dirt track as this BeamNG.Earth draws it in a road tile: its DecalRoad pieces (up to 1.5.5), or (1.6:
        the carriageways painted into the ground's photo, roads.ROADS_IN_GROUND) the dirt the photo gets painted with,
        as (width m,) per painted segment."""
        import roads as roadsmod
        if not getattr(roadsmod, "ROADS_IN_GROUND", False):
            return [c["w"] for c in chunks if c["m"] == "m_dirt_road"]
        import surface
        x0, y0, x1, y1 = roadsmod.tile_bbox(tx, ty)
        px = 256
        got = surface._road_segments(frame, x0, y0, x1 - x0, px, px, cells)
        if got is None:
            return []
        _, hws, kind = got
        dirt = list(surface.PHOTO_ROAD_RGBA).index("dirt")
        edge = getattr(surface, "PHOTO_ROAD_EDGE_M", 0.0)       # (1.7.1: painted this much past each edge)
        return [round(float(h) * 2 * (x1 - x0) / px - 2 * edge, 2) for h, k in zip(hws, kind) if k == dirt]

    def drawn_paved(self, frame, tx, ty, cells, chunks):
        import roads as roadsmod
        if not getattr(roadsmod, "ROADS_IN_GROUND", False):
            return [c for c in chunks if c["m"] == "road_asphalt_2lane"]
        import surface
        x0, y0, x1, y1 = roadsmod.tile_bbox(tx, ty)
        got = surface._road_segments(frame, x0, y0, x1 - x0, 256, 256, cells)
        paved = list(surface.PHOTO_ROAD_RGBA).index("paved")
        return [] if got is None else [k for k in got[2] if k == paved]

    def test_road_tiles_and_grading(self):
        import grading
        import roads as roadsmod
        frame = self.geodesy.EnuFrame(*ll(3800, 0), 0.0)

        def elev(lat, lon):
            return ground(lat, lon)
        # the tile with the hillside's track in it
        tx, ty = int(math.floor(200 / roadsmod.TILE)), int(math.floor(0 / roadsmod.TILE))
        cells = [self.md.cell(k, layers=("roads",)).layers["roads"] for k in roadsmod.cells_of_tile(frame, tx, ty)]
        chunks = roadsmod.build_tile(frame, tx, ty, cells, elev)
        dirt = self.drawn_dirt(frame, tx, ty, cells, chunks)
        self.assertTrue(dirt, "the dirt track drawn in the tile")
        self.assertTrue(all(w <= 4.0 for w in dirt), dirt)
        # the ground graded flat across the track on the 30 % hillside: a shelf
        g = grading.Grader(frame, self.md, elev)
        la, lo = ll(np.full(5, 4000.0), np.array([-1.0, -0.5, 0.0, 0.5, 1.0]))
        z = g.apply(la, lo, elev(la, lo))
        self.assertLess(np.ptp(z), 0.1, f"flat across the core: {z}")
        self.assertGreater(np.ptp(elev(la, lo)), 0.5)

    def test_creek_bridge_on_the_course_made_a_ground_road(self):
        import roads as roadsmod
        f = self.roads(*ll(1500, 0))
        i = f.index("0cc3")
        self.assertGreaterEqual(i, 0)
        self.assertEqual([k for _, _, k in roadsmod.level_ranges(f, i)], [], "no bridge range left")
        self.assertEqual(len(roadsmod.ground_parts(f, i)), 1, "the whole road on the ground")
        self.assertIsNone(roadsmod.bridge_specs(f)[i])
        # an overpass over the mapped road the course follows, high enough on its embankments: stays a bridge
        g = self.roads(*ll(2500, 0))
        j = g.index("0dd4")
        self.assertEqual([k for _, _, k in roadsmod.level_ranges(g, j)], ["bridge"])
        # one whose deck cannot clear that road (its ends at the road's height): a crossing at grade
        h = self.roads(*ll(2200, 0))
        self.assertEqual([k for _, _, k in roadsmod.level_ranges(h, h.index("0ee5"))], [], "the low overpass flattened")
        # one over the road in a cutting: the hills are high, but its ends are graded down to the road (and a motorway)
        c = self.roads(*ll(2700, 0))
        self.assertEqual([k for _, _, k in roadsmod.level_ranges(c, c.index("0ff6"))], [],
                         "the overpass in a cutting flattened")
        # the road tile at the crossing: no bridge deck, the dirt track crossing the road
        frame = self.geodesy.EnuFrame(*ll(1500, 0), 0.0)
        tx, ty = int(math.floor(0 / roadsmod.TILE)), int(math.floor(0 / roadsmod.TILE))
        cells = [self.md.cell(k, layers=("roads",)).layers["roads"] for k in roadsmod.cells_of_tile(frame, tx, ty)]
        chunks = roadsmod.build_tile(frame, tx, ty, cells, lambda la, lo: ground(la, lo))
        self.assertFalse([c for c in chunks if c.get("deck") or c.get("ctx")], "no deck")
        self.assertTrue(self.drawn_dirt(frame, tx, ty, cells, chunks), "the track")
        self.assertTrue(self.drawn_paved(frame, tx, ty, cells, chunks), "the road, at grade")

    def test_motorway_bridge_over_the_course_judged_by_its_headroom(self):
        """A motorway's bridge the course passes under off the roads: kept where the deck can stand high over the
        course (a canyon), a crossing at grade where it cannot (a wash the elevation data filled in: the deck stood a
        metre over the course, a wall across it; the user's Libramiento de Ensenada, 2026-10-31)."""
        import roads as roadsmod
        f = self.roads(*ll(1800, 0))
        self.assertEqual([k for _, _, k in roadsmod.level_ranges(f, f.index("0ff8"))], [], "no headroom: at grade")
        g = self.roads(*ll(5500, 0))
        self.assertEqual([k for _, _, k in roadsmod.level_ranges(g, g.index("0ff9"))], ["bridge"],
                         "over the canyon: the course passes under")

    def test_toll_plaza_kept(self):
        """A toll plaza on the course stays for BeamNG.Earth to draw its booths (its islands, their booths, its flat
        footprint); a low slab and a kiosk on the course that are not a plaza's are still left out."""
        key = self.mapcells.cell_of(*ll(3300, 0))
        cd = self.md.cell(key, layers=("buildings", "building_parts"))
        self.assertEqual(sorted(str(i) for i in cd.layers["buildings"].ids), ["t0", "t1", "t2"])
        self.assertEqual(sorted(str(i) for i in cd.layers["building_parts"].ids), ["p1", "p2"])
        from gpsd import corridor
        self.assertTrue(corridor.toll_like(cd.layers["buildings"], 1))
        # and BeamNG.Earth draws its toll booths there (its own detection, on what the cells now hold)
        import buildings as bm
        import roads as roadsmod
        frame = self.geodesy.EnuFrame(*ll(3200, -100), 0.0)
        x0, y0, x1, y1 = roadsmod.tile_bbox(0, 0)
        cds = [self.md.cell(k, layers=("buildings", "building_parts", "roads"))
               for k in roadsmod.cells_of_tile(frame, 0, 0, margin=0.0)]
        items = bm.tile_buildings(frame, x0, y0, x1, y1, [c.layers.get("buildings") for c in cds],
                                  lambda la, lo: ground(la, lo), part_layers=[c.layers.get("building_parts") for c in cds],
                                  roads_xy=bm.road_lines(frame, [c.layers.get("roads") for c in cds], x0, y0))
        if hasattr(bm, "toll_booth_rows"):              # (BeamNG.Earth 1.5.5 on)
            self.assertEqual(len(bm.toll_booth_rows(items, x0, y0)), 2, "both toll booths drawn")

    def test_buildings_on_the_course_left_out(self):
        f = self.md.cell(self.mapcells.cell_of(*ll(800, 0)), layers=("buildings",)).layers["buildings"]
        self.assertEqual([str(i) for i in f.ids], ["b2"])
        self.assertEqual(len(f.parts(0)[0][0]), 5)
        # clearing off: both
        pts = [list(ll(x, 0.0)) for x in range(0, 6001, 50)]
        self.paintfile.write_json(self.paintfile.course_path(), {"enabled": True, "paint": True, "clear": False,
                                                                   "name": "Test 1000", "scale": 1.0, "points": pts})
        self.earthpatch.state().checked = -1e9
        os.utime(self.paintfile.course_path())
        f = self.md.cell(self.mapcells.cell_of(*ll(800, 0)), layers=("buildings",)).layers["buildings"]
        self.assertEqual(sorted(str(i) for i in f.ids), ["b1", "b2"])
        self.paintfile.write_course(pts, "Test 1000", 1.0, True, "test:1")
        self.earthpatch.state().checked = -1e9
        os.utime(self.paintfile.course_path())

    def test_walls_cut_along_the_course(self):
        from gpsd import corridor
        wall = {"base": np.array([[x, 3.0] for x in range(-50, 51, 5)], float), "top": np.ones(21),
                "foot": np.zeros(21), "toward": np.tile([0.0, -1.0], (21, 1))}
        course = [np.array([[0.0, -100.0], [0.0, 100.0]])]          # crossing the wall's road at x = 0
        cut = corridor.cut_walls([wall], course)
        self.assertEqual(len(cut), 2)
        self.assertTrue(all(np.abs(w["base"][:, 0]).min() > corridor.CLEAR_M for w in cut))
        self.assertEqual(len(cut[0]["top"]), len(cut[0]["base"]))

    def test_walls_alongside_stay(self):
        from gpsd import corridor
        wall = {"base": np.array([[5.0, y] for y in range(-50, 51, 5)], float), "top": np.ones(21),
                "foot": np.zeros(21), "toward": np.tile([-1.0, 0.0], (21, 1))}
        course = [np.array([[0.0, -100.0], [0.0, 100.0]])]          # along the wall, 5 m from it
        self.assertEqual(len(corridor.cut_walls([wall], course)), 1)
        self.assertEqual(len(corridor.cut_walls([wall], course)[0]["base"]), 21)

    def test_plan_with_a_route(self):
        from gpsd import earthpatch
        pts = [list(ll(x, 0.0)) for x in range(0, 2001, 50)]
        route = [list(ll(x, 300.0)) for x in range(0, 2001, 50)]
        plan = earthpatch.parse_plan({"enabled": True, "lines": [
            {"kind": "course", "points": pts, "name": "C", "paint": True, "clear": True},
            {"kind": "route", "points": route, "name": "R", "clear": True, "paint": True}]})
        self.assertEqual([c.kind for c in plan.lines], ["course", "route"])
        self.assertIs(plan.paint, plan.lines[0], "only the course gets a dirt track")
        self.assertEqual([c.clear_m for c in plan.clearing], [corridor_clear(), route_clear()])
        legacy = earthpatch.parse_plan({"enabled": True, "points": pts, "name": "Old", "paint": False})
        self.assertIsNone(legacy.paint)
        self.assertEqual(len(legacy.clearing), 1)
        self.assertIsNone(earthpatch.parse_plan({"enabled": False, "lines": []}))

    def test_missing_data_is_never_kept_as_terrain(self):
        """A fetch that failed (or was put off) is not "no trees" / "no lake", and heights from the fallback DEM are not
        kept: the course's ground is planned once on complete data, the same every time."""
        from gpsd import earthpatch as ep
        st = self.earthpatch.state()

        class Boom(Exception):
            pass
        orig = st.orig_cell

        def failing(md, key, layers, kind="demand"):
            if "canopy" in layers or "water" in layers:
                raise Boom("deferred")
            return orig(md, key, layers, kind)
        st.orig_cell = failing
        try:
            la, lo = ll(np.array([100.0, 200.0]), np.zeros(2))
            with self.assertRaises(Boom):
                st.canopy_fn(self.md, "background")(la, lo)
            st.water.clear()
            with self.assertRaises(Boom):
                st.lake_fn(self.md, "background")(la, lo)
        finally:
            st.orig_cell = orig
            st.water.clear()

        class FakeDem:
            served = {}
        la, lo = ll(np.array([0.0, 50.0]), np.zeros(2))
        self.assertFalse(ep.dem_fallback(FakeDem(), la, lo, 15))
        z, tile = 15, 512
        fx = (lo / 360.0 + 0.5) * (2 ** z) * tile - 0.5
        fy = (0.5 - np.arcsinh(np.tan(np.radians(la))) / (2 * np.pi)) * (2 ** z) * tile - 0.5
        key = (z, int(fx[0]) // tile, int(fy[0]) // tile)
        FakeDem.served = {key: "mapterhorn"}
        self.assertFalse(ep.dem_fallback(FakeDem(), la, lo, 15))
        FakeDem.served = {key: "aws-terrarium"}
        self.assertTrue(ep.dem_fallback(FakeDem(), la, lo, 15))

    def test_auto_terrain_plan(self):
        from gpsd import earthpatch
        import vegetation
        pts = [list(ll(x, 0.0)) for x in range(0, 2001, 50)]
        base = {"enabled": True, "lines": [{"kind": "course", "points": pts, "name": "C", "rough": "auto"}]}
        plain = earthpatch.parse_plan(base).paint
        self.assertEqual((plain.rough, plain.dangers), ("auto", []))
        base["lines"][0]["dangers"] = [list(ll(1000, 30)), list(ll(1500, 400)), ["bad"]]
        c = earthpatch.parse_plan(base).paint
        self.assertEqual(c.dangers, [1000.0], "the one by the line, at its place along it")
        self.assertNotEqual(c.key, plain.key, "the ground is made again with them")
        # the boulders' model: the cell's own rocks' (they fit the place), else by region
        it = vegetation.Items(*(np.zeros(3) for _ in range(9)))
        it.kind = np.array([vegetation.KIND_TREE, vegetation.KIND_ROCK, vegetation.KIND_ROCK], np.uint8)
        it.group = np.array([vegetation.G_CONIFER, vegetation.G_ROCK, vegetation.G_ROCK], np.uint8)
        g = earthpatch.rock_groups(it, vegetation, np.array([31.0, 31.0]), np.array([-115.0, -115.0]))
        self.assertEqual(g.tolist(), [vegetation.G_ROCK] * 2)
        g = earthpatch.rock_groups(vegetation._empty(), vegetation, np.array([31.0]), np.array([-115.0]))
        self.assertEqual(g.tolist(), [vegetation.G_DESERT_ROCK])

    def test_grade_separation_reads_the_map_as_it_is(self):
        """BeamNG.Earth 1.7's grade separation reads a cell's neighbours in its own threads: they get its roads without
        the course's track (merging the track plans windows, whose road specs ask the grade separation again: the
        road workers deadlocked, the user's server.log 2026-10-29)."""
        import threading
        f = self.roads(*ll(1000, 0))
        self.assertTrue(any(str(i).startswith(cr.ID_PREFIX) for i in f.ids), "the track, for everyone else")
        got = {}

        def read():
            got["f"] = self.roads(*ll(1000, 0))
        t = threading.Thread(target=read, name=self.earthpatch.GRADESEP_THREADS + "_3")
        t.start(); t.join(60)
        self.assertIn("f", got)
        g = got["f"]
        self.assertFalse(any(str(i).startswith(cr.ID_PREFIX) for i in (g.ids if g is not None else [])),
                         "the grade separation's neighbour read: the map's roads only")

    def test_no_deadlock_with_grade_separation_on(self):
        """The deadlock itself: grade separation reading every cell's neighbours (BNE_GRADESEP=on; Ensenada's cells
        with short tunnels do so in the default mode), a course whose windows nobody planned yet, a fresh map data:
        a cell on the course still comes back."""
        import threading
        try:
            import gradesep
        except ImportError:
            self.skipTest("BeamNG.Earth before 1.7: no grade separation")
        import mapdata
        on, tun = gradesep.ON, getattr(gradesep, "TUNNELS", None)       # (1.7.0: ON only)
        gradesep.ON = gradesep.TUNNELS = True
        pts = [list(ll(x, 3.0)) for x in range(0, 6001, 50)]
        try:
            self.paintfile.write_course(pts, "Deadlock", 1.0, True, "test:deadlock")
            self.earthpatch.state().checked = -1e9
            md = mapdata.MapData(tempfile.mkdtemp(prefix="egps-md-gs-"), fetcher=object())
            got = {}

            def read():
                f = md.cell(self.mapcells.cell_of(*ll(1000, 3)), layers=("roads",)).layers["roads"]
                import roads
                roads.road_specs(f, None, None)         # (its level ranges: the grade separation, the neighbours)
                got["f"] = f
            t = threading.Thread(target=read, daemon=True)
            t.start(); t.join(90)
            self.assertIn("f", got, "came back (deadlocked before 1.6.7)")
        finally:
            gradesep.ON = on
            if tun is None:
                del gradesep.TUNNELS
            else:
                gradesep.TUNNELS = tun
            pts = [list(ll(x, 0.0)) for x in range(0, 6001, 50)]
            self.paintfile.write_course(pts, "Test 1000", 1.0, True, "test:1")
            self.earthpatch.state().checked = -1e9
            os.utime(self.paintfile.course_path())

    def test_turning_off(self):
        self.paintfile.write_course([], "", 1.0, False, "")
        self.earthpatch.state().checked = -1e9
        f = self.roads(*ll(1000, 0))
        self.assertFalse(any(str(i).startswith(cr.ID_PREFIX) for i in (f.ids if f is not None else [])))
        pts = [list(ll(x, 0.0)) for x in range(0, 6001, 50)]
        self.paintfile.write_course(pts, "Test 1000", 1.0, True, "test:1")
        self.earthpatch.state().checked = -1e9
        os.utime(self.paintfile.course_path())

    def test_the_first_ground_stays_and_a_pin_brings_back_a_snapshot(self):
        """A window is written once: what another process planned first is everyone's. A plan pinned to a snapshot
        (a replay's ground) uses the snapshot's windows as they are."""
        import time as _t
        ep, pf = self.earthpatch, self.paintfile
        st = ep.state()
        course = st.current().paint
        k = course.windows_near(*ll(1000, 0), 10)[0]
        path = os.path.join(pf.windows_dir(course.cid), f"w{k:06d}.json")
        mine = {"algo": cr.ALGO, "pieces": [{"id": "mine"}]}
        first = {"algo": cr.ALGO, "pieces": [{"id": "first"}]}
        if os.path.exists(path):
            os.unlink(path)
        self.assertEqual(pf.write_json_first(path, first), first)
        self.assertEqual(pf.write_json_first(path, mine), first, "never replaced")
        os.unlink(path)
        # pinned: a snapshot of this course with its own window k
        snap = pf.snapshots_dir("rec_pin_test")
        os.makedirs(snap, exist_ok=True)
        pf.write_json(os.path.join(snap, "meta.json"), {"cid": course.cid})
        pf.write_json(os.path.join(snap, f"w{k:06d}.json"), {"algo": cr.ALGO, "pieces": [{"id": "recorded"}]})
        obj = pf.read_json(pf.course_path())
        try:
            obj["pin"] = "rec_pin_test"
            pf.write_json(pf.course_path(), obj)
            t = _t.time_ns()
            os.utime(pf.course_path(), ns=(t, t))
            st.checked = -1e9
            c2 = st.current().paint
            self.assertTrue(c2.pin and c2.key != course.key)
            self.assertEqual(st.window(self.md, c2, k, "demand"), [{"id": "recorded"}])
            self.assertFalse(os.path.exists(path), "nothing written to the course's own ground")
            obj["pin"] = "not_this_course"
            pf.write_json(pf.course_path(), obj)
            os.utime(pf.course_path(), ns=(t + 10 ** 9, t + 10 ** 9))
            st.checked = -1e9
            self.assertIsNone(st.current().paint.pin, "another course's snapshot: planned as usual")
        finally:
            obj.pop("pin", None)
            pf.write_json(pf.course_path(), obj)
            os.utime(pf.course_path(), ns=(_t.time_ns() + 2 * 10 ** 9,) * 2)
            st.checked = -1e9
            st.current()

    def test_plan_cache_kept_per_ground(self):
        """BeamNG.Earth 1.6.1's plan cache (road plans shared by its processes on disk, per anchor): the dirt track is
        in those plans, so each GPS ground has its own folder; another course or setting at the same anchor never reads
        the old one's plans."""
        try:
            import plancache
        except ImportError:
            self.skipTest("BeamNG.Earth before 1.6.1: no plan cache")
        import grading
        ep, pf = self.earthpatch, self.paintfile
        st = ep.state()
        frame = self.geodesy.EnuFrame(*ll(1000, 0), 0.0)
        g = grading.Grader(frame, self.md, lambda la, lo: ground(la, lo))
        old = os.environ.get(plancache.RUN_ENV)
        os.environ[plancache.RUN_ENV] = "test_run"
        try:
            a = plancache.for_grader(self.md.cache_dir, g, None, None)
            self.assertIn("egps-" + ep.share_tag(st), a.dir, "the GPS ground in the folder")
            obj = pf.read_json(pf.course_path())
            try:
                pf.write_json(pf.course_path(), dict(obj, rough="extra" if obj.get("rough") != "extra" else "mild"))
                t = __import__("time").time_ns()
                os.utime(pf.course_path(), ns=(t, t))
                st.checked = -1e9
                b = plancache.for_grader(self.md.cache_dir, g, None, None)
                self.assertNotEqual(a.dir, b.dir, "another ground at the same anchor: another folder")
            finally:
                pf.write_json(pf.course_path(), obj)
                os.utime(pf.course_path(), ns=(__import__("time").time_ns() + 10 ** 9,) * 2)
                st.checked = -1e9
                st.current()
        finally:
            if old is None:
                os.environ.pop(plancache.RUN_ENV, None)
            else:
                os.environ[plancache.RUN_ENV] = old

    def test_revisit_cache_kept_per_ground(self):
        """BeamNG.Earth 1.6.3's revisit cache (a place's road tiles, far tiles, road plans and cell facts kept for the
        next visit): keyed by the GPS ground too, so a place built with one course or setting never comes back under
        another; with nothing painted, BeamNG.Earth's own key; a build the painter could not finish is not kept."""
        try:
            import revisit
        except ImportError:
            self.skipTest("BeamNG.Earth before 1.6.3: no revisit cache")
        ep, pf = self.earthpatch, self.paintfile
        st = ep.state()
        self.assertTrue(getattr(revisit.key, "_earthgps", False), "the hook is in")
        orig = revisit.key.__closure__ and [c.cell_contents for c in revisit.key.__closure__
                                             if callable(c.cell_contents) and c.cell_contents is not ep.share_tag]
        a = revisit.key("roads", 31.86, -116.6, 15, 1, 2)
        self.assertNotEqual(a, revisit.key("roads", 31.86, -116.6, 15, 1, 3), "still the tile's own")
        obj = pf.read_json(pf.course_path())
        try:
            pf.write_json(pf.course_path(), dict(obj, rough="extra" if obj.get("rough") != "extra" else "mild"))
            t = __import__("time").time_ns()
            os.utime(pf.course_path(), ns=(t, t))
            st.checked = -1e9
            b = revisit.key("roads", 31.86, -116.6, 15, 1, 2)
            self.assertNotEqual(a, b, "another ground at the same place: another key")
        finally:
            pf.write_json(pf.course_path(), obj)
            os.utime(pf.course_path(), ns=(__import__("time").time_ns() + 10 ** 9,) * 2)
            st.checked = -1e9
            st.current()
        self.assertEqual(revisit.key("roads", 31.86, -116.6, 15, 1, 2), a, "the same ground again: the same key")
        # nothing painted: BeamNG.Earth's own key (its cache shared as it is)
        from unittest import mock
        with mock.patch.object(ep, "share_tag", lambda s: "-"):
            plain = revisit.key("roads", 31.86, -116.6, 15, 1, 2)
        self.assertTrue(orig, "the original key function kept")
        self.assertEqual(plain, orig[0]("roads", 31.86, -116.6, 15, 1, 2))
        # a window the painter could not plan (its data not there yet): the builds running now are not kept
        before = revisit.faults()
        course = st.current().paint
        k = max(st.wins) + 50 if st.wins else 999
        st.win_failed[k] = __import__("time").monotonic()
        self.assertIsNone(st.window(self.md, course, k, "background"))
        self.assertGreater(revisit.faults(), before, "marked: not kept")
        st.win_failed.pop(k, None)

    def test_compute_sharing_only_between_the_same_ground(self):
        """BeamNG.Earth 1.6's compute sharing: a far tile is asked of / served to another server only when both build
        the same GPS ground (course, settings, painter code); replies of another ground or of a server without the
        painter are refused (the tile is built here)."""
        try:
            import peerwork as pw
        except ImportError:
            self.skipTest("BeamNG.Earth before 1.6: no compute sharing")
        import farfield
        ep = self.earthpatch
        st = ep.state()
        mine = ep.share_tag(st)
        self.assertNotEqual(mine, "-", "a course is painted")
        args = (1, LAT0, LON0, farfield.Tile(0, 0, 0), 12, None, None, False, farfield.Layout(32, 512, True, None))
        h = pw.job_header("far_geometry", args, {"roads": True, "grading": True})
        self.assertEqual(h["settings"]["egps"], mine, "the job says which ground")
        pw.check_job(h)                                         # the same ground: served
        other = dict(h, settings=dict(h["settings"], egps="0123456789ab"))
        with self.assertRaises(ValueError):
            pw.check_job(other)
        vanilla = dict(h, settings={k: v for k, v in h["settings"].items() if k != "egps"})
        with self.assertRaises(ValueError):
            pw.check_job(vanilla)                               # (a server without the painter asking)
        self.assertNotEqual(pw.job_key(h), pw.job_key(other), "kept apart in the reply cache")

        # replies, as they come off the network
        base = {"ok": True, "built": {}}
        ep._check_reply(st, dict(base, egps=mine))
        for bad in (dict(base, egps="0123456789ab"), dict(base)):
            with self.assertRaises(RuntimeError):
                ep._check_reply(st, bad)            # another ground, or a server without the painter
        ep._check_reply(st, {"ok": False, "miss": True})        # (not a tile: nothing to check)
        saved = pw.built_msg
        try:
            pw.built_msg = lambda built: ({}, [])
            head, _ = pw.reply_of("far_geometry", None)
        finally:
            pw.built_msg = saved
        self.assertEqual(head["egps"], mine, "our replies say which ground")

    def test_prefetch_plans_the_track_around_the_car(self):
        """The prefetch process's pass: the windows around the car's pose, nearest to where it is going first, planned
        and written for every process (so a cell's road data does not wait for them)."""
        ep = self.earthpatch
        st = ep.state()
        plan = st.current()
        course = plan.paint
        la, lo = ll(4000, 0)
        order = ep.prefetch_order(course, {"lat": la, "lon": lo, "speed": 40.0, "heading": 90.0})
        self.assertTrue(order, "windows near the car")
        mid = [(course.boxes[k][0] + course.boxes[k][2]) / 2 for k in order[:2]]
        self.assertTrue(all(m >= ll(4000, 0)[1] - 0.003 for m in mid), "ahead (east) first")
        with st.lock:
            for k in order:
                st.wins.pop(k, None)
        for k in order:
            p = os.path.join(self.paintfile.windows_dir(course.cid), f"w{k:06d}.json")
            if os.path.exists(p):
                os.unlink(p)
        self.paintfile.write_json(self.paintfile.pose_path(), {"lat": la, "lon": lo, "speed": 40.0, "heading": 90.0,
                                                               "t": __import__("time").time()})
        made = ep.prefetch_once(st, self.md, limit=3)
        self.assertEqual(made, order[:3])
        for k in made:
            self.assertTrue(os.path.exists(os.path.join(self.paintfile.windows_dir(course.cid), f"w{k:06d}.json")),
                            "written for the other processes")
            self.assertTrue(os.path.exists(os.path.join(self.paintfile.windows_dir(course.cid), f"r{k:06d}.json")),
                            "and the track's relief there")
        self.paintfile.write_json(self.paintfile.pose_path(), {"lat": la, "lon": lo, "t": 0})
        self.assertEqual(ep.prefetch_once(st, self.md), [], "an old pose: nothing")

    def set_rough(self, rough):
        pts = [list(ll(x, 0.0)) for x in range(0, 6001, 50)]
        obj = self.paintfile.write_course(pts, "Test 1000", 1.0, True, "test:1")
        obj["rough"] = rough
        self.paintfile.write_json(self.paintfile.course_path(), obj)
        t = __import__("time").time_ns()
        os.utime(self.paintfile.course_path(), ns=(t, t))
        self.earthpatch.state().checked = -1e9

    def test_track_relief_in_the_graded_ground(self):
        """The track's relief (relief.py) in BeamNG.Earth's graded heights (everything takes them: the physics block,
        the road mesh, the ground tiles): on the dirt, not on the paved road across, the same at any lift."""
        import grading
        frame = self.geodesy.EnuFrame(*ll(3000, 0), 0.0)
        st = self.earthpatch.state()

        def graded(xs, ys, **kw):
            la, lo = ll(np.asarray(xs, float), np.asarray(ys, float))
            g = grading.Grader(frame, self.md, lambda a, b: ground(a, b))
            return g.apply(la, lo, ground(la, lo), **kw)
        xs = np.arange(600.0, 1400.0, 2.0)
        road = np.arange(2300.0, 2700.0, 2.0)
        cross = np.arange(4196.0, 4205.0, 1.0)
        rough = [graded(v, np.zeros_like(v)) for v in (xs, road, cross)]
        lifted = graded(xs, np.zeros_like(xs), lift=grading.ROAD_LIFT)
        tunnel = graded(xs, np.zeros_like(xs), roads_only=True)
        self.set_rough("off")
        try:
            flat = [graded(v, np.zeros_like(v)) for v in (xs, road, cross)]
            flat_lifted = graded(xs, np.zeros_like(xs), lift=grading.ROAD_LIFT)
        finally:
            self.set_rough("on")
        dz = rough[0] - flat[0]
        self.assertGreater(np.ptp(dz), 0.3, "rough along the desert track")
        la, lo = ll(xs, np.zeros_like(xs))
        self.assertTrue(np.allclose(dz, st.relief_at(self.md, la, lo)), "the relief, added to the graded ground")
        self.assertTrue(np.allclose(lifted - flat_lifted, dz), "the same under the road mesh's lift")
        self.assertTrue(np.allclose(tunnel, flat[0]), "a tunnel's ends: none")
        self.assertGreater(np.ptp(rough[1] - flat[1]), 0.2, "along the mapped dirt road too")
        self.assertTrue(np.allclose(rough[2], flat[2]), "none where it crosses the paved road")
        self.set_rough("auto")
        try:
            auto = graded(xs, np.zeros_like(xs))
            self.assertTrue(np.allclose(auto - flat[0], st.relief_at(self.md, la, lo)), "auto: added the same way")
            self.assertFalse(np.allclose(auto, rough[0]), "and its own")
            self.assertGreater(np.ptp(auto - flat[0]), 0.2)
        finally:
            self.set_rough("on")

    def test_cut_bank_beside_the_track(self):
        """On a steep hillside BeamNG.Earth's grading cuts the dirt track in with a wall's step (a strip at the road's
        level, the ground straight up behind it) and no wall stands there on a dirt road: the course's own track gets a
        sloping cut bank instead (banks.py); the downhill side, the track itself and the ground past the bank stay."""
        import grading
        from gpsd import banks
        frame = self.geodesy.EnuFrame(*ll(1000, 0), 0.0)

        def steep(la, lo):
            _x, y = xy(np.asarray(la, float), np.asarray(lo, float))
            return 1.0 * np.maximum(y, 0.0)                 # 1:1 up to the north, a 3+ m cut at the core's edge

        def graded(ys):
            la, lo = ll(np.full_like(ys, 1000.3), ys)
            g = grading.Grader(frame, self.md, steep)
            return g.apply(la, lo, steep(la, lo))
        ys = np.arange(-12.0, 26.0, 0.25)
        self.set_rough("off")
        old = banks.FROM_TV
        try:
            with_banks = graded(ys)
            banks.FROM_TV = 99                              # (a course of the first terrain version: the step)
            step = graded(ys)
        finally:
            banks.FROM_TV = old
            self.set_rough("on")
        rise = np.diff(step) / 0.25
        self.assertGreater(rise.max(), 2.5, f"BeamNG.Earth's step (the test needs it): {rise.max():.2f}")
        bank = np.diff(with_banks) / 0.25
        self.assertLess(bank.max(), 1.6, "a sloping bank")
        self.assertTrue(np.all(with_banks <= steep(*ll(np.full_like(ys, 1000.3), ys)) + 0.05), "a cut, never a fill")
        same = (ys < 2.0) | (ys > 22.0)
        self.assertTrue(np.allclose(with_banks[same], step[same]), "the track, the downhill side, past the bank")
        self.assertGreater(self.earthpatch.state().stats["bank_points"], 0)

    def test_course_ground_in_the_blocks_surfaces(self):
        """BeamNG.Earth's block surfaces (surface.paint_lots, the last land paint of a block) get the course's ground
        (surfaces.py): the dry wash across the course at x 600 is a creek bed (the land cover there is unknown: not
        dry country: gravel), the sand and gravel layers are BeamNG.Earth's materials too, its own indices kept."""
        import surface as surfacemod
        from gpsd import surfaces
        st = self.earthpatch.state()
        names = [m[0] for m in surfacemod.MATERIALS]
        self.assertEqual(names[surfacemod.DIRT], "beamngEarthDirt", "BeamNG.Earth's own indices kept")
        self.assertIn(("bngEarthGroundOcSand", "SAND"), surfacemod.MATERIALS)
        self.assertIn(("bngEarthGroundOcGravel", "GRAVEL"), surfacemod.MATERIALS)
        gravel = names.index("bngEarthGroundOcGravel")
        st.md = self.md
        xs = np.arange(560.0, 641.0, 2.0)
        gx, gy = np.meshgrid(xs, np.array([-2.0, 0.0, 2.0]))
        la, lo = ll(gx, gy)                 # (a block's grid: rows by columns)
        idx = np.full(gx.shape, surfacemod.LOOSE, np.uint8)
        before = st.stats["surface_points"]
        out = surfacemod.paint_lots(idx, la, lo, [])[1]
        self.assertEqual(int(out[np.argmin(np.abs(xs - 600))]), gravel, "the wash's bed")
        self.assertEqual(int(out[0]), surfacemod.DIRT, "the track away from it: packed")
        self.assertGreater(st.stats["surface_points"], before)
        self.assertGreaterEqual(self.earthpatch.state().current().paint.tv, surfaces.FROM_TV)

    def test_boulders_in_the_canyon(self):
        """Rocks beside the track where it runs through the canyon (BeamNG.Earth's own vegetation rocks)."""
        import vegetation
        veg = vegetation.Vegetation(self.md, None)
        veg._load = lambda x, y: vegetation._empty()        # (the test world has no canopy or land cover data)
        rocks = []
        for key in self.mapcells.cells_for_bbox(*ll(-50, -60), *ll(6050, 60)):
            it = veg.cell(key)
            sel = it.kind == vegetation.KIND_ROCK
            x, y = xy(it.lat[sel], it.lon[sel])
            rocks += list(zip(x, y))
        r = np.array(rocks).reshape(-1, 2)
        self.assertGreater(len(r), 20, "rocks by the track")
        self.assertTrue(np.all(r[:, 0] > 4700), "in the canyon only")
        self.assertTrue(np.all(np.abs(r[:, 1]) > 2.5), "beside the track, not on it")

    def test_trees_off_the_track(self):
        """Trees, bushes and rocks standing on the course's track are taken out (BeamNG.Earth keeps them off a road by
        its class's width only, and a cell built before the course was loaded had none of it); beside it they stay.
        Cells are kept on disk per GPS ground."""
        import vegetation
        veg = vegetation.Vegetation(self.md, tempfile.mkdtemp(prefix="egps-veg-"))
        xs = np.array([800.0, 800.0, 800.0, 800.0, 1200.0, 2500.0, 2500.0])
        ys = np.array([0.0, 2.0, 9.0, -30.0, 1.5, 0.5, 14.0])
        la, lo = ll(xs, ys)
        n = len(xs)

        def build(x, y):
            return vegetation.Items(np.asarray(lo, np.float64), np.asarray(la, np.float64), np.full(n, 8, np.float32),
                                    np.full(n, 2, np.float32), np.zeros(n, np.uint8), np.zeros(n, np.uint8),
                                    np.zeros(n, np.float32), np.zeros(n, np.float32), np.ones(n, np.float32))
        veg._build = build
        key = self.mapcells.cell_of(*ll(800, 0))
        it = veg.cell(key)
        x, y = xy(it.lat, it.lon)
        got = sorted((round(float(a)), round(float(b))) for a, b in zip(x, y))
        self.assertNotIn((800, 0), got, "a tree in the middle of the track: gone")
        self.assertNotIn((800, 2), got, "one on its side: gone")
        self.assertIn((800, 9), got, "one past its edge: stays")
        self.assertIn((800, -30), got, "one well away: stays")
        key2 = self.mapcells.cell_of(*ll(2500, 0))
        it2 = veg.cell(key2)
        x2, y2 = xy(it2.lat, it2.lon)
        got2 = sorted((round(float(a)), round(float(b))) for a, b in zip(x2, y2))
        self.assertNotIn((2500, 0), got2, "one on the dirt road the course follows: gone")
        self.assertIn((2500, 14), got2, "beside that road: stays")
        p = veg._path(int(key[1]), int(key[2]))
        self.assertIn("egps-" + self.earthpatch.share_tag(self.earthpatch.state()), p, "kept per GPS ground")

    def test_tiles_as_the_server_builds_them(self):
        """build_tile with the options BeamNG.Earth's server passes (walls=, which calls the wrapped retaining_walls
        with its own extra arguments: 1.5.5's decks=), along the course: the tiles build, and walls come out."""
        import roads as roadsmod
        for x0 in (1500, 2200, 2700, 4000):
            frame = self.geodesy.EnuFrame(*ll(x0, 0), 0.0)
            cells = [self.md.cell(k, layers=("roads",)).layers["roads"] for k in roadsmod.cells_of_tile(frame, 0, 0)]
            walls = []
            chunks = roadsmod.build_tile(frame, 0, 0, cells, lambda la, lo: ground(la, lo), walls=walls)
            self.assertIsInstance(chunks, list, f"tile at x {x0} built")
            self.assertTrue(chunks or self.drawn_dirt(frame, 0, 0, cells, chunks), f"tile at x {x0}: something drawn")
            self.assertIsInstance(walls, list)

    def test_earth_builds_the_flattened_overpasses_as_walls(self):
        """What BeamNG.Earth itself builds without the clearing: the overpasses the clearing flattens get decks at the
        road's height (walls across it), the one it keeps a deck high over the road (the rule agrees with Earth)."""
        import roads as roadsmod
        self.paintfile.write_course([], "", 1.0, False, "")
        self.earthpatch.state().checked = -1e9
        try:
            got = {}
            for x0, fid in ((2200, "0ee5"), (2500, "0dd4"), (2700, "0ff6")):
                frame = self.geodesy.EnuFrame(*ll(x0, 0), 0.0)
                cells = [self.md.cell(k, layers=("roads",)).layers["roads"] for k in roadsmod.cells_of_tile(frame, 0, 0)]
                chunks = roadsmod.build_tile(frame, 0, 0, cells, lambda la, lo: ground(la, lo))
                zs = [p[2] for c in chunks if c.get("deck") and c.get("fid") == fid for p in c["n"]]
                got[fid] = max(zs) if zs else None
            self.assertLess(got["0ee5"], 1.0, f"low overpass: a wall in BeamNG.Earth ({got})")
            self.assertLess(got["0ff6"], 1.0, f"overpass in a cutting: a wall in BeamNG.Earth ({got})")
            self.assertGreater(got["0dd4"], 5.0, f"flyover: high over the road in BeamNG.Earth ({got})")
        finally:
            pts = [list(ll(x, 0.0)) for x in range(0, 6001, 50)]
            self.paintfile.write_course(pts, "Test 1000", 1.0, True, "test:1")
            self.earthpatch.state().checked = -1e9
            os.utime(self.paintfile.course_path())

    def test_ruts_where_the_track_blends_in(self):
        """Imagery in BeamNG.Earth's cache: light sand west of x 1150 (the dirt track's own colour), green scrub east
        of it. A road tile over both: rut strips (over the dirt, as road markings) only on the sand."""
        import roads as roadsmod
        from PIL import Image

        from gpsd import ruts
        root = os.path.join(self.md.cache_dir, "imagery", "eox2023")
        z = 14
        la0, lo0 = ll(-300, -400)
        la1, lo1 = ll(2500, 400)
        x0, y1 = (int(v // 256) for v in ruts.mercator_px(la0, lo0, z))
        x1, y0 = (int(v // 256) for v in ruts.mercator_px(la1, lo1, z))
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                im = Image.new("RGB", (256, 256))
                px = im.load()
                for u in range(256):
                    lon = (tx * 256 + u + 0.5) / (256.0 * (1 << z)) * 360.0 - 180.0
                    ex, _ = xy(LAT0, lon)
                    c = (214, 188, 150) if ex < 1150 else (92, 104, 60)
                    for v in range(256):
                        px[u, v] = c
                os.makedirs(os.path.join(root, str(z), str(tx)), exist_ok=True)
                im.save(os.path.join(root, str(z), str(tx), f"{ty}.jpg"), quality=95)
        self.earthpatch.state()._imagery = None     # (earlier tests looked before these tiles were there)
        frame = self.geodesy.EnuFrame(*ll(1000, 0), 0.0)
        cells = [self.md.cell(k, layers=("roads",)).layers["roads"] for k in roadsmod.cells_of_tile(frame, 0, 0)]
        self.assertIsNotNone(self.earthpatch.state().cache_dir, "BeamNG.Earth's cache folder known")
        chunks = roadsmod.build_tile(frame, 0, 0, cells, lambda la, lo: ground(la, lo))
        track = [c for c in chunks if c["m"] == "m_dirt_road"]
        if getattr(roadsmod, "ROADS_IN_GROUND", False):      # (1.6: painted into the ground; the ruts follow its line)
            self.assertFalse(track, "no dirt pieces of its own")
            self.assertTrue(self.drawn_dirt(frame, 0, 0, cells, chunks), "the track painted into the ground")
            track = self.earthpatch.dirt_chunks(roadsmod, frame, 0, 0, cells, lambda la, lo: ground(la, lo))
        rut = [c for c in chunks if c["m"] == ruts.RUT_MATERIAL]
        self.assertTrue(track, "the dirt track on this tile")
        self.assertEqual(len(rut) % 2, 0, "ruts in pairs")
        self.assertTrue(rut, "ruts on the sand")
        xs = np.array([p[0] for c in rut for p in c["n"]])
        self.assertLess(xs.max(), 150 + ruts.GAP_M, f"only over the sand (west of x 1150): {xs.max():.0f}")
        self.assertLess(min(p[2] for c in rut for p in c["n"]) - min(p[2] for c in track for p in c["n"]), 5.0)
        import roadmesh
        self.assertEqual(roadmesh.layer_of(rut[0]), "mark", "drawn over the dirt like a road marking")
        if not getattr(roadsmod, "ROADS_IN_GROUND", False):
            self.assertEqual(roadmesh.layer_of(track[0]), "base")


if __name__ == "__main__":
    unittest.main()
