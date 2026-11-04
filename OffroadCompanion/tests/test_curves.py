"""Terrain 8 (courseroads.CURVES_TV): the course's corners rounded to arcs within CURVE_DEV_M of the course file's line,
the samples keeping their distance along it (the game counts along the file's line: bend tells it where the track
went), and wider tracks."""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

from gpsd import courseroads as cr  # noqa: E402

LAT0, LON0 = 31.0, -115.5
PL = cr.Plane(LAT0, LON0)


def course(xy, tv=None):
    return cr.Course([PL.ll(x, y) for x, y in xy], 1.0, "T", tv)


def heading_steps(c):
    """Degrees the line turns at each sample."""
    xy = [PL.xy(a, b) for a, b in zip(c.lat, c.lon)]
    hd = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(xy, xy[1:])]
    return [abs((math.degrees(b - a) + 180) % 360 - 180) for a, b in zip(hd, hd[1:])], xy


def dist_to_line(p, line):
    best = 1e18
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        best = min(best, math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy))
    return best


class TestRoundedCorners(unittest.TestCase):
    def test_a_right_angle_becomes_an_arc(self):
        line = [(0, 0), (500, 0), (500, 500)]
        c, old = course(line), course(line, 7)
        self.assertEqual(c.n, old.n, "the same samples, the same distances along the course")
        steps, xy = heading_steps(c)
        old_steps, _ = heading_steps(old)
        self.assertGreater(max(old_steps), 80, "terrain 7: one sharp turn at the point")
        self.assertLess(max(steps), 40, "terrain 8: spread over the arc")
        self.assertAlmostEqual(sum(steps), 90.0, delta=2.0)
        dev = max(dist_to_line(p, line) for p in xy)
        self.assertLessEqual(dev, cr.CURVE_DEV_M + 0.01, "never far from the course's own line")
        self.assertGreater(dev, 4.0, "but really rounded")

    def test_a_gentle_bend_sweeps(self):
        a = math.radians(30)
        line = [(0, 0), (400, 0), (400 + 400 * math.cos(a), 400 * math.sin(a))]
        steps, xy = heading_steps(course(line))
        self.assertLess(max(steps), 5.0, "a long sweeper, no kink")
        self.assertLessEqual(max(dist_to_line(p, line) for p in xy), cr.CURVE_DEV_M)

    def test_bend_is_left_of_the_files_line(self):
        c = course([(0, 0), (500, 0), (500, 500)])            # a left turn
        self.assertTrue(all(b >= 0 for b in c.bend) and max(c.bend) > 1.0, "inside a left turn: to the left")
        c = course([(0, 0), (500, 0), (500, -500)])           # a right turn
        self.assertTrue(all(b <= 0 for b in c.bend) and min(c.bend) < -1.0)
        for b, (la, lo), (la0, lo0) in zip(c.bend, zip(c.lat, c.lon), zip(*cr.resample(
                [PL.ll(0, 0), PL.ll(500, 0), PL.ll(500, -500)]))):
            if b == 0.0:
                self.assertEqual((la, lo), (la0, lo0), "away from the corner: exactly the file's line")

    def test_a_recorded_drive_stays_as_it_is(self):
        # a GPS recording every 5 m round a 60 m radius bend: already smooth
        pts = [(60 * math.sin(t / 60.0), 60 - 60 * math.cos(t / 60.0)) for t in range(0, 180, 5)]
        c, old = course(pts), course(pts, 7)
        moved = max(math.hypot(*(lambda p, q: (p[0] - q[0], p[1] - q[1]))(PL.xy(a, b), PL.xy(e, f)))
                    for a, b, e, f in zip(c.lat, c.lon, old.lat, old.lon))
        self.assertLess(moved, 0.5)

    def test_a_hairpin_keeps_its_point(self):
        # (a fillet round a hairpin would cut off its tip, the course's own turn: the point stays, only eased)
        line = [(0, 0), (300, 0), (0, 20)]
        steps, xy = heading_steps(course(line))
        self.assertLessEqual(max(dist_to_line(p, line) for p in xy), cr.CURVE_DEV_M + 0.01)
        self.assertGreater(max(steps), 60, "still a hairpin")
        self.assertGreater(max(p[0] for p in xy), 285.0, "its tip where the course turns")

    def test_older_versions_unchanged(self):
        line = [(0, 0), (500, 0), (500, 500)]
        c = course(line, 7)
        self.assertEqual((c.lat, c.lon), tuple(cr.resample([PL.ll(x, y) for x, y in line])))
        self.assertFalse(any(c.bend))


class TestWidths(unittest.TestCase):
    def test_wider_tracks(self):
        for room in (4, 8, 12, 16, 20, 30):
            w7, w8 = cr.widths([room] * 20, 1.0, 7)[10], cr.widths([room] * 20, 1.0, 8)[10]
            self.assertGreaterEqual(w8, w7)
            self.assertLessEqual(w8 / 2.0, max(room / 2.0, cr.WIDTH_MIN_V8 / 2.0), "never wider than the room")
        self.assertEqual(cr.widths([4] * 20, 1.0, 8)[10], cr.WIDTH_MIN_V8, "a ledge: still narrow")
        self.assertEqual(cr.widths([12] * 20, 1.0, 8)[10], 6.5, "a little relief: about two lanes")
        self.assertEqual(cr.widths([22] * 20, 1.0, 8)[10], cr.WIDTH_MAX_V8)


if __name__ == "__main__":
    unittest.main()
