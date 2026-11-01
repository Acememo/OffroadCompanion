"""Terrain 7's sections (gpsd/variety.py): sand traps, rock sections, gravel and rock crawls, only where the place has
them, the same for everyone, soft on the game's 2 m lattice, and the ground under them to match."""
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
    from gpsd import surfaces
    from gpsd import variety as vy

LAT0, LON0 = 30.4, -115.6
MATS = {"ASPHALT": 0, "GRASS": 1, "DUSTY": 2, "LOOSE": 3, "ROCK": 4, "SNOW": 5, "MUD": 6, "COBBLE": 7, "LAWN": 8,
        "DIRT": 9, "SAND": 10, "GRAVEL": 11}
# the stretches of the course (x, m east): what each is
PLAIN = (100, 700)          # open flat desert
WASH = (900, 1400)          # a dry wash the course runs in
CANYON = (2000, 3200)       # a desert canyon (the walls rise 1.5 m per m from 7 m off the line)
HILL = (3500, 4200)         # a rocky hillside (the ground rises 0.6 m per m to the north)
FAN = (4500, 5300)          # an alluvial fan: the course climbs a steady 5 %
LAKE = (5500, 5800)         # a dry lake
ROAD = (5900, 6300)         # a mapped dirt road followed
GREEN = (6400, 7000)        # green country (grassland), a creek mapped intermittent along it


def frame(lat0=LAT0, lon0=LON0):
    kx = math.radians(1) * cr.R_EARTH * math.cos(math.radians(lat0))
    ky = math.radians(1) * cr.R_EARTH

    def ll(x, y):
        return lat0 + np.asarray(y, np.float64) / ky, lon0 + np.asarray(x, np.float64) / kx

    def xy(lat, lon):
        return (np.asarray(lon) - lon0) * kx, (np.asarray(lat) - lat0) * ky
    return ll, xy


def inside(x, span):
    return (x > span[0]) & (x < span[1])


def core(span, m=150.0):
    """The stretch without its ends (where the ground changes from the last stretch's)."""
    m = min(m, (span[1] - span[0]) / 4.0)
    return (span[0] + m, span[1] - m)


def world(tv=7, shift=0.0, dangers=(2600.0, 600.0), rough="auto"):
    """7.2 km due east, the track along y = 0 (the stretches above); shift: the whole place moved north (km), so the
    stretches' hashes differ (another place on the Earth, the same kind of ground)."""
    ll, xy = frame(LAT0 + shift / 111.0, LON0)
    c = cr.Course([tuple(map(float, ll(x, 0.0))) for x in range(0, 7201, 40)], tv=tv)
    c.rough = rough

    def ground(lat, lon):
        x, y = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        z = np.where(inside(x, CANYON), np.maximum(0.0, np.abs(y) - 7.0) * 1.5, 0.0)
        z = z + np.where(inside(x, HILL), np.maximum(0.0, y) * 0.6, 0.0)
        z = z + 0.05 * np.clip(x - FAN[0], 0.0, FAN[1] - FAN[0]) + np.where(x > FAN[1], 0.0, 0.0)
        return z

    def road_fn(lat0, lon0, lat1, lon1, plane):
        (la, lo), (lb, lob) = ll(ROAD[0], 0.0), ll(ROAD[1], 0.0)
        ax, ay = plane.xy(float(la), float(lo))
        bx, by = plane.xy(float(lb), float(lob))
        return [(ax, ay, bx, by, 3.0, 0)]

    def land(lat, lon):
        x, _ = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        return np.where(inside(x, GREEN), 30, 60).tolist()

    def lake(lat, lon):
        x, _ = xy(np.asarray(lat, np.float64), np.asarray(lon, np.float64))
        return inside(x, LAKE).astype(float).tolist()

    def lonlat(pts):
        la, lo = ll(np.array([p[0] for p in pts], float), np.array([p[1] for p in pts], float))
        return np.stack([lo, la], 1)
    waters = [("wash", 6.0, False, lonlat([(WASH[0], 0.0), (WASH[1], 0.0)])),
              ("wash", 2.0, False, lonlat([(GREEN[0], 3.0), (GREEN[1], 3.0)]))]

    def waters_fn(lat0, lon0, lat1, lon1):
        return [w for w in waters if w[3][:, 0].max() >= lon0 and w[3][:, 0].min() <= lon1 and
                w[3][:, 1].max() >= lat0 and w[3][:, 1].min() <= lat1]

    def pieces(k):
        a, b = c.inner(k)
        return [{"id": f"~egpsT{k:06d}000", "w": 7.0, "i0": a,
                 "ll": [[float(c.lon[i]), float(c.lat[i])] for i in range(a, b + 1)]}]
    pcs = {k: pieces(k) for k in range(c.nwin)}
    profs = {k: rf.window_profile(c, k, pcs[k], road_fn, lambda la, lo: ground(la, lo).tolist(), lake, land,
                                  waters_fn) for k in range(c.nwin)}
    c.dangers = rf.danger_s(c, [tuple(map(float, ll(x, 0.0))) for x in dangers])
    return ll, xy, c, profs, pcs, ground, land


def along(c, profs, ll):
    """(x, the facts, the weights sand, rock, gravel, crawl) every 10 m along the course."""
    s = np.arange(0.0, (c.n - 1) * rf.STEP, rf.STEP)
    f = rf._Facts(profs).at(s)
    ws, wr, wg = vy.weights(c, s, f)
    wc = vy.crawl_weight(c, s, f) if getattr(c, "rough", "on") == "auto" else np.zeros(len(s))
    return s, f, ws, wr, wg, wc


@unittest.skipUnless(HAVE_NP, "numpy")
class TestWhere(unittest.TestCase):
    """Each kind of section only where the place has it; where it may come, the hash of the place decides."""

    @classmethod
    def setUpClass(cls):
        cls.runs = []
        for k in range(16):
            ll, _xy, c, profs, _p, _g, _l = world(shift=1.7 * k)
            cls.runs.append(along(c, profs, ll))

    def share(self, which, span, thr=0.5):
        got = []
        for s, f, ws, wr, wg, wc in self.runs:
            w = {"sand": ws, "rock": wr, "gravel": wg, "crawl": wc}[which]
            m = inside(s, span)          # (the course runs due east from x = 0: s is x)
            got.append(float(np.mean(w[m] >= thr)))
        return float(np.mean(got))

    def test_sand_traps_in_the_washes_and_canyons_rarely_on_the_plain(self):
        self.assertGreater(self.share("sand", WASH), 0.4, "a wash the course runs in: mostly sand traps")
        self.assertGreater(self.share("sand", CANYON), 0.1, "a desert canyon's floor: some")
        self.assertLess(self.share("sand", PLAIN), 0.15, "open desert: now and then")
        for span in (HILL, LAKE, GREEN):
            self.assertEqual(self.share("sand", core(span), 0.05), 0.0, f"none at {span}")
        self.assertLess(self.share("sand", ROAD), 0.03, "a mapped dirt road: hardly ever")

    def test_rock_in_canyons_and_on_rocky_hillsides_only(self):
        self.assertGreater(self.share("rock", CANYON), 0.25)
        self.assertGreater(self.share("rock", HILL), 0.2)
        for span in (PLAIN, WASH, FAN, LAKE, GREEN):
            self.assertEqual(self.share("rock", core(span), 0.05), 0.0, f"none at {span}")

    def test_gravel_on_the_fans_and_green_creeks(self):
        self.assertGreater(self.share("gravel", FAN), 0.3, "an alluvial fan: gravel")
        self.assertGreater(self.share("gravel", GREEN), 0.05, "a creek bed in green country: some")
        for span in (PLAIN, WASH, LAKE):
            self.assertEqual(self.share("gravel", core(span), 0.05), 0.0, f"none at {span}")

    def test_never_two_at_once(self):
        for s, f, ws, wr, wg, wc in self.runs:
            self.assertTrue(np.all(ws + wr + wg <= 1.0 + 1e-9))

    def test_crawls_at_canyon_dangers_only(self):
        s, f, ws, wr, wg, wc = self.runs[0]
        self.assertEqual(float(wc[inside(s, (300, 900))].max()), 0.0, "the DANGER in open desert: no crawl")
        crawled = [float(r[5][inside(r[0], (2550, 2650))].max()) for r in self.runs]
        self.assertGreater(np.mean(np.asarray(crawled) > 0.9), 0.4, "the one in the canyon: a crawl, mostly")
        self.assertLess(np.mean(np.asarray(crawled) > 0.9), 1.0, "... not always")
        for r in self.runs:
            self.assertEqual(float(r[5][(r[0] < 2350) | (r[0] > 2900)].max()), 0.0, "only around the waypoint")

    def test_no_crawls_off_auto_nor_before_terrain_7(self):
        ll, _xy, c, profs, _p, _g, _l = world(rough="on")
        self.assertEqual(float(along(c, profs, ll)[5].max()), 0.0)
        ll, _xy, c6, profs6, _p, _g, _l = world(tv=6)
        s, f, ws, wr, wg, wc = along(c6, profs6, ll)
        self.assertEqual(float(max(ws.max(), wr.max(), wg.max(), wc.max())), 0.0)
        self.assertNotIn("grade", profs6[0])
        self.assertNotIn("washn", profs6[0])


@unittest.skipUnless(HAVE_NP, "numpy")
class TestShape(unittest.TestCase):
    """The heights: a sand trap sinks the track, a crawl is a staircase of shelves; nothing spiky on the lattice."""

    @classmethod
    def setUpClass(cls):
        for k in range(16):             # a place where the canyon's waypoint is a crawl and the wash a sand trap
            ll, xy, c, profs, pcs, g, land = world(shift=1.7 * k)
            r = along(c, profs, ll)
            if r[5].max() > 0.99 and np.mean(r[2][inside(r[0], WASH)] > 0.9) > 0.5:
                break
        cls.ll, cls.c, cls.profs, cls.pcs, cls.land, cls.res = staticmethod(ll), c, profs, pcs, staticmethod(land), r

    def field(self, x0, x1, auto=True, scale=1.0, c=None):
        gx, gy = np.meshgrid(np.arange(x0, x1, 2.0), np.arange(-20.0, 20.0, 2.0))     # (the game's lattice)
        la, lo = self.ll(gx, gy)
        return gx, gy, rf.relief(c or self.c, self.profs, la, lo, scale, auto=auto)

    def test_a_sand_trap_sinks_the_track(self):
        s, f, ws, wr, wg, wc = self.res
        m = inside(s, WASH) & (ws > 0.95)
        x0, x1 = float(s[m].min()), float(s[m].max())
        gx, gy, h = self.field(x0, x1)
        track = np.abs(gy) <= 2.0
        beside = (np.abs(gy) >= 5.0) & (np.abs(gy) <= 6.0)
        self.assertLess(h[track].mean(), h[beside].mean() - 0.15, "the track sunk, the sand thrown up beside it")

    def test_a_crawl_is_shelves_soft_on_the_lattice(self):
        s, f, ws, wr, wg, wc = self.res
        m = wc > 0.99
        x0, x1 = float(s[m].min()), float(s[m].max())
        gx, gy, h = self.field(x0, x1)
        mid = h[np.argmin(np.abs(gy[:, 0]))]
        self.assertGreater(np.ptp(mid), 0.6, "steps up and down")
        self.assertLess(np.abs(np.diff(mid)).max() / 2.0, 0.45, "each step over a few metres, no wall")
        k = max(np.abs(np.diff(h, 2, axis=0)).max(), np.abs(np.diff(h, 2, axis=1)).max())
        self.assertLess(k, 0.8, f"no point stands out of its neighbours by much ({k:.2f} m)")
        _gx, _gy, h0 = self.field(x0, x1, auto=False)
        self.assertLess(np.ptp(h0[np.argmin(np.abs(gy[:, 0]))]), np.ptp(mid), "Auto only")

    def test_soft_everywhere(self):
        for x0, x1 in (WASH, CANYON, HILL, FAN):
            gx, gy, h = self.field(x0, x1, scale=1.6)
            k = max(np.abs(np.diff(h, 2, axis=0)).max(), np.abs(np.diff(h, 2, axis=1)).max())
            self.assertLess(k, 0.8, f"{x0}-{x1}: {k:.2f} m")

    def test_flat_is_flat(self):
        gx, gy, h = self.field(*WASH, auto=False, scale=0.0)
        self.assertEqual(float(np.abs(h).max()), 0.0)


@unittest.skipUnless(HAVE_NP, "numpy")
class TestGround(unittest.TestCase):
    """The ground under them (surfaces.py) and the drawn track (no dirt decal over sand, rock and crawls)."""

    @classmethod
    def setUpClass(cls):
        TestShape.setUpClass.__func__(cls)

    def mats(self, x0, x1, y=0.0):
        gx = np.arange(x0, x1, 2.0)
        la, lo = self.ll(gx, np.full(len(gx), y))
        cls_ = np.asarray(self.land(la, lo))
        idx = np.where(cls_ == 30, MATS["GRASS"], MATS["LOOSE"]).astype(np.uint8)
        idx = np.where(np.abs(y) <= 3.5, MATS["DIRT"], idx).astype(np.uint8)
        return gx, surfaces.course_surfaces(idx, la, lo, self.c, self.profs, MATS)

    def test_surfaces_follow_the_sections(self):
        s, f, ws, wr, wg, wc = self.res
        k = 1.0 - wc                    # (a crawl wins)
        for w, mat, y in ((ws * k, "SAND", 0.0), (ws * k, "SAND", 5.0), (wr * k, "ROCK", 0.0),
                          (wr * k, "GRAVEL", 4.5), (wg * k, "GRAVEL", 0.0), (wc, "ROCK", 0.0), (wc, "ROCK", 5.5)):
            m = w > 0.95
            if not m.any():
                continue
            gx, got = self.mats(float(s[m].min()), float(s[m].max()), y)
            ww = np.interp(gx, s, w)
            self.assertTrue(np.all(got[ww > 0.95] == MATS[mat]), f"{mat} at {y} m")
        self.assertTrue((wr > 0.95).any() and (ws > 0.95).any() and (wc > 0.95).any())

    def test_the_dirt_decal_only_where_dirt(self):
        s, f, ws, wr, wg, wc = self.res
        ps = [p for k in sorted(self.pcs) for p in self.pcs[k]]
        out, complete = vy.split_bare(self.c, self.profs, ps)
        self.assertTrue(complete)
        ids = [p["id"] for p in out]
        self.assertEqual(len(ids), len(set(ids)), "ids unique")
        bare = np.maximum(np.maximum(ws, wr), wc) >= vy.BARE_W
        n_rock = 0
        for p in out:
            ii = int(p["i0"]) + np.arange(len(p["ll"]))
            inner = ii[1:-1] if len(ii) > 2 else ii[:1]
            want = bare[np.minimum(inner, len(bare) - 1)]
            self.assertTrue(np.all(want == (p.get("surface") == "rock")), p["id"])
            n_rock += p.get("surface") == "rock"
        self.assertGreater(n_rock, 0)
        # every point of the course's track still drawn, runs joined end to start
        for k in self.pcs:
            mine = [p for p in out if p["id"].startswith(self.pcs[k][0]["id"])]
            pts = [q for p in mine for q in p["ll"]]
            self.assertEqual(len({tuple(q) for q in pts}), len(self.pcs[k][0]["ll"]))
        # a window not planned: all dirt for now, and said so
        some = dict(list(self.profs.items())[:1])
        _o, complete = vy.split_bare(self.c, some, ps)
        self.assertFalse(complete)

    def test_crawl_boulders_leave_a_line(self):
        b = (LON0 - 0.3, LAT0 - 0.3, LON0 + 0.3, LAT0 + 1.0)
        r = rf.rocks(self.c, self.profs, b, auto=True)
        idx, d, s = rf.nearest(self.c, self.profs, r["lat"], r["lon"])
        f = rf._Facts(self.profs).at(s)
        wc = vy.crawl_weight(self.c, s, f)
        intrack = (np.abs(d) <= f["hw"]) & (wc > 0.4)
        self.assertGreater(intrack.sum(), 5, "boulders in the crawl's track")
        lane = vy.crawl_lane(s[intrack], f["hw"][intrack])
        gap = np.abs(d[intrack] - lane)
        self.assertGreater(gap.min(), vy.CRAWL_LANE[2] - 0.6, "a line kept clear between them")
        self.assertTrue(np.all(r["size"][idx[intrack]] <= 0.75))
        r0 = rf.rocks(self.c, self.profs, b, auto=False)
        n_auto = np.count_nonzero(intrack)
        idx0, d0, s0 = rf.nearest(self.c, self.profs, r0["lat"], r0["lon"])
        f0 = rf._Facts(self.profs).at(s0)
        self.assertEqual(int(np.count_nonzero(np.abs(d0) <= f0["hw"])), 0, "none in the track off Auto")
        self.assertGreater(n_auto, 0)


if __name__ == "__main__":
    unittest.main()
