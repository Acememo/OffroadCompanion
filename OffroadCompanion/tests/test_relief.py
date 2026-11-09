"""The track's relief (relief.py): where it goes, what it is made of, and that it is the same whoever asks for it.

Pure: numpy only (no BeamNG.Earth checkout needed; test_paint.py checks it inside BeamNG.Earth's grading).
"""
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

LAT0, LON0 = 31.02, -115.43


def frame():
    kx = math.radians(1) * cr.R_EARTH * math.cos(math.radians(LAT0))
    ky = math.radians(1) * cr.R_EARTH

    def ll(x, y):
        return LAT0 + np.asarray(y, np.float64) / ky, LON0 + np.asarray(x, np.float64) / kx

    def xy(lat, lon):
        return (np.asarray(lon) - LON0) * kx, (np.asarray(lat) - LAT0) * ky
    return ll, xy


@unittest.skipUnless(HAVE_NP, "numpy")
class TestRelief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ll, xy = frame()
        cls.ll, cls.xy = staticmethod(ll), staticmethod(xy)
        # 6 km due east. Ground: flat desert to 2 km; 2-3 km a paved road along the course; at 3.5 km a paved road
        # across it; 4-5 km a canyon (walls rising 1.5 m per m from 7 m off the line); the 5.2-5.8 km a dry lake
        cls.course = cr.Course([tuple(map(float, ll(x, 0.0))) for x in range(0, 6001, 50)])

        def road_fn(lat0, lon0, lat1, lon1, plane):
            out = []
            for xa, ya, xb, yb, hw, paved in ((2000, 0, 3000, 0, 3.5, 1), (3500, -300, 3500, 300, 4.0, 1)):
                (la, lo), (lb, lob) = ll(xa, ya), ll(xb, yb)
                ax, ay = plane.xy(float(la), float(lo))
                bx, by = plane.xy(float(lb), float(lob))
                out.append((ax, ay, bx, by, hw, paved))
            return out

        def ground(lat, lon):
            x, y = xy(lat, lon)
            canyon = (x > 4000) & (x < 5000)
            return np.where(canyon, np.maximum(0.0, np.abs(y) - 7.0) * 1.5, 0.0)

        def water(lat, lon):
            x, _ = xy(lat, lon)
            return ((x > 5200) & (x < 5800)).astype(float).tolist()

        def pieces(k):
            a, b = cls.course.inner(k)
            return [{"w": 8.0, "ll": [[cls.course.lon[i], cls.course.lat[i]] for i in range(a, b + 1)]}]
        cls.profiles = {k: rf.window_profile(cls.course, k, pieces(k), road_fn,
                                             lambda la, lo: ground(la, lo).tolist(), water)
                        for k in range(cls.course.nwin)}

    def at(self, x, y, profiles=None, scale=1.0):
        la, lo = self.ll(x, y)
        return rf.relief(self.course, profiles or self.profiles, la, lo, scale)

    def fact(self, name, x):
        i = int(round(x / cr.STEP_M))
        for p in self.profiles.values():
            if p["a"] <= i <= p["b"]:
                return p[name][i - p["a"]]

    def test_the_facts_of_the_course(self):
        self.assertEqual(self.fact("hw", 1000), 4.0, "the dirt track's own width")
        self.assertEqual(self.fact("rough", 1000), 1.0, "desert: rough")
        self.assertEqual(self.fact("rough", 2500), 0.0, "along the paved road: none")
        self.assertEqual(self.fact("rough", 3500), 0.0, "crossing the paved road: none")
        self.assertEqual(self.fact("rough", 3800), 1.0)
        self.assertGreater(self.fact("rock", 4500), 0.9, "a canyon")
        self.assertEqual(self.fact("rock", 1000), 0.0)
        self.assertGreater(self.fact("lake", 5500), 0.9, "a dry lake")

    def test_where_the_road_is(self):
        """ctr: the middle of a road the course follows, m left of the course line (the course signs stand beside
        it); 0 on the course's own dirt track."""
        ll = self.ll

        def road_fn(lat0, lon0, lat1, lon1, plane):
            (la, lo), (lb, lob) = ll(0, 3.0), ll(1000, 3.0)
            ax, ay = plane.xy(float(la), float(lo))
            bx, by = plane.xy(float(lb), float(lob))
            return [(ax, ay, bx, by, 4.0, 0)]
        p = rf.window_profile(self.course, 0, [], road_fn, lambda la, lo: [0.0] * len(la), None)
        self.assertAlmostEqual(p["ctr"][30], 3.0, places=1)
        self.assertEqual(p["hw"][30], 4.0)
        self.assertEqual(self.profiles[0]["ctr"][30], 0.0, "the dirt track: on the course line")

    def test_a_dirt_road_beside_the_course_is_its_road(self):
        """A recorded GPS line 15 m off the dirt road it followed: that road is the course's (no second track laid
        beside it), and its relief goes on that road (the user, 2026-10-22)."""
        ll, xy = self.ll, self.xy
        from gpsd import courseroads as crm
        x = [float(v) for v in range(0, 1001, 10)]
        y = [0.0] * len(x)
        tx, ty = [1.0] * len(x), [0.0] * len(x)
        dirt = [(0.0, 15.0, 1000.0, 15.0, 3.0, 0)]
        paved = [(0.0, 15.0, 1000.0, 15.0, 3.0, 1)]
        across = [(500.0 - 300.0, -520.0, 500.0 + 300.0, 520.0, 3.0, 0)]     # (a dirt road crossing at 60 degrees)
        self.assertTrue(all(crm.covered(x, y, tx, ty, dirt)), "a dirt road 15 m off: followed")
        self.assertFalse(any(crm.covered(x, y, tx, ty, paved)), "a highway 15 m off: not the course")
        self.assertFalse(any(crm.covered(x, y, tx, ty, across)), "a dirt road across it: not followed")
        self.assertFalse(any(crm.covered(x, y, tx, ty, [sg[:5] for sg in dirt])), "no paved flag: the narrow rule")

        def road_fn(lat0, lon0, lat1, lon1, plane):
            (la, lo), (lb, lob) = ll(0, 15.0), ll(2000, 15.0)
            ax, ay = plane.xy(float(la), float(lo))
            bx, by = plane.xy(float(lb), float(lob))
            return [(ax, ay, bx, by, 3.0, 0)]
        prof = {k: rf.window_profile(self.course, k, [], road_fn, lambda la, lo: [0.0] * len(la), None)
                for k in (0, 1)}
        self.assertAlmostEqual(prof[0]["ctr"][50], 15.0, places=0)
        xs = np.arange(300.0, 1700.0, 1.0)
        on_road = rf.relief(self.course, prof, *ll(xs, np.full_like(xs, 15.0)))
        self.assertGreater(np.ptp(on_road), 0.3, "rough on the dirt road the course follows")
        r = rf.rocks(self.course, {0: dict(prof[0], rock=[1.0] * len(prof[0]["rock"]))},
                     (LON0 - 0.1, LAT0 - 0.1, LON0 + 0.1, LAT0 + 0.1))
        _, ry = xy(r["lat"], r["lon"])
        self.assertTrue(len(ry) and np.all(np.abs(ry - 15.0) > 3.0 + 0.5), "rocks beside that road, not on it")

    def test_relief_on_dirt_only(self):
        xs = np.arange(200.0, 1800.0, 1.0)
        dz = self.at(xs, np.zeros_like(xs))
        self.assertGreater(np.ptp(dz), 0.4, "rough along the desert track")
        self.assertLessEqual(dz.max(), rf.CLAMP[1])
        self.assertGreaterEqual(dz.min(), rf.CLAMP[0])
        on_road = self.at(np.arange(2200.0, 2800.0, 1.0), np.zeros(600))
        self.assertTrue(np.all(on_road == 0), "never on asphalt")
        cross = self.at(np.arange(3495.0, 3506.0, 1.0), np.zeros(11))
        self.assertTrue(np.all(np.abs(cross) < 1e-9), "nor where it crosses a paved road")
        far = self.at(np.full(10, 1000.0), np.linspace(30, 300, 10))
        self.assertTrue(np.all(far == 0), "nothing away from the course")

    def test_whoops_and_washes(self):
        # along the whole desert stretch: rolling bumps ~10 m apart, and at least one wash or kicker
        xs = np.arange(0.0, 2000.0, 0.5)
        dz = self.at(xs, np.zeros_like(xs))
        f = np.abs(np.fft.rfft(dz - dz.mean()))
        freq = np.fft.rfftfreq(len(dz), 0.5)
        peak = 1.0 / freq[1:][np.argmax(f[1:])]
        self.assertTrue(8.0 < peak < 13.0 or 20.0 < peak < 28.0, f"whoops' spacing {peak:.1f} m")
        self.assertLess(dz.min(), -0.3, "a wash")

    def test_v4_dips_are_streambeds_not_holes(self):
        """Terrain 4: a wash is an eased bank down, a flat floor, an eased bank up; mostly shallow, about one per km
        (terrain 3: a bell up to 0.95 m deep, one per ~580 m)."""
        x = np.arange(-30.0, 30.0, 0.25)
        z = rf.dip(x, 0.45, 12.0, 9.0)
        self.assertAlmostEqual(float(z.min()), -0.45)
        floor = x[np.abs(z + 0.45) < 0.01]
        self.assertGreaterEqual(floor.max() - floor.min(), 11.5, "a long flat floor")
        slope = np.abs(np.diff(z) / 0.25).max()
        self.assertLess(slope, 0.45 * math.pi / (2 * 9.0) + 0.01, "eased banks")
        self.assertEqual(float(z[0]), 0.0)

        class C:
            pass
        n = 4000
        for tv, per_km_max in ((4, 1.6), (3, 3.0)):
            c = C()
            c.tv = tv
            c.lat = [LAT0] * (n * 17 + 2)
            c.lon = [LON0 + i * 1e-4 for i in range(n * 17 + 2)]
            s = np.arange(0.0, n * 170.0, 2.0)
            h = rf._bin_features(c, s, np.zeros(len(s)))
            low = h < -0.12
            starts = int(np.count_nonzero(low[1:] & ~low[:-1]))
            per_km = starts / (n * 0.17)
            self.assertLess(per_km, per_km_max, (tv, per_km))
            if tv == 4:
                self.assertGreater(per_km, 0.6)
                self.assertGreaterEqual(h.min(), -0.71, "never deeper than WASH_DEEP_M")
                runs = np.diff(np.flatnonzero(np.diff(low.astype(int)))) * 2.0
                self.assertGreater(np.median(runs[::2]), 10.0, "long low parts")

    def test_lake_stays_smooth(self):
        xs = np.arange(5300.0, 5700.0, 1.0)
        lake = self.at(xs, np.zeros_like(xs))
        desert = self.at(np.arange(600.0, 1000.0, 1.0), np.zeros(400))
        self.assertLess(np.std(lake), 0.3 * np.std(desert))

    def test_the_same_whoever_asks(self):
        # a block (a grid), a road tile (a few points), in another order, in pieces: the same heights
        gx, gy = np.meshgrid(np.arange(900.0, 1100.0, 2.0), np.arange(-20.0, 21.0, 2.0))
        whole = self.at(gx, gy)
        self.assertEqual(whole.shape, gx.shape)
        rng = np.random.default_rng(3)
        order = rng.permutation(gx.size)
        shuffled = self.at(gx.ravel()[order], gy.ravel()[order])
        self.assertTrue(np.array_equal(shuffled, whole.ravel()[order]))
        part = self.at(gx[5:7, 40:60], gy[5:7, 40:60])
        self.assertTrue(np.array_equal(part, whole[5:7, 40:60]))
        # only the windows near the points asked for: the same
        near = {k: p for k, p in self.profiles.items() if k in self.course.windows_in(
            (float(self.ll(800, 0)[1]), float(self.ll(0, -50)[0]), float(self.ll(1200, 0)[1]), float(self.ll(0, 50)[0])))}
        self.assertTrue(np.array_equal(self.at(gx, gy, near), whole))
        # a window's facts computed again (another process): the same
        again = rf.window_profile(self.course, 0, [{"w": 8.0, "ll": [[self.course.lon[i], self.course.lat[i]]
                                                                     for i in range(0, 101)]}],
                                  lambda *a: [], lambda la, lo: [0.0] * len(la), None)
        self.assertEqual(again["hw"], self.profiles[0]["hw"])
        self.assertEqual(again["rough"], self.profiles[0]["rough"])

    def test_scale(self):
        # (through terrain 4 the relief scales with the setting; terrain 5's banked corners and rutted sections are
        # chosen by it: test_v5_*)
        tv, self.course.tv = self.course.tv, 4
        try:
            xs = np.arange(200.0, 1800.0, 1.0)
            one = self.at(xs, np.zeros_like(xs))
            mild = self.at(xs, np.zeros_like(xs), scale=0.55)
            inner = np.abs(one) < 0.5
            self.assertTrue(np.allclose(mild[inner], one[inner] * 0.55))
            self.assertTrue(np.all(self.at(xs, np.zeros_like(xs), scale=0.0) == 0))
        finally:
            self.course.tv = tv

    def test_global_noise(self):
        # the noise is the place's: a point's value does not depend on what else is asked
        x = np.array([-12345678.9, 0.5, 98765.4321])
        y = np.array([3456789.0, -0.25, 1234.5])
        a = rf.fbm(x / 9.0, y / 9.0, 3)
        b = np.array([rf.fbm(np.array([u / 9.0]), np.array([v / 9.0]), 3)[0] for u, v in zip(x, y)])
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(np.all((a >= 0) & (a < 1)))
        g = np.linspace(0, 50, 2001)
        v = rf.vnoise(g, g * 0.3, 7)
        self.assertLess(np.abs(np.diff(v)).max(), 0.06, "smooth")

    def test_turn_berm_on_the_outside(self):
        ll, _ = self.ll, self.xy
        # a left curve (radius 120 m)
        pts = [tuple(map(float, ll(x, 0.0))) for x in range(0, 401, 20)]
        for a in range(1, 30):
            t = math.radians(a * 3)
            pts.append(tuple(map(float, ll(400 + 120 * math.sin(t), 120 - 120 * math.cos(t)))))
        c = cr.Course(pts)
        prof = {k: rf.window_profile(c, k, [], lambda *a: [], lambda la, lo: [0.0] * len(la), None)
                for k in range(c.nwin)}
        turns = [t for p in prof.values() for t in p["turn"]]
        self.assertGreater(max(turns), 3.0, "a left turn: positive")
        # 30 degrees into the curve: just past the edge, the outside (right) higher than the inside, on average
        t = math.radians(30)
        cx, cy = 400 + 120 * math.sin(t), 120 - 120 * math.cos(t)
        nx, ny = -math.sin(t), math.cos(t)       # (the curve's centre is to the left: +n)
        o = rf.DEFAULT_HALF_M + 0.8
        out_ = np.mean([rf.relief(c, prof, *ll(cx - nx * o + dx, cy - ny * o), 1.0) for dx in np.linspace(-4, 4, 9)])
        in_ = np.mean([rf.relief(c, prof, *ll(cx + nx * o + dx, cy + ny * o), 1.0) for dx in np.linspace(-4, 4, 9)])
        self.assertGreater(out_ - in_, 0.15, f"outside {out_:.2f}, inside {in_:.2f}")

    def test_rocks_in_the_canyon_beside_the_track(self):
        b = (LON0 - 0.1, LAT0 - 0.1, LON0 + 0.1, LAT0 + 0.1)
        r = rf.rocks(self.course, self.profiles, b)
        x, y = self.xy(r["lat"], r["lon"])
        self.assertGreater(len(x), 50)
        self.assertTrue(np.all((x > 3800) & (x < 5200)), "only where it is rocky")
        self.assertTrue(np.all(np.abs(y) > self.fact("hw", 4500) + 0.5), "never on the track")
        self.assertTrue(np.all(np.abs(y) < 10.0))
        again = rf.rocks(self.course, self.profiles, b)
        self.assertTrue(all(np.array_equal(r[k], again[k]) for k in r), "the same every time")
        # a cell's share: the rocks inside its bounds, the same ones
        half = (LON0 - 0.1, LAT0 - 0.1, float(self.ll(4500, 0)[1]), LAT0 + 0.1)
        h = rf.rocks(self.course, self.profiles, half)
        hx, _ = self.xy(h["lat"], h["lon"])
        self.assertTrue(np.all(hx < 4500.01) and len(hx) == int(np.sum(x < 4500.0)))

    def fresh(self, dangers=()):
        c = cr.Course([tuple(map(float, self.ll(x, 0.0))) for x in range(0, 6001, 50)])
        c.dangers = list(dangers)
        return c

    def test_auto_sections_vary_and_are_the_same_for_everyone(self):
        # 80 km of course: fast, mild, rough and extra stretches, each a km or more, from the place alone
        pts = [tuple(map(float, self.ll(x, 3000 * math.sin(x / 9000.0)))) for x in range(0, 80001, 200)]
        a, b = cr.Course(pts, tv=8), cr.Course(pts, tv=8)       # (terrain 8's shares; 9's: TestTerrain9)
        la, lb = rf.course_auto(a)["level"], rf.course_auto(b)["level"]
        self.assertTrue(np.array_equal(la, lb), "the same on every computer")
        share = lambda m: float(np.mean(m))                                    # noqa: E731
        self.assertGreater(share(la < 0.45), 0.03, "fast stretches")
        self.assertGreater(share((la > 0.5) & (la < 0.6)), 0.05, "mild")
        self.assertGreater(share((la > 0.9) & (la < 1.1)), 0.1, "rough")
        self.assertGreater(share(la > 1.5), 0.1, "very rough")
        self.assertLess(np.abs(np.diff(la)).max(), 0.2, "blending, not jumps")
        changes = np.count_nonzero(np.diff(np.digitize(la, [0.45, 0.8, 1.3])))
        self.assertLess(changes, len(la) * cr.STEP_M / 800.0, "sections, not flicker")

    def test_auto_relief_follows_the_sections(self):
        c = self.fresh()
        c.tv = 4                    # (terrain 5's banks and ruts are chosen by the level, not scaled by it)
        lvl = rf.course_auto(c)["level"]
        la, lo = self.ll(np.arange(0.0, 2000.0, 1.0), np.zeros(2000))
        auto = rf.relief(c, self.profiles, la, lo, 1.0, auto=True)
        plain = rf.relief(c, self.profiles, la, lo, 1.0)
        want = rf._per_sample(lvl, np.arange(0.0, 2000.0, 1.0))
        ok = (np.abs(plain) > 0.02) & (np.abs(plain) < 1.0)
        ratio = auto[ok] / plain[ok]
        clipped = (auto[ok] <= rf.CLAMP[0] + 1e-9) | (auto[ok] >= rf.CLAMP[1] - 1e-9)
        self.assertTrue(np.all(np.isclose(ratio, want[ok], atol=0.02) | clipped), "scaled by the level")
        self.assertGreater(float(want.max() - want.min()), 0.2, "(the level changes along this stretch)")

    def test_auto_danger_is_rough_with_a_hazard(self):
        c = self.fresh([1500.0])
        A = rf.course_auto(c)
        i = int(1500 / cr.STEP_M)
        self.assertGreaterEqual(A["level"][i], rf.DANGER_LEVEL - 1e-6)
        self.assertGreaterEqual(A["level"][int(1450 / cr.STEP_M)], rf.DANGER_LEVEL - 1e-6, "from before the sign")
        self.assertEqual(len(A["hazard"]), 1)
        kind = A["hazard"][0][1]
        xs = np.arange(1470.0, 1530.0, 0.5)
        la, lo = self.ll(xs, np.zeros_like(xs))
        with_ = rf.relief(c, self.profiles, la, lo, 1.0, auto=True)
        without = rf.relief(self.fresh(), self.profiles, la, lo, 1.0, auto=True)
        if kind in (0, 1):
            self.assertGreater(np.abs(with_ - without).max(), 0.5, f"a {('ditch', 'kicker')[kind]} at the danger")
        else:
            b = (LON0 - 0.1, LAT0 - 0.1, LON0 + 0.1, LAT0 + 0.1)
            r = rf.rocks(c, self.profiles, b, auto=True)
            x, _ = self.xy(r["lat"], r["lon"])
            self.assertGreater(int(np.sum((x > 1460) & (x < 1560))), 4, "a rock garden at the danger")
        # every kind comes up somewhere
        kinds = {rf.course_auto(self.fresh([float(s)]))["hazard"][0][1] for s in range(500, 2000, 50)}
        self.assertEqual(kinds, {0, 1, 2})

    def test_auto_boulder_fields(self):
        # over a long desert course: rocks on some stretches, none on others, how many from the place
        pts = [tuple(map(float, self.ll(x, 0.0))) for x in range(0, 40001, 200)]
        c = cr.Course(pts)
        profs = {}
        for k in range(c.nwin):
            a, b = c.inner(k)
            m = b - a + 1
            profs[k] = {"algo": rf.ALGO, "a": a, "b": b, "hw": [3.0] * m, "ctr": [0.0] * m, "rough": [1.0] * m,
                        "rock": [0.0] * m, "turn": [0.0] * m, "lake": [0.0] * m}
        bounds = (LON0 - 1, LAT0 - 1, LON0 + 1, LAT0 + 1)
        self.assertEqual(len(rf.rocks(c, profs, bounds)["lon"]), 0, "no rocks on the plain but with auto")
        r = rf.rocks(c, profs, bounds, auto=True)
        x, y = self.xy(r["lat"], r["lon"])
        per_km = np.bincount((x // 1000).astype(int), minlength=40)[:40]
        self.assertGreater(int(np.sum(per_km == 0)), 8, f"none on many stretches: {per_km}")
        self.assertGreater(int(per_km.max()), 40, "a boulder field somewhere")
        self.assertTrue(np.all(np.abs(y) > 3.0 + 0.6), "beside the track, never on it")
        again = rf.rocks(cr.Course(pts), profs, bounds, auto=True)
        self.assertTrue(all(np.array_equal(r[k], again[k]) for k in r), "the same for everyone")
        for p in profs.values():
            p["lake"] = [1.0] * len(p["lake"])
        self.assertEqual(len(rf.rocks(c, profs, bounds, auto=True)["lon"]), 0, "none on a lake")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_NP, "numpy")
class TestTerrain5(unittest.TestCase):
    """Terrain 5: banked corners on rough ground, rutted sections on mild or rougher ground."""

    @classmethod
    def setUpClass(cls):
        ll, xy = frame()
        cls.ll = staticmethod(ll)

        class Line:                        # 300 km of course samples (bank_weight only reads its places)
            lat = (LAT0 + np.arange(30001) * cr.STEP_M / 111000.0).tolist()
            lon = [LON0] * 30001
        cls.line = Line()
        cls.mids = (np.arange(1999) + 0.5) * rf.BANK_BIN_M          # each stretch's middle

    def share(self, turn, power, course=None):
        w = rf.bank_weight(course or self.line, self.mids, np.full(len(self.mids), turn), np.full(len(self.mids), power))
        return float(np.mean(w > 0.5)), w

    def test_banks_more_likely_the_tighter_and_rougher(self):
        rough, extra = 1.0, 1.6
        self.assertEqual(self.share(14.0, 0.0)[0], 0.0, "Flat: never")
        self.assertEqual(self.share(14.0, 0.55)[0], 0.0, "Mild: never")
        self.assertEqual(self.share(2.0, extra)[0], 0.0, "a gentle bend: never")
        self.assertEqual(self.share(0.0, extra)[0], 0.0, "a straight: never")
        tight_rough = self.share(14.0, rough)[0]
        self.assertGreater(tight_rough, 0.2)
        self.assertLess(tight_rough, 0.5, "Rough: not every tight corner")
        self.assertLess(self.share(7.0, rough)[0], tight_rough, "a looser corner: less likely")
        tight_extra = self.share(14.0, extra)[0]
        self.assertGreater(tight_extra, tight_rough, "rougher: more likely")
        self.assertLess(tight_extra, 0.97, "Extra: still not every one")
        sh = [self.share(t, extra)[0] for t in (4.0, 7.0, 10.0, 14.0)]
        self.assertEqual(sh, sorted(sh), "the chance grows with the tightness")

    def test_banks_the_same_for_everyone_and_eased(self):
        _, w = self.share(14.0, 1.2)

        class Again:
            lat, lon = list(self.line.lat), list(self.line.lon)
        _, w2 = self.share(14.0, 1.2, Again())
        self.assertTrue(np.array_equal(w, w2), "from the course's places alone")
        s = np.arange(0.0, 60000.0, 1.0)
        ws = rf.bank_weight(self.line, s, np.full(len(s), 14.0), np.full(len(s), 1.2))
        self.assertLess(np.abs(np.diff(ws)).max(), 0.02, "no bank switching on in a few metres")
        self.assertTrue(((ws > 0.9).any()) and ((ws < 0.1).any()))

    def test_bank_shape(self):
        hw, slope = 4.0, 0.2
        x = np.arange(-12.0, 12.01, 0.05)
        z = rf.bank_dz(x, hw, slope)
        self.assertAlmostEqual(float(rf.bank_dz(np.array([0.0]), hw, slope)[0]), 0.0)
        self.assertAlmostEqual(float(rf.bank_dz(np.array([hw]), hw, slope)[0]), slope * hw, "the outside edge up")
        self.assertAlmostEqual(float(rf.bank_dz(np.array([-hw]), hw, slope)[0]), -rf.BANK_INSIDE * slope * hw,
                               msg="the inside dug a little")
        self.assertLess(np.abs(np.diff(z)).max(), 0.4 * 0.05, "smooth: no step anywhere")
        far = np.abs(x) > hw + max(rf.BANK_LIP_M, rf.BANK_IN_M) + 0.01
        self.assertTrue(np.allclose(z[far], 0.0), "back to the ground past the lip and the dig")
        self.assertTrue(np.all(np.diff(z[(x >= 0) & (x <= hw)]) > 0), "tilted into the corner")

    def test_banked_corner_in_the_relief(self):
        # a 90 degree corner of 50 m radius on rough desert, then a straight: banked (when its stretch says so) on tv 5,
        # never on tv 4; the outside up, the inside down
        pts, x, y = [], 0.0, 0.0
        for _ in range(60):
            pts.append((x, y)); x += cr.STEP_M
        cx, cy, r = x, 50.0, 50.0
        for a in np.linspace(-90, 0, 9)[1:]:
            pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
        x, y = pts[-1]
        for _ in range(60):
            y += cr.STEP_M; pts.append((x, y))
        found = None
        for shift in range(0, 400):        # (move the course about till its corner's stretch banks)
            off = shift * 900.0
            c = cr.Course([tuple(map(float, self.ll(px + off, py))) for px, py in pts])

            def pieces(k):
                a, b = c.inner(k)
                return [{"w": 8.0, "ll": [[c.lon[i], c.lat[i]] for i in range(a, b + 1)]}]
            prof = {k: rf.window_profile(c, k, pieces(k), lambda *a: [], lambda la, lo: [0.0] * len(la),
                                         lambda la, lo: [0.0] * len(la)) for k in range(c.nwin)}
            facts = rf._Facts(prof)
            sc = np.arange(500.0, 800.0, 2.0)
            f = facts.at(sc)
            if rf.bank_weight(c, sc, f["turn"], f["rough"] * 1.6).max() > 0.7:
                found = c, prof, off
                break
        self.assertIsNotNone(found, "some corner banks")
        c, prof, off = found
        # across the corner's middle (45 degrees round): inside toward the centre, outside away
        a = math.radians(-45)
        ux, uy = math.cos(a), math.sin(a)
        mx, my = cx + r * ux + off, cy + r * uy
        t = np.array([-4.5, -2.0, 0.0, 2.0, 4.5])          # + outward
        la, lo = self.ll(mx + ux * t, my + uy * t)
        h5 = rf.relief(c, prof, la, lo, 1.6)
        c.tv = 4
        h4 = rf.relief(c, prof, la, lo, 1.6)
        c.tv = rf.BANKS_TV
        lift = h5 - h4                                     # (the ruts' share is small and level across: RUT_* m)
        self.assertGreater(lift[3] - lift[1], 0.4, "tilted into the corner")
        self.assertGreater(lift[4], 0.25, "the outside up")
        self.assertLess(lift[0], 0.0, "the inside dug")

    def test_rutted_sections(self):
        g = np.random.RandomState(5)
        gx, gy = g.uniform(-2e6, 2e6, 40000), g.uniform(-2e6, 2e6, 40000)

        def share(hw, power, road=0.0):
            return float(np.mean(rf.rut_weight(gx, gy, np.full(len(gx), hw), power, road) > 0.5))
        self.assertEqual(share(3.0, 0.0), 0.0, "Flat: none")
        mild = share(3.0, 0.55)
        self.assertGreater(mild, 0.03, "Mild: some")
        self.assertLess(share(4.5, 1.0), share(2.0, 1.0), "narrower: more")
        self.assertLess(mild, share(3.0, 1.6), "rougher: more")
        self.assertLess(share(3.0, 1.0, 1.0), share(3.0, 1.0), "a graded road: fewer")
        self.assertLess(share(2.0, 1.6), 0.6, "sections, not everywhere")

    def test_ruts_only_from_terrain_5(self):
        tr = TestRelief
        TestRelief.setUpClass()
        c, prof = tr.course, tr.profiles
        xs = np.arange(200.0, 1800.0, 1.0)
        la, lo = tr.ll(xs, np.zeros_like(xs))
        c.tv = 4
        self.assertFalse(rf.ruts_at(c, prof, la, lo).any(), "terrain 4: none")
        self.assertTrue(np.array_equal(rf.relief(c, prof, la, lo), rf.relief(c, prof, la, lo)))
        h4 = rf.relief(c, prof, la, lo)
        c.tv = 5
        w = rf.ruts_at(c, prof, la, lo)
        h5 = rf.relief(c, prof, la, lo)
        self.assertTrue(np.array_equal(h4[w == 0], h5[w == 0]), "a straight track: only the ruts change it")
        self.assertFalse(rf.ruts_at(c, prof, la, lo, scale=0.0).any(), "Flat: none")


@unittest.skipUnless(HAVE_NP, "numpy")
class TestTerrain6(unittest.TestCase):
    """Terrain 6: no shape narrower than the game's 2 m lattice can hold (no saw teeth, no lone pyramids), the
    heights much as before."""

    @classmethod
    def setUpClass(cls):
        ll, _xy = frame()
        cls.ll = staticmethod(ll)
        pts, x, y, hd = [], 0.0, 0.0, 0.0
        for i in range(260):                # a straight, a tight right, a sweeper, a tight left
            turn = -10.0 if 60 <= i < 69 else 3.0 if 100 <= i < 125 else 11.0 if 160 <= i < 170 else 0.0
            hd += math.radians(turn)
            x += 10 * math.cos(hd)
            y += 10 * math.sin(hd)
            pts.append((x, y))
        cls.pts = pts

    def field(self, tv, box, scale=1.6):
        c = cr.Course([tuple(map(float, self.ll(px, py))) for px, py in self.pts], 1.0, "T6", tv)

        def pieces(k):
            a, b = c.inner(k)
            return [{"w": 7.0, "ll": [[c.lon[i], c.lat[i]] for i in range(a, b + 1)]}]
        prof = {k: rf.window_profile(c, k, pieces(k), lambda *a: [], lambda la, lo: [0.0] * len(la),
                                     lambda la, lo: [0.0] * len(la)) for k in range(c.nwin)}
        gx, gy = np.meshgrid(np.arange(box[0], box[1], 2.0), np.arange(box[2], box[3], 2.0))   # (the game's lattice)
        la, lo = self.ll(gx, gy)
        return rf.relief(c, prof, la, lo, scale)

    def test_no_spikes_on_the_lattice(self):
        for box in ((100, 400, -40, 40), (540, 700, -160, 20), (1100, 1260, -700, -470)):
            h5, h6 = self.field(5, box), self.field(6, box)
            k5 = max(np.abs(np.diff(h5, 2, axis=0)).max(), np.abs(np.diff(h5, 2, axis=1)).max())
            k6 = max(np.abs(np.diff(h6, 2, axis=0)).max(), np.abs(np.diff(h6, 2, axis=1)).max())
            self.assertLess(k6, 0.8, f"{box}: no point stands out of its neighbours by much ({k6:.2f} m)")
            self.assertLess(k6, 0.6 * k5, f"{box}: far softer than terrain 5 ({k6:.2f} against {k5:.2f} m)")
            self.assertGreater(np.ptp(h6), 0.7 * np.ptp(h5), f"{box}: as rough as before, only rounder")

    def test_the_banked_bowl_is_smooth(self):
        hw, slope = 4.0, 0.2
        x = np.arange(-15.0, 15.0, 0.01)
        z = rf.bank_dz_v6(x, hw, slope)
        g = np.diff(z) / 0.01
        self.assertLess(np.abs(np.diff(g)).max(), 0.01, "no crease: the slope never jumps")
        self.assertAlmostEqual(z.max(), slope * hw, places=3)
        self.assertGreater(x[np.argmax(z)], hw, "the lip's crest past the outer edge")
        self.assertAlmostEqual(z.min(), -rf.BANK_INSIDE * slope * hw, places=3)
        self.assertTrue(np.all(z[(x < -hw - rf.BANK_V6[0]) | (x > hw + rf.BANK_V6[2] + rf.BANK_V6[3])] == 0))

    def test_older_versions_unchanged(self):
        self.assertEqual(rf.SMOOTH_TV, 6)
        h5 = self.field(5, (540, 700, -160, 20))
        k5 = max(np.abs(np.diff(h5, 2, axis=0)).max(), np.abs(np.diff(h5, 2, axis=1)).max())
        self.assertGreater(k5, 1.0, "terrain 5's ground as it always was (the golden test holds it exactly)")


class TestTerrain9(unittest.TestCase):
    """Terrain 9, Baja only (the user, 2026-11-06): rough sections rarer, the rougher the rarer (mild ones more common);
    on a mapped dirt road the course follows (BeamNG.Earth 1.8.2 wears it too) the part over Mild softened, but not at
    the DANGER waypoints nor on the course's own track."""

    @classmethod
    def setUpClass(cls):
        ll, _xy = frame()
        cls.ll = staticmethod(ll)
        pts = [tuple(map(float, ll(x, 3000 * math.sin(x / 9000.0)))) for x in range(0, 400001, 200)]
        cls.pts = pts

    def shares(self, tv):
        c = cr.Course(self.pts, tv=tv)
        lv = rf.course_auto(c)["level"]
        return lv, [float(np.mean(m)) for m in (lv < 0.45, (lv >= 0.45) & (lv < 0.775), (lv >= 0.775) & (lv < 1.3),
                                                 lv >= 1.3)]

    def test_rough_sections_rarer_the_rougher_the_rarer(self):
        _l8, (f8, m8, r8, x8) = self.shares(8)
        lv, (f9, m9, r9, x9) = self.shares(9)
        self.assertGreater(m9, m8, "more mild")
        self.assertGreater(f9, f8, "more fast")
        self.assertLess(r9, r8, "fewer rough")
        self.assertLess(x9, x8, "fewer extra rough")
        self.assertLess(x9 / x8, r9 / r8, "the rougher, the rarer")
        self.assertGreater(m9, max(f9, r9, x9), "mild the commonest")
        self.assertTrue(0.05 < x9 < 0.2 and 0.18 < r9 < 0.38, (f9, m9, r9, x9))
        self.assertTrue(np.array_equal(lv, rf.course_auto(cr.Course(self.pts, tv=9))["level"]), "the same everywhere")

    def test_softer_on_a_mapped_dirt_road_but_not_at_a_danger_sign(self):
        c = cr.Course([tuple(map(float, self.ll(x, 0.0))) for x in range(0, 6001, 50)], tv=9)
        c.dangers = [3000.0]
        A = rf.course_auto(c)
        n = len(A["level"])
        A["level"][:] = 1.6                         # (every level by hand: the rule alone)
        A["level"][:20] = 1.0
        A["level"][20:40] = 0.55
        A["level"][40:60] = 0.35
        s = np.arange(n) * cr.STEP_M
        own = rf.auto_level(c, A, s, {"road": np.zeros(n)})
        road = rf.auto_level(c, A, s, {"road": np.ones(n)})
        self.assertTrue(np.allclose(own, A["level"]), "the course's own track: as before")
        self.assertAlmostEqual(float(road[10]), 0.55 + 0.45 * rf.ROAD_EXCESS_V9)
        self.assertAlmostEqual(float(road[100]), 0.55 + 1.05 * rf.ROAD_EXCESS_V9)
        self.assertTrue(np.allclose(road[20:60], A["level"][20:60]), "mild and fast: as before")
        i = int(3000 / cr.STEP_M)
        self.assertAlmostEqual(float(road[i]), float(A["level"][i]), msg="at the DANGER waypoint: full")
        half = rf.auto_level(c, A, s, {"road": np.full(n, 0.5)})
        self.assertTrue(np.all((half[100:110] < own[100:110]) & (half[100:110] > road[100:110])), "eased at its ends")
        c8 = cr.Course([tuple(map(float, self.ll(x, 0.0))) for x in range(0, 6001, 50)], tv=8)
        A8 = rf.course_auto(c8)
        s8 = np.arange(len(A8["level"])) * cr.STEP_M
        self.assertTrue(np.array_equal(rf.auto_level(c8, A8, s8, {"road": np.ones(len(s8))}), A8["level"]),
                        "terrain 8 and older: as they were")


class TestTerrain10(unittest.TestCase):
    """Terrain 10 (the user, 2026-11-08): BeamNG.Earth's wear is kept off the mapped dirt roads the course follows
    (earthpatch.followed_rows), so 9's softening there is gone; 9's section shares stay."""

    def test_no_softening_shares_kept(self):
        ll, _xy = frame()
        pts = [tuple(map(float, ll(x, 3000 * math.sin(x / 9000.0)))) for x in range(0, 100001, 200)]
        c9, c10 = cr.Course(pts, tv=9), cr.Course(pts, tv=10)
        A9, A10 = rf.course_auto(c9), rf.course_auto(c10)
        self.assertTrue(np.array_equal(A9["level"], A10["level"]), "9's shares")
        s = np.arange(len(A10["level"])) * cr.STEP_M
        road = {"road": np.ones(len(s))}
        self.assertTrue(np.array_equal(rf.auto_level(c10, A10, s, road), A10["level"]), "no softening on a road")
        self.assertFalse(np.array_equal(rf.auto_level(c9, A9, s, road), A9["level"]), "9 still softens")
