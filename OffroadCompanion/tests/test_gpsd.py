import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fixtures as fx  # noqa: E402
from gpsd import geo, protocol, routing, trackparse  # noqa: E402
from gpsd.fetch import FetchError, Response  # noqa: E402
from gpsd.sources import files, osm, racemx, score  # noqa: E402


class FakeFetcher:
    """url substring -> bytes | dict | Exception."""

    def __init__(self, routes):
        self.routes, self.calls, self.forgot = routes, [], []

    def forget(self, url, data=None):
        self.forgot.append(url)

    def get(self, url, ttl=None, data=None, accept=None, timeout=None, headers=None):
        self.calls.append((url, data))
        for k, v in self.routes.items():
            if k in url:
                if callable(v):
                    v = v(headers or {})
                if isinstance(v, Exception):
                    raise v
                if isinstance(v, (dict, list)):
                    v = json.dumps(v)
                if isinstance(v, str):
                    v = v.encode("utf-8")
                return Response(v, url, "text/html" if v.lstrip()[:1] == b"<" and b"<html" in v[:200] else "")
        raise FetchError("HTTP 404 from test", 404)


class TestClassify(unittest.TestCase):
    def test_score_names(self):
        c = trackparse.classify
        self.assertEqual(c("RM 105"), ("racemile", {"rm": 105.0}))
        self.assertEqual(c("VCP 181A")[0], "vcp")
        self.assertEqual(c("CHECK 1")[0], "checkpoint")
        self.assertEqual(c("CP 3")[0], "checkpoint")
        self.assertEqual(c("END SZ01"), ("speed_end", {"zone": 1}))
        self.assertEqual(c("SZ01 60"), ("speed_start", {"zone": 1, "limit": 60}))
        self.assertEqual(c("SZ 3 - 35 MPH")[1]["limit"], 56)
        self.assertEqual(c("DANGER 3-15")[0], "danger")
        self.assertEqual(c("X", "Skull and Crossbones")[0], "danger")
        self.assertEqual(c("BEGIN PRE-RUN")[0], "place")
        self.assertEqual(c("START")[0], "start")
        self.assertEqual(c("A. ENSENADA")[0], "place")
        self.assertEqual(c("CERRO COLORADO")[0], "place")


class TestParse(unittest.TestCase):
    def test_gpx_with_track(self):
        data, pts = fx.score_gpx()
        t = trackparse.parse(data, "26B5H.GPX")
        self.assertEqual(t["kind"], "course")
        self.assertFalse(t["approximate"])
        self.assertAlmostEqual(t["length"], geo.cumulative(pts)[-1], delta=30)
        kinds = {w["name"]: w for w in t["waypoints"]}
        self.assertLess(kinds["VCP 181A"]["off"], 2)
        self.assertGreater(kinds["A. ENSENADA"]["off"], 1500)
        # sorted along the course
        ss = [w["s"] for w in t["waypoints"]]
        self.assertEqual(ss, sorted(ss))
        # speed zone paired, the lone END stays a marker
        self.assertEqual(len(t["zones"]), 1)
        z = t["zones"][0]
        self.assertEqual(z["limit"], 60)
        self.assertAlmostEqual(z["s1"] - z["s0"], 500, delta=20)
        # race mile anchors kept in order
        self.assertEqual([r[1] for r in t["rm"]], [1, 2, 3, 4, 5])

    def test_gpx_waypoints_only_builds_rough_line(self):
        data, _ = fx.score_gpx(with_track=False)
        t = trackparse.parse(data, "x.gpx")
        self.assertTrue(t["approximate"])
        self.assertEqual(t["kind"], "course")
        self.assertEqual(len(t["points"]), 5)            # RM 1..5

    def test_kml_pieces_chain(self):
        data, pts = fx.kml_pieces()
        t = trackparse.parse(data, "x.kml")
        self.assertAlmostEqual(t["length"], geo.cumulative(pts)[-1], delta=60)
        # direction: starts at the first piece's start
        self.assertAlmostEqual(t["points"][0][0], pts[0][0], places=5)
        self.assertEqual(t["name"], "26B5H-COMPLETE SPTM-0604.kml")
        self.assertEqual({w["kind"] for w in t["waypoints"]}, {"vcp", "racemile"})

    def test_kmz(self):
        data, _ = fx.kml_pieces()
        t = trackparse.parse(fx.kmz(data), "x.kmz")
        self.assertGreater(len(t["points"]), 10)

    def test_geojson(self):
        pts = fx.line(30)
        gj = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "Lap"},
             "geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in pts]}},
            {"type": "Feature", "properties": {"name": "CP 1"},
             "geometry": {"type": "Point", "coordinates": [pts[10][1], pts[10][0]]}}]}
        t = trackparse.parse(json.dumps(gj).encode(), "lap.geojson")
        self.assertEqual(t["waypoints"][0]["kind"], "checkpoint")

    def test_bad(self):
        with self.assertRaises(trackparse.TrackError):
            trackparse.parse(b"<html><body>nope</body></html>", "x")
        with self.assertRaises(trackparse.TrackError):
            trackparse.parse(b"", "x")

    def test_self_crossing_rm_snaps_to_right_pass(self):
        # an out-and-back: RM 3 lies where the line passes twice; it must snap to the later pass
        out = fx.line(100, 50.0, curve=False)
        back = [(la + 0.00002, lo) for la, lo in out[::-1]]
        pts = out + back[1:]
        wps = [{"name": "RM 1", "lat": out[32][0], "lon": out[32][1]},
               {"name": "RM 4", "lat": out[29][0], "lon": out[29][1]}]   # ~4.8 km in: on the way back
        t = trackparse.from_points("ob", pts, wps)
        rm4 = next(w for w in t["waypoints"] if w["name"] == "RM 4")
        self.assertGreater(rm4["s"], 6000)


class TestRouting(unittest.TestCase):
    def test_parse_steps(self):
        data, pts = fx.osrm_answer()
        r = routing.parse(data, "en")
        self.assertEqual(len(r["steps"]), 4)
        self.assertEqual(r["steps"][0]["text"], "Head east on Calle Primera")
        self.assertEqual(r["steps"][1]["text"], "Turn right onto Avenida Reforma (MEX 1)")
        self.assertEqual(r["steps"][2]["text"], "At the roundabout take exit 2")
        self.assertEqual(r["steps"][3]["text"], "Your destination is on the left")
        self.assertEqual(r["steps"][1]["icon"], "right")
        s = [st["s"] for st in r["steps"]]
        self.assertEqual(s, sorted(s))
        self.assertAlmostEqual(r["steps"][1]["s"], geo.cumulative(pts)[30], delta=5)

    def test_spanish(self):
        data, _ = fx.osrm_answer()
        r = routing.parse(data, "es")
        self.assertEqual(r["steps"][1]["text"], "Gira a la derecha hacia Avenida Reforma (MEX 1)")
        self.assertEqual(r["steps"][0]["text"], "Dirígete al este por Calle Primera")

    def test_plan_retries_without_bearing(self):
        data, _ = fx.osrm_answer()
        calls = []

        class F:
            def get(self, url, ttl=None, data_=None, accept=None):
                calls.append(url)
                if "bearings" in url:
                    raise FetchError("HTTP 400", 400)
                return Response(json.dumps(data).encode(), url)
        r = routing.plan(F(), 31.8, -116.6, 31.9, -116.5, bearing=90)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(r["steps"]), 4)


class TestSources(unittest.TestCase):
    def test_osm_circuits(self):
        cs = osm.circuits(fx.overpass_answer())
        self.assertEqual(len(cs), 2)
        lap = cs[0]
        self.assertTrue(lap["closed"])
        self.assertEqual(lap["name"], "Autódromo Hermanos Rodríguez")
        self.assertGreater(lap["length"], 3000)

    def test_osm_areas_shared(self):
        """Spots a little apart ask the same area (one cached answer for the list, the course, the pre-load)."""
        self.assertEqual(osm.query(32.531, -116.981, 25000), osm.query(32.548, -116.99, 25000))
        self.assertNotEqual(osm.query(32.512, -116.981, 25000), osm.query(32.512, -116.981, 75000))
        f = FakeFetcher({"overpass": fx.overpass_answer()})
        osm.preload(f, 19.40, -99.09)
        self.assertEqual(len(f.calls), 1)

    def test_osm_list_and_get(self):
        f = FakeFetcher({"overpass": fx.overpass_answer()})
        res = osm.list_items(f, {"lat": 19.40, "lon": -99.09, "radius": 25000})
        self.assertEqual(len(res["items"]), 2)
        t = osm.get(f, res["items"][0]["id"], {})
        self.assertEqual(t["kind"], "circuit")
        self.assertTrue(t["closed"])
        self.assertEqual(t["waypoints"][0]["kind"], "finish")         # "Start / Finish"

    def test_racemx_baja_order(self):
        pts = racemx.baja_course_points(fx.RACEMX_MAP_HTML)
        self.assertEqual([p[0] for p in pts], ["San José del Cabo, Avenida Centenario", "Cabo Pulmo", "Los Barriles"])
        self.assertAlmostEqual(pts[1][1], 23.4454)
        f = FakeFetcher({"spectator-map": fx.RACEMX_MAP_HTML, "venues.json": fx.VENUES_JSON,
                         "overpass": fx.overpass_answer()})
        res = racemx.list_items(f, {"lat": 31.8, "lon": -116.6})
        ids = [i["id"] for i in res["items"]]
        self.assertIn("baja1000-order", ids)
        self.assertIn("venue:autodromo-hermanos-rodriguez", ids)
        t = racemx.get(f, "baja1000-order", {})
        self.assertEqual(t["kind"], "waypoints")
        self.assertEqual(len(t["waypoints"]), 4)                       # loop closed by the finish
        self.assertEqual(t["waypoints"][-1]["kind"], "finish")
        c = racemx.get(f, "venue:autodromo-hermanos-rodriguez", {})
        self.assertEqual(c["kind"], "circuit")
        e = racemx.get(f, "venue:ensenada-score-baja-start-finish", {})
        self.assertEqual(e["kind"], "waypoints")
        # OpenStreetMap's servers down: the venue itself (to drive to), and a note; not an error (the user's Tulum)
        from gpsd import overpass
        overpass.reset()
        down = FakeFetcher({"spectator-map": fx.RACEMX_MAP_HTML, "venues.json": fx.VENUES_JSON,
                            "overpass": FetchError("HTTP 502 from overpass-api.de", 502)})
        old = overpass.PASSES
        overpass.PASSES = ((25, 0.0), (60, 0.0))
        try:
            d = racemx.get(down, "venue:autodromo-hermanos-rodriguez", {})
        finally:
            overpass.PASSES = old
        self.assertEqual(d["kind"], "waypoints")
        self.assertIn("OpenStreetMap", d.get("note", ""))

    def test_score_listing_fallback_pages(self):
        gpx, _ = fx.score_gpx()
        f = FakeFetcher({"wp-json": FetchError("HTTP 404", 404), "?s=gps": "<html></html>",
                         "final-full-course-gps-files": fx.SCORE_PAGE_HTML,
                         "gps-files-2021-baja-1000": fx.SCORE_2021_HTML, "59th-baja": "<html></html>",
                         "course-map-2026": "<html></html>", "PROC-0604.GPX": gpx})
        res = score.list_items(f, {})
        names = sorted(i["name"] for i in res["items"])
        self.assertEqual(len(res["items"]), 3, names)            # Pro, Sportsman (GPX preferred), 2021 full course
        self.assertTrue(all(i["detail"].startswith("GPX") for i in res["items"]))
        self.assertIn("GPS Files 2021 Baja 1000 - Full Course", names)
        pro = next(i for i in res["items"] if "PROC" in i["name"])
        t = score.get(f, pro["id"], {})
        self.assertEqual(t["source"], "score")

    def test_score_file_answered_with_a_web_page(self):
        """SCORE's site answers a file it replaced with a web page (the user, 2026-10-26: "not a valid GPX/KML file
        (mismatched tag: line 93, column 2)"): the file of the same name the page links is taken, the page is not kept;
        with none, a browser's second try; else the listing is refreshed and the player told why."""
        gpx, _ = fx.score_gpx()
        ref = "https://score-raceinfo.com/wp-content/uploads/2026/10/26B10-PRO.gpx"
        page = ("<!DOCTYPE html><html><head><title>26B10-PRO</title><link rel='stylesheet' href='x.css'></head><body>"
                "<a href='https://score-raceinfo.com/wp-content/uploads/2026/10/26B10-PRO-1.kml'>other</a>"
                "<a href='https://score-raceinfo.com/wp-content/uploads/2026/11/26B10-PRO.gpx'>26B10-PRO</a>"
                "</body></html>")
        self.assertTrue(trackparse.looks_like_html(page.encode()))
        self.assertFalse(trackparse.looks_like_html(gpx))
        with self.assertRaises(trackparse.WebPageError):
            trackparse.parse(page.encode(), "26B10-PRO.gpx")
        f = FakeFetcher({"2026/10/26B10-PRO.gpx": page, "2026/11/26B10-PRO.gpx": gpx})
        t = score.get(f, ref, {})
        self.assertIn("2026/11/26B10-PRO.gpx", t["sourceUrl"], "the file the page links under the same name")
        self.assertIn(ref, f.forgot, "the web page not kept as the file")
        # a bot check: the same address answers a browser
        f = FakeFetcher({"26B10-PRO.gpx": lambda h: gpx if "Mozilla" in h.get("User-Agent", "") else page.replace(
            "26B10-PRO.gpx", "nothing.txt")})
        self.assertEqual(score.get(f, ref, {})["source"], "score")
        # gone for good
        f = FakeFetcher({"26B10-PRO.gpx": "<html><head><title>Not here</title></head><body></body></html>"})
        with self.assertRaises(trackparse.TrackError) as cm:
            score.get(f, ref, {})
        self.assertIn("newer one", str(cm.exception))
        self.assertIn(score.HOST + "/?s=gps", f.forgot, "the listing asked again")

    def test_score_listing_wp_api(self):
        api = [{"title": {"rendered": "Final Full Course GPS files 6.5.26"}, "link": "https://score-raceinfo.com/x/",
                "content": {"rendered": fx.SCORE_PAGE_HTML}, "date": "2026-06-05"}]
        f = FakeFetcher({"wp-json/wp/v2/posts": api, "wp-json/wp/v2/pages": []})
        res = score.list_items(f, {"q": "sptm"})
        self.assertEqual(len(res["items"]), 1)

    def test_local_files_and_traversal(self):
        d = tempfile.mkdtemp()
        data, _ = fx.score_gpx()
        with open(os.path.join(d, "baja.gpx"), "wb") as fh:
            fh.write(data)
        res = files.list_local(d, {})
        self.assertEqual(res["items"][0]["id"], "baja.gpx")
        self.assertGreater(len(files.get_local(d, "baja.gpx")["points"]), 10)
        with self.assertRaises(trackparse.TrackError):
            files.get_local(d, "../../etc/passwd")

    def test_url_rejects_pages_and_local(self):
        f = FakeFetcher({"example.com": "<html><head></head><body>hi</body></html>"})
        with self.assertRaises(trackparse.TrackError):
            files.get_url(f, "https://example.com/course")
        with self.assertRaises(trackparse.TrackError):
            files.get_url(f, "http://127.0.0.1:47613/x.gpx")
        with self.assertRaises(trackparse.TrackError):
            files.get_url(f, "file:///etc/passwd")


class TestPaint(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ["EARTHGPS_DIR"] = self.dir

    def tearDown(self):
        os.environ.pop("EARTHGPS_DIR", None)

    def test_pose_for_the_prefetch(self):
        import earth_gpsd
        from gpsd import paintfile
        srv = earth_gpsd.Server(FakeFetcher({}), self.dir)
        self.assertIn("pose", earth_gpsd.FEATURES)
        srv.on_pose({"type": "pose", "lat": 31.02, "lon": -114.84, "speed": 40, "heading": 200})
        got = paintfile.read_json(paintfile.pose_path())
        self.assertEqual((got["lat"], got["lon"], got["speed"], got["heading"]), (31.02, -114.84, 40, 200))
        srv.on_pose({"type": "pose", "lat": 32.0, "lon": -114.0})
        self.assertEqual(paintfile.read_json(paintfile.pose_path())["lat"], 31.02, "at most every 1.5 s")
        srv.on_pose({"type": "pose", "lat": 999, "lon": 0})

    def test_ground_code_shared_and_pasted(self):
        """The ground code a friend copies from Settings, pasted on the same course: the settings that give its seal
        (the user, 2026-10-28: "let people share terrain code so someone else can paste it ... so they for sure get the
        exact same track"); another course, a short seal, a newer terrain version: told why."""
        import earth_gpsd
        from gpsd import terrain
        pts = [[31.0, -115.5], [31.0, -115.49], [31.01, -115.48]]
        friend = earth_gpsd.Server(FakeFetcher({}), self.dir)
        friend.tracks["a"] = {"points": pts, "name": "A", "approximate": False}
        r = friend.do_paint({"type": "paint", "enabled": True, "trackId": "a", "scale": 1.4, "rough": "extra",
                             "ruts": "off", "clear": False, "tv": 2})
        code = r["code"]
        self.assertTrue(code.startswith(r["seal"] + "-"))
        me = earth_gpsd.Server(FakeFetcher({}), self.dir)
        me.tracks["a"] = {"points": pts, "name": "A", "approximate": False}
        self.assertIn("load the course", me.do_ground_code({"type": "ground_code", "code": code})["error"])
        me.do_paint({"type": "paint", "enabled": True, "trackId": "a"})
        got = me.do_ground_code({"type": "ground_code", "id": 7, "code": code})
        self.assertTrue(got["ok"], got)
        self.assertEqual(got["settings"], {"paint": True, "clear": False, "rough": "extra", "ruts": "off",
                                           "scale": 1.4, "tv": 2})
        r2 = me.do_paint(dict({"type": "paint", "enabled": True, "trackId": "a"}, **got["settings"]))
        self.assertEqual(r2["seal"], r["seal"], "the same ground")
        self.assertEqual(r2["code"], code)
        self.assertTrue(me.do_ground_code({"type": "ground_code", "code": r["seal"]})["same"], "a bare seal: compared")
        me.tracks["b"] = {"points": pts[:2], "name": "B", "approximate": False}
        me.do_paint({"type": "paint", "enabled": True, "trackId": "b"})
        self.assertIn("another course", me.do_ground_code({"type": "ground_code", "code": code})["error"])
        newer = terrain.share_code("T9-abcdef", tv=9)
        self.assertIn("update Offroad Companion", me.do_ground_code({"type": "ground_code", "code": newer})["error"])
        self.assertIn("not a ground code", me.do_ground_code({"type": "ground_code", "code": "hello"})["error"])

    def test_wetness_from_recent_rain(self):
        """The ground's wetness from the last days' rain (gpsd/wetness.py): soaked after a downpour, drying faster in
        hot dry air, the same for everyone near (a 0.1 degree grid, the UTC hour)."""
        from gpsd import wetness
        now = 1_800_000_000
        hours = [now - 3600 * k for k in range(72, -1, -1)]

        def w(rain_at, mm, temp=15.0, rh=60.0):
            p = [mm if (now - t) // 3600 in rain_at else 0.0 for t in hours]
            return wetness.model(hours, p, [temp] * len(hours), [rh] * len(hours), now + 120)
        self.assertEqual(w((), 0)["level"], "dry")
        soaked = w((1, 2, 3), 6.0)
        self.assertEqual(soaked["level"], "soaked")
        self.assertGreaterEqual(soaked["w"], wetness.PUDDLE_W)
        self.assertEqual(soaked["rainMmH"], 0.0, "it stopped an hour ago")
        self.assertGreater(w((0,), 2.0)["rainMmH"], 0, "raining now")
        old = w((40, 41), 6.0)
        self.assertLess(old["w"], soaked["w"], "two days ago: drier")
        self.assertLess(w((20,), 8.0, 35.0, 15.0)["w"], w((20,), 8.0, 10.0, 90.0)["w"], "hot dry air dries it sooner")
        self.assertEqual(wetness.grid(31.8649, -116.5967), (31.9, -116.6))
        self.assertAlmostEqual(soaked["w"] / wetness.STEP, round(soaked["w"] / wetness.STEP))
        f = FakeFetcher({"api.open-meteo.com": {"hourly": {"time": hours, "precipitation": [0.0] * 70 + [5, 5, 5],
                                                            "temperature_2m": [20] * 73,
                                                            "relative_humidity_2m": [70] * 73}}})
        got = wetness.fetch(f, 31.86, -116.6, now=now + 60)
        self.assertEqual((got["lat"], got["lon"]), (31.9, -116.6))
        self.assertIn("latitude=31.9", f.calls[0][0])
        self.assertGreater(got["w"], 0.8)

    def test_paint_flow(self):
        import earth_gpsd
        from gpsd import paintfile
        srv = earth_gpsd.Server(FakeFetcher({}), self.dir)
        pts = [[31.0, -115.5], [31.0, -115.49]]
        # unknown track (a restarted companion): asks for the points
        r = srv.do_paint({"type": "paint", "id": 1, "enabled": True, "trackId": "score:x", "scale": 1})
        self.assertEqual(r["need"], "score:x")
        r = srv.do_paint({"type": "paint", "id": 2, "enabled": True, "trackId": "score:x", "scale": 1.35,
                          "points": pts, "name": "Baja"})
        self.assertTrue(r["painting"])
        c = paintfile.read_json(paintfile.course_path())
        ln = c["lines"][0]
        self.assertEqual((c["enabled"], ln["kind"], ln["name"], ln["scale"], ln["points"]),
                         (True, "course", "Baja", 1.35, pts))
        self.assertIsNone(r["painter"])
        # a loaded track by id; an approximate one is refused
        srv.tracks["a"] = {"points": pts, "name": "A", "approximate": False}
        srv.tracks["b"] = {"points": pts, "name": "B", "approximate": True}
        self.assertTrue(srv.do_paint({"type": "paint", "enabled": True, "trackId": "a"})["painting"])
        r = srv.do_paint({"type": "paint", "enabled": True, "trackId": "b"})
        self.assertIn("error", r)
        self.assertFalse(paintfile.read_json(paintfile.course_path())["enabled"])
        # the painter's heartbeat
        paintfile.write_json(paintfile.heartbeat_path(), {"pid": 1, "t": time.time(), "course": "A"})
        self.assertEqual(srv.do_paint({"type": "paint_status"})["painter"]["course"], "A")
        paintfile.write_json(paintfile.heartbeat_path(), {"pid": 1, "t": time.time() - 600})
        self.assertIsNone(srv.do_paint({"type": "paint_status"})["painter"])
        # the GPS route: cleared too, beside the course
        self.assertTrue(srv.do_paint({"type": "paint", "enabled": True, "trackId": "a"})["painting"])
        r = srv.do_route_clear({"type": "route_clear", "enabled": True, "points": pts, "name": "To Tijuana"})
        self.assertTrue(r["clearing"])
        c = paintfile.read_json(paintfile.course_path())
        self.assertEqual([(l["kind"], l["paint"]) for l in c["lines"]], [("course", True), ("route", False)])
        srv.do_route_clear({"type": "route_clear", "enabled": False})
        self.assertEqual([l["kind"] for l in paintfile.read_json(paintfile.course_path())["lines"]], ["course"])
        srv.do_paint({"type": "paint", "enabled": False})
        c = paintfile.read_json(paintfile.course_path())
        self.assertEqual((c["enabled"], c["lines"]), (False, []))

    def test_track_save(self):
        import earth_gpsd
        from gpsd import trackparse
        pts = [[31.8, -116.6], [31.81, -116.59], [31.82, -116.6]]
        a = earth_gpsd.save_gpx(self.dir, "Arroyo <loop>", pts, [{"name": "CP 1", "lat": 31.81, "lon": -116.59}])
        b = earth_gpsd.save_gpx(self.dir, "Arroyo <loop>", pts)
        self.assertEqual((a["ref"], b["ref"]), ("Arroyo _loop_.gpx", "Arroyo _loop_ (2).gpx"))
        with open(a["path"], "rb") as f:
            t = trackparse.parse(f.read(), a["ref"])
        self.assertEqual(len(t["points"]), 3)
        self.assertEqual(sorted(w["kind"] for w in t["waypoints"]), ["checkpoint", "finish", "start"])
        with self.assertRaises(ValueError):
            earth_gpsd.save_gpx(self.dir, "x", [[31.8, -116.6]])
        srv = earth_gpsd.Server(FakeFetcher({}), self.dir)
        r = srv.do_track_save({"type": "track_save", "id": 4, "name": "Mine", "points": pts})
        self.assertTrue(r["ok"])
        self.assertEqual(srv.do_track_get({"type": "track_get", "source": "local", "ref": r["ref"]})["track"]["name"],
                         "Mine")


class TestStreets(unittest.TestCase):
    def test_tiles_and_parse(self):
        from gpsd import streets
        data = {"elements": [
            {"type": "way", "tags": {"highway": "primary", "name": "Avenida Reforma", "ref": "MEX 1"},
             "geometry": [{"lat": 31.86, "lon": -116.6}, {"lat": 31.861, "lon": -116.6}, {"lat": 31.862, "lon": -116.6}]},
            {"type": "way", "tags": {"highway": "footway"}, "geometry": [{"lat": 31.86, "lon": -116.6}]},
            {"type": "way", "tags": {"highway": "residential_link"}, "geometry": [{"lat": 31.86, "lon": -116.6},
                                                                                {"lat": 31.86, "lon": -116.59}]}]}
        ways = streets.parse(data)
        self.assertEqual([(w["c"], w["n"], w["r"], len(w["p"])) for w in ways],
                         [("primary", "Avenida Reforma", "MEX 1", 2), ("residential", "", "", 2)])
        ts = streets.tiles_near(31.865, -116.605, 1500)
        self.assertEqual(ts[0], streets.tile_of(31.865, -116.605))
        self.assertGreaterEqual(len(ts), 4)
        self.assertIn("highway", streets.query(ts[0]))

    def test_near_in_the_background(self):
        from gpsd import streets
        f = FakeFetcher({"interpreter": {"elements": [
            {"type": "way", "tags": {"highway": "residential", "name": "Calle 1"},
             "geometry": [{"lat": 31.865, "lon": -116.605}, {"lat": 31.866, "lon": -116.605}]}]}})
        s = streets.Streets(f)
        r = s.near(31.865, -116.605, 500)
        self.assertGreater(r["pending"], 0)
        end, got = time.time() + 10, []
        while time.time() < end:
            r = s.near(31.865, -116.605, 500, [t["key"] for t in got])
            got += r["tiles"]
            if not r["pending"]:
                break
            time.sleep(0.05)
        self.assertEqual(r["pending"], 0)
        self.assertTrue(any(w["n"] == "Calle 1" for t in got for w in t["ways"]))


class TestServer(unittest.TestCase):
    def test_end_to_end(self):
        import earth_gpsd
        gpx, _ = fx.score_gpx()
        osrm, _ = fx.osrm_answer()
        fetcher = FakeFetcher({"routing.openstreetmap.de": osrm, "course.gpx": gpx})
        d = tempfile.mkdtemp()
        srv = earth_gpsd.Server(fetcher, d)
        loop = asyncio.new_event_loop()
        started = threading.Event()
        holder = {}

        def run():
            asyncio.set_event_loop(loop)
            s = loop.run_until_complete(asyncio.start_server(srv.handle, "127.0.0.1", 0))
            holder["port"] = s.sockets[0].getsockname()[1]
            started.set()
            loop.run_forever()
        th = threading.Thread(target=run, daemon=True)
        th.start()
        started.wait(5)
        c = socket.create_connection(("127.0.0.1", holder["port"]), timeout=10)
        dec = protocol.Decoder()

        def ask(msg, want):
            c.sendall(protocol.encode(msg))
            end = time.time() + 10
            while time.time() < end:
                for m in dec.feed(c.recv(1 << 20)):
                    if m["type"] == want:
                        return m
            self.fail("no answer")
        h = ask({"type": "hello"}, "hello")
        self.assertEqual(len(h["sources"]), 6)
        r = ask({"type": "route", "id": 7, "lat0": 31.86, "lon0": -116.6, "lat1": 31.87, "lon1": -116.58,
                 "bearing": 90}, "route_result")
        self.assertEqual(r["id"], 7)
        self.assertEqual(len(r["steps"]), 4)
        t = ask({"type": "track_get", "id": 8, "source": "url", "ref": "https://example.org/course.gpx"},
                "track_result")
        self.assertEqual(t["track"]["id"], "url:https://example.org/course.gpx")
        bad = ask({"type": "track_get", "id": 9, "source": "url", "ref": "https://example.org/missing.gpx"},
                  "track_result")
        self.assertIn("error", bad)
        bt = ask({"type": "track_list", "id": 10, "source": "bajatracker"}, "track_list_result")
        self.assertIn("private", bt["note"])
        c.close()
        time.sleep(0.3)
        loop.call_soon_threadsafe(loop.stop)
        th.join(2)


if __name__ == "__main__":
    unittest.main()


class TestOverpass(unittest.TestCase):
    """The Overpass servers: the next one when one does not answer, the one that answered first next time, a cached
    answer before any, an old one when none answers (the user, 2026-10-22: "cannot reach overpass.kumi.systems")."""

    def setUp(self):
        from gpsd import overpass
        self.op = overpass
        overpass.reset()
        self._passes = overpass.PASSES
        overpass.PASSES = ((25, 0.0), (75, 0.0))      # (no waiting in the tests)
        self._par = overpass.PARALLEL_FIRST
        overpass.PARALLEL_FIRST = False               # (a known order of tries; test_both_at_once asks at once)

    def tearDown(self):
        self.op.PASSES = self._passes
        self.op.PARALLEL_FIRST = self._par

    def test_both_at_once(self):
        """The first pass asks both servers at the same time: the slow one does not hold up the answer."""
        import threading as th
        op = self.op
        op.PARALLEL_FIRST = True
        release = th.Event()
        f = self.fetcher({})

        def get(url, ttl=None, data=None, accept=None, timeout=None):
            f.tries.append((url, timeout))
            if "overpass-api.de" in url:
                release.wait(5)                       # (the busy one: stuck until the test ends)
                raise FetchError("cannot reach overpass-api.de: The read operation timed out")
            return Response(json.dumps({"elements": [5]}).encode(), url)
        f.get = get
        t0 = time.monotonic()
        self.assertEqual(op.run(f, "q8", ttl=None), {"elements": [5]})
        self.assertLess(time.monotonic() - t0, 2.0, "the quick server's answer, without waiting for the stuck one")
        release.set()

    def fetcher(self, answers, cache_dir=None):
        from gpsd.fetch import Fetcher
        f = Fetcher(cache_dir)
        f.tries = []

        def get(url, ttl=None, data=None, accept=None, timeout=None):
            f.tries.append((url, timeout))
            a = answers.get(urllib.parse.urlsplit(url).hostname)
            if isinstance(a, Exception) or a is None:
                raise a or FetchError("cannot reach x: timed out")
            r = Response(json.dumps(a).encode(), url)
            if ttl is not None:
                f._cache_write(url, data, r)
            return r
        f.get = get
        return f

    def test_next_server_and_remembered(self):
        op = self.op
        f = self.fetcher({"overpass-api.de": FetchError("cannot reach overpass-api.de: The read operation timed out"),
                          "overpass.private.coffee": {"elements": [1]}})
        self.assertEqual(op.run(f, "q1", ttl=None), {"elements": [1]})
        self.assertEqual([u for u, _ in f.tries][:2], [op.ENDPOINTS[0], op.ENDPOINTS[1]])
        self.assertTrue(all(t == op.PASSES[0][0] for _, t in f.tries), "each try has its own time limit")
        f.tries.clear()
        op.run(f, "q2", ttl=None)
        self.assertEqual(f.tries[0][0], op.ENDPOINTS[1], "the server that answered first next time")

    def test_cached_from_any_server_and_old_answer_when_none(self):
        import tempfile
        op = self.op
        d = tempfile.mkdtemp(prefix="egps-op-")
        f = self.fetcher({"overpass.private.coffee": {"elements": [7]}}, d)
        self.assertEqual(op.run(f, "q3", ttl=3600), {"elements": [7]})
        op.reset()
        f2 = self.fetcher({}, d)
        self.assertEqual(op.run(f2, "q3", ttl=3600), {"elements": [7]}, "cached: no server asked")
        self.assertEqual(f2.tries, [])
        import os
        import time as _t
        for root, _, files in os.walk(d):          # (the cache is old now)
            for n in files:
                os.utime(os.path.join(root, n), (_t.time() - 10 ** 7, _t.time() - 10 ** 7))
        self.assertEqual(op.run(f2, "q3", ttl=3600), {"elements": [7]}, "nobody answers: the old answer")
        self.assertEqual(len(f2.tries), 2 * len(op.ENDPOINTS), "timed out: each tried once more, patiently")

    def test_error_names_every_server(self):
        op = self.op
        f = self.fetcher({"overpass-api.de": FetchError("HTTP 502 from overpass-api.de", 502),
                          "overpass.private.coffee": FetchError("cannot reach x: certificate verify failed")})
        with self.assertRaises(FetchError) as cm:
            op.run(f, "q4", ttl=None, what="OpenStreetMap circuits")
        msg = str(cm.exception)
        self.assertIn("not answering", msg)
        self.assertEqual([(u, t) for u, t in f.tries],
                         [(op.ENDPOINTS[0], 25), (op.ENDPOINTS[1], 25), (op.ENDPOINTS[0], 75)],
                         "the busy server tried again patiently; the broken one not")
        f.tries.clear()
        with self.assertRaises(FetchError):
            op.run(f, "q5", ttl=None)
        self.assertEqual(len(f.tries), 3, "all failed recently: all tried again anyway")

    def test_busy_server_answers_the_patient_try(self):
        op = self.op
        n = {"k": 0}
        f = self.fetcher({})

        def get(url, ttl=None, data=None, accept=None, timeout=None):
            f.tries.append((url, timeout))
            n["k"] += 1
            if "overpass-api.de" in url and timeout and timeout > 30:
                return Response(json.dumps({"elements": [9]}).encode(), url)
            raise FetchError("HTTP 504 from x", 504)
        f.get = get
        self.assertEqual(op.run(f, "q7", ttl=None), {"elements": [9]})

    def test_overpass_runtime_error_is_a_failure(self):
        op = self.op
        f = self.fetcher({"overpass-api.de": {"elements": [], "remark": "runtime error: Query timed out"},
                          "overpass.private.coffee": {"elements": [3]}})
        self.assertEqual(op.run(f, "q6", ttl=None), {"elements": [3]})



class TestCourseSides(unittest.TestCase):
    def test_sides_from_the_server_profiles(self):
        """course_sides: the track's half width and middle along the painted course, from the relief profiles the
        BeamNG.Earth server wrote (the course signs beside the track, the user 2026-10-22)."""
        import earth_gpsd
        from gpsd import courseroads, paintfile
        d = tempfile.mkdtemp(prefix="egps-sides-")
        with mock_env(EARTHGPS_DIR=d):
            srv = earth_gpsd.Server(FakeFetcher({}), d)
            pts = [[31.0, -115.5 + i * 0.001] for i in range(300)]
            srv.plan["course"] = {"kind": "course", "points": pts, "scale": 1.0}
            c = courseroads.Course([tuple(p) for p in pts], 1.0)
            paintfile.write_json(os.path.join(paintfile.windows_dir(c.cid), "r000000.json"),
                                 {"algo": 2, "a": 0, "b": 100, "hw": [4.5] * 101, "ctr": [1.5] * 101})
            r = srv.do_course_sides({"id": 7, "s0": 100, "s1": 1200})
            self.assertEqual(r["step"], courseroads.STEP_M)
            self.assertEqual(r["i0"], 10)
            self.assertEqual(r["hw"][0], 4.5)
            self.assertEqual(r["ctr"][0], 1.5)
            self.assertIsNone(r["hw"][-1], "a window the server has not planned yet: not known")
            self.assertEqual(r["spots"], [], "no relief planned there: no jumps or crossings said")
            # the relief planned: a paved road across at sample 50, dirt elsewhere; jumps where the terrain has them
            rough = [1.0] * 101
            rough[49:52] = [0.0, 0.0, 0.0]
            paintfile.write_json(os.path.join(paintfile.windows_dir(c.cid), "r000000.json"),
                                 {"algo": 4, "a": 0, "b": 100, "hw": [4.5] * 101, "ctr": [1.5] * 101,
                                  "rough": rough, "rock": [0.0] * 101})
            r = srv.do_course_sides({"id": 9, "s0": 0, "s1": 1000})
            kinds = {f["kind"] for f in r["spots"]}
            cross = [f["s"] for f in r["spots"] if f["kind"] == "crossing"]
            self.assertEqual(cross, [500.0], "the paved road across")
            from gpsd import spots
            want = [p for p, _ in spots.kicks(c.lat, c.lon, 0, 1000) if not 485 <= p <= 515]   # (dirt only)
            jumps = [f["s"] for f in r["spots"] if f["kind"] == "jump"]
            self.assertEqual(jumps, want, "every jump the terrain has there, none on the paved road")
            self.assertTrue(kinds <= {"crossing", "jump"})
            # how urban the stretch is (the Lots crowds): pending while the towns are fetched, then every 100 m
            from gpsd import urban
            self.assertIn(r.get("urbState"), ("pending", "ok", "failed"))
            self.assertEqual((r["urbStep"], r["urbK0"]), (urban.STEP_M, 0))
            with mock.patch.object(urban.overpass, "run", lambda *a, **k: {"elements": [
                    {"type": "node", "id": 1, "lat": 31.0, "lon": -115.47, "tags": {"place": "town"}}]}):
                srv.urban = urban.Urban(None)
                srv.do_course_sides({"id": 11, "s0": 0, "s1": 1000})
                for _ in range(200):
                    r = srv.do_course_sides({"id": 12, "s0": 0, "s1": 3000})
                    if r["urbState"] != "pending":
                        break
                    time.sleep(0.01)
            self.assertEqual(r["urbState"], "ok")
            self.assertGreaterEqual(len(r["urb"]), 31, "every 100 m of the stretch (and a step past its end)")
            self.assertLess(r["urb"][0], r["urb"][-1], "nearer the town (at the stretch's end), more urban")
            srv.plan["course"]["rough"] = "off"
            r = srv.do_course_sides({"id": 10, "s0": 0, "s1": 1000})
            self.assertFalse([f for f in r["spots"] if f["kind"] == "jump"], "Flat terrain: no jumps")
            srv.plan["course"] = None
            self.assertIn("error", srv.do_course_sides({"id": 8, "s0": 0, "s1": 10}))


class TestJumpPose(unittest.TestCase):
    def test_a_teleport_destination_goes_through_at_once(self):
        import earth_gpsd
        from gpsd import paintfile
        d = tempfile.mkdtemp(prefix="egps-pose-")
        with mock_env(EARTHGPS_DIR=d):
            srv = earth_gpsd.Server(FakeFetcher({}), d)
            srv.preload_circuits = lambda lat, lon: None
            srv.on_pose({"lat": 31.0, "lon": -115.0})
            srv.on_pose({"lat": 31.5, "lon": -115.5})          # (within POSE_EVERY_S: dropped)
            self.assertEqual(paintfile.read_json(paintfile.pose_path())["lat"], 31.0)
            srv.on_pose({"lat": 32.0, "lon": -116.0, "jump": True})
            self.assertEqual(paintfile.read_json(paintfile.pose_path())["lat"], 32.0, "a jump at once")


class TestTerrainSnapshots(unittest.TestCase):
    def test_a_replay_keeps_its_ground_and_gets_it_back(self):
        """terrain_snapshot keeps the course's windows (as the server wrote them) under the replay's name; paint with
        pin plans that ground again, even with the course no longer loaded, with the same seal."""
        import earth_gpsd
        from gpsd import courseroads, paintfile, terrain
        d = tempfile.mkdtemp(prefix="egps-snap-")
        with mock_env(EARTHGPS_DIR=d):
            srv = earth_gpsd.Server(FakeFetcher({}), d)
            pts = [[31.0, -115.5 + i * 0.001] for i in range(300)]
            wp = [{"kind": "danger", "lat": 31.0, "lon": -115.45}, {"kind": "vcp", "lat": 31.0, "lon": -115.4}]
            srv.tracks["f:a"] = {"points": pts, "name": "Baja", "waypoints": wp}
            r = srv.do_paint({"type": "paint", "id": 1, "enabled": True, "trackId": "f:a", "scale": 1.0,
                              "rough": "auto"})
            seal = r["seal"]
            self.assertRegex(seal, r"^T\d+-")
            self.assertEqual(r["terrain"], terrain.VERSION)
            cid = courseroads.Course([tuple(p) for p in pts], 1.0).cid
            paintfile.write_json(os.path.join(paintfile.windows_dir(cid), "w000000.json"), {"algo": 4, "pieces": [1]})
            paintfile.write_json(os.path.join(paintfile.windows_dir(cid), "r000000.json"), {"algo": 4, "a": 0})
            s = srv.do_terrain_snapshot({"id": 2, "name": "rec_123_456"})
            self.assertTrue(s.get("ok"), s)
            self.assertEqual((s["seal"], s["windows"]), (seal, 2))
            # later: other settings, another course loaded, the companion restarted (tracks forgotten)
            srv.do_paint({"type": "paint", "id": 3, "enabled": True, "trackId": "f:a", "scale": 1.0, "rough": "on"})
            srv.tracks.clear()
            r2 = srv.do_paint({"type": "paint", "id": 4, "enabled": True, "trackId": "f:a", "scale": 1.0,
                               "rough": "auto", "pin": "rec_123_456"})
            self.assertNotIn("need", r2, "the course comes from the snapshot")
            self.assertEqual(r2["seal"], seal, "the same ground")
            plan = paintfile.read_json(paintfile.course_path())["lines"][0]
            self.assertEqual(plan["pin"], "rec_123_456")
            self.assertEqual(plan["dangers"], [[31.0, -115.45]])
            r3 = srv.do_paint({"type": "paint", "id": 5, "enabled": True, "trackId": "f:a", "scale": 1.0,
                               "pin": "nope"})
            self.assertEqual(r3.get("pinMissing"), "nope")
            self.assertIn("error", srv.do_terrain_snapshot({"id": 6, "name": "///"}))
            # old snapshots go
            for i in range(5):
                os.makedirs(paintfile.snapshots_dir(f"x{i}"))
            earth_gpsd.prune_snapshots(keep=3)
            self.assertEqual(len(os.listdir(paintfile.snapshots_dir())), 3)


class mock_env:
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = os.environ.get(k)
            os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
