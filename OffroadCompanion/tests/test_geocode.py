"""The app's search (gpsd/geocode.py): coordinates, Photon, Nominatim only when submitted, errors."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gpsd import geocode  # noqa: E402
from gpsd.fetch import FetchError  # noqa: E402

PHOTON = {"features": [
    {"geometry": {"coordinates": [-117.1951, 32.8326]},
     "properties": {"name": "Clairemont Drive", "city": "San Diego", "state": "California",
                    "country": "United States", "osm_value": "residential"}},
    {"geometry": {"coordinates": [-117.2, 32.83]}, "properties": {"housenumber": "4310", "street": "Clairemont Drive",
                                                               "city": "San Diego", "country": "United States"}}]}
NOMINATIM = [{"lat": "32.8326", "lon": "-117.1951", "name": "Clairemont Drive", "type": "residential",
              "display_name": "Clairemont Drive, San Diego, California, United States",
              "address": {"road": "Clairemont Drive", "city": "San Diego", "state": "California",
                          "country": "United States"}}]


class R:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Net:
    def __init__(self, photon=PHOTON, nominatim=NOMINATIM):
        self.photon, self.nominatim, self.calls = photon, nominatim, []

    def get(self, url, ttl=None, timeout=None, **kw):
        self.calls.append(url)
        v = self.photon if "photon" in url else self.nominatim
        if isinstance(v, Exception):
            raise v
        return R(json.loads(json.dumps(v)))


class TestGeocode(unittest.TestCase):
    def test_coordinates(self):
        self.assertEqual(geocode.parse_latlon("31.8667, -116.6"), (31.8667, -116.6))
        self.assertEqual(geocode.parse_latlon("32.83 N 117.19 W"), (32.83, -117.19))
        self.assertIsNone(geocode.parse_latlon("clairmont drive"))
        self.assertIsNone(geocode.parse_latlon("95, 10"))
        net = Net()
        r = geocode.search(net, "32.8326, -117.1951")
        self.assertEqual((r["results"][0]["lat"], r["results"][0]["lon"]), (32.8326, -117.1951))
        self.assertEqual(net.calls, [], "no network for coordinates")

    def test_photon_while_typing(self):
        net = Net()
        r = geocode.search(net, "clairmont drive san diego", 31.86, -116.6, "en")
        self.assertEqual(r["source"], "photon")
        self.assertEqual(r["results"][0]["name"], "Clairemont Drive")
        self.assertEqual(r["results"][0]["detail"], "San Diego, California, United States")
        self.assertEqual(r["results"][1]["name"], "4310 Clairemont Drive")
        self.assertIn("lat=31.86", net.calls[0])
        self.assertEqual(len(net.calls), 1)

    def test_photon_down_while_typing_never_asks_nominatim(self):
        net = Net(photon=FetchError("cannot reach photon.komoot.io: timed out"))
        r = geocode.search(net, "clairmont drive", submitted=False)
        self.assertTrue(r["error"] and r["retry"])
        self.assertFalse([u for u in net.calls if "nominatim" in u], "no autocomplete on Nominatim (its policy)")

    def test_submitted_falls_back_to_nominatim(self):
        net = Net(photon=FetchError("cannot reach photon.komoot.io: timed out"))
        r = geocode.search(net, "clairmont drive san diego", 31.86, -116.6, "es", submitted=True)
        self.assertEqual(r["source"], "nominatim")
        self.assertEqual(r["results"][0]["name"], "Clairemont Drive")
        self.assertIn("accept-language=es", net.calls[-1])
        # nothing found on Photon: Nominatim tried too when submitted
        net = Net(photon={"features": []})
        self.assertEqual(geocode.search(net, "some place", submitted=True)["source"], "nominatim")
        self.assertEqual(geocode.search(net, "some place", submitted=False)["results"], [])

    def test_both_down(self):
        net = Net(photon=FetchError("HTTP 503"), nominatim=FetchError("HTTP 429"))
        r = geocode.search(net, "clairmont drive", submitted=True)
        self.assertEqual(r["results"], [])
        self.assertIn("Photon", r["error"])
        self.assertIn("Nominatim", r["error"])

    def test_short(self):
        self.assertEqual(geocode.search(Net(), "ab")["results"], [])


if __name__ == "__main__":
    unittest.main()
