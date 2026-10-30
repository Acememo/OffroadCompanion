"""How urban a course is along it (gpsd/urban.py): towns from OpenStreetMap, 0 in open country .. 1 in a city."""
import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(HERE))

from gpsd import urban  # noqa: E402

ENSENADA = (31.866, -116.596)       # a city (~440 000 people)
OJOS = (31.896, -116.267)           # Ojos Negros, a village (~1 000)
ANSWER = {"elements": [
    {"type": "node", "id": 1, "lat": ENSENADA[0], "lon": ENSENADA[1],
     "tags": {"place": "city", "name": "Ensenada", "population": "443,807"}},
    {"type": "node", "id": 2, "lat": OJOS[0], "lon": OJOS[1], "tags": {"place": "village", "name": "Ojos Negros"}},
    {"type": "node", "id": 3, "lat": 31.0, "lon": -116.0, "tags": {"place": "hamlet"}},          # (not counted)
    {"type": "node", "id": 1, "lat": ENSENADA[0], "lon": ENSENADA[1], "tags": {"place": "city"}},  # (once)
]}


def east(p, m):
    import math
    return p[0], p[1] + m / (111320.0 * math.cos(math.radians(p[0])))


class TestValues(unittest.TestCase):
    def setUp(self):
        self.places = urban.Places(urban.parse(ANSWER))

    def test_parse(self):
        got = urban.parse(ANSWER)
        self.assertEqual(len(got), 2, "cities, towns and villages, each once")
        self.assertEqual(got[0][2:], ("city", 443807.0))
        self.assertIsNone(got[1][3], "no population: None")

    def test_near_and_far(self):
        v = self.places.value
        self.assertGreater(v(*ENSENADA), 0.95, "in the city")
        self.assertGreater(v(*east(ENSENADA, 8000)), 0.5, "8 km out of a big city: still busy")
        self.assertEqual(v(*east(ENSENADA, 60000)), 0.0, "60 km out: open country")
        self.assertGreater(v(*OJOS), 0.3, "a village")
        self.assertLess(v(*OJOS), v(*ENSENADA), "less than a city")
        self.assertEqual(v(*east(OJOS, 5000)), 0.0, "5 km from a village: nothing")
        self.assertGreater(v(*east(ENSENADA, 3000)), v(*east(ENSENADA, 10000)), "falls off away from it")

    def test_population_widens_the_reach(self):
        small = urban.reach("city", 50000.0)[1]
        big = urban.reach("city", 1500000.0)[1]
        self.assertLess(small, big)
        self.assertEqual(urban.reach("town", None), (0.7, 6000.0))

    def test_boxes_follow_the_course(self):
        lats = [31.0 + i * 0.0001 for i in range(12000)]
        lons = [-116.0] * 12000
        bx = urban.boxes(lats, lons)
        self.assertEqual(len(bx), 3, "a box every CHUNK_N samples")
        self.assertLess(bx[0][0], 31.0 - 0.2)
        self.assertIn("(city|town|village)", urban.query(bx))


class TestFetch(unittest.TestCase):
    def test_pending_then_values(self):
        u = urban.Urban(fetcher=None)
        lats = [ENSENADA[0]] * 300
        lons = [ENSENADA[1] + i * 0.001 for i in range(300)]
        gate = []
        with mock.patch.object(urban.overpass, "run", lambda f, q, ttl=0, what="": gate.append(q) or ANSWER):
            st = u.state("c1", lats, lons)
            self.assertIn(st, ("pending", "ok"))
            for _ in range(100):
                if u.state("c1", lats, lons) == "ok":
                    break
                time.sleep(0.01)
        self.assertEqual(u.state("c1", lats, lons), "ok")
        vals = u.values(lats, lons, 0, 2, 10.0)
        self.assertEqual(len(vals), 3)
        self.assertGreater(vals[0], 0.9)
        self.assertEqual(len(gate), 1, "fetched once for the course")

    def test_failed_is_open_country(self):
        u = urban.Urban(fetcher=None)

        def boom(*a, **k):
            raise urban.overpass.FetchError("down")
        with mock.patch.object(urban.overpass, "run", boom):
            u.state("c2", [31.0], [-116.0])
            for _ in range(100):
                if u.state("c2", [31.0], [-116.0]) != "pending":
                    break
                time.sleep(0.01)
        self.assertEqual(u.state("c2", [31.0], [-116.0]), "failed")
        self.assertEqual(u.values([31.0], [-116.0], 0, 1, 10.0), [0.0, 0.0])

    def test_while_pending(self):
        u = urban.Urban(fetcher=None)
        u.key, u.st = "c3", "pending"
        self.assertIsNone(u.values([31.0], [-116.0], 0, 1, 10.0))


if __name__ == "__main__":
    unittest.main()
