"""Test fixtures shaped like the real services' answers."""
import io
import json
import math
import zipfile

LAT0, LON0 = 31.8667, -116.6        # Ensenada


def line(n=200, step_m=50.0, lat0=LAT0, lon0=LON0, curve=True):
    """A course heading east then curving south: [(lat, lon)]."""
    pts = []
    x = y = 0.0
    h = math.pi / 2
    for i in range(n):
        pts.append((lat0 + y / 111195.0, lon0 + x / (111195.0 * math.cos(math.radians(lat0)))))
        if curve and 80 <= i < 110:
            h += math.radians(3)          # a long right-hander
        x += step_m * math.sin(h)
        y += step_m * math.cos(h)
    return pts


def score_gpx(with_track=True):
    pts = line()
    wpts = [
        ("BEGIN PRE-RUN", pts[2], "Navaid, Red"),
        ("RM 1", pts[33], "Waypoint"), ("RM 2", pts[65], "Waypoint"), ("RM 3", pts[97], "Waypoint"),
        ("RM 4", pts[129], "Waypoint"), ("RM 5", pts[161], "Waypoint"),
        ("SZ01 60", pts[10], "Waypoint"), ("END SZ01", pts[20], "Waypoint"),
        ("END SZ02", pts[150], "Waypoint"),
        ("VCP 181A", pts[120], "Flag, Red"), ("CHECK 1", pts[140], "Flag, Blue"),
        ("DANGER 3-15", pts[90], "Skull and Crossbones"), ("A. ENSENADA", (pts[50][0] + 0.02, pts[50][1]), "Navaid, Blue"),
    ]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="Garmin Desktop App">',
           "<metadata><time>2026-06-02T20:20:25Z</time></metadata>"]
    for name, (la, lo), sym in wpts:
        out.append(f'<wpt lat="{la}" lon="{lo}"><time>2026-06-02T20:20:25Z</time><name>{name}</name>'
                   f"<sym>{sym}</sym><type>user</type></wpt>")
    if with_track:
        out.append("<trk><name>26B5H COMPLETE PROC</name><trkseg>")
        for la, lo in pts[:100]:
            out.append(f'<trkpt lat="{la}" lon="{lo}"><ele>12.0</ele></trkpt>')
        out.append("</trkseg><trkseg>")
        for la, lo in pts[100:]:
            out.append(f'<trkpt lat="{la}" lon="{lo}"></trkpt>')
        out.append("</trkseg></trk>")
    out.append("</gpx>")
    return "\n".join(out).encode("utf-8"), pts


def kml_pieces():
    """The course as three LineStrings out of order, one reversed, plus a Point folder."""
    pts = line()
    a, b, c = pts[:70], pts[69:140], pts[139:]
    def ls(p):
        return " ".join(f"{lo},{la},0" for la, lo in p)
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2"><Document>
<name>26B5H-COMPLETE SPTM-0604.kml</name><Folder><name>Course</name>
<Placemark><name>Section 3</name><LineString><coordinates>{ls(c)}</coordinates></LineString></Placemark>
<Placemark><name>Section 1</name><LineString><coordinates>{ls(a)}</coordinates></LineString></Placemark>
<Placemark><name>Section 2</name><LineString><coordinates>{ls(b[::-1])}</coordinates></LineString></Placemark>
</Folder><Folder id="Waypoints"><name>Waypoints</name>
<Placemark><name>VCP 12</name><Point><coordinates>{pts[60][1]},{pts[60][0]},0</coordinates></Point></Placemark>
<Placemark><name>RM 2</name><Point><coordinates>{pts[65][1]},{pts[65][0]},0</coordinates></Point></Placemark>
</Folder></Document></kml>"""
    return body.encode("utf-8"), pts


def kmz(kml_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("files/icon.png", b"\x89PNG")
        z.writestr("doc.kml", kml_bytes)
    return buf.getvalue()


def osrm_answer():
    pts = line(40, 40.0)
    coords = [[lo, la] for la, lo in pts]
    steps = [
        {"maneuver": {"type": "depart", "bearing_after": 90, "location": coords[0]}, "name": "Calle Primera",
         "distance": 1200, "duration": 90},
        {"maneuver": {"type": "turn", "modifier": "right", "location": coords[30]}, "name": "Avenida Reforma",
         "ref": "MEX 1", "distance": 400, "duration": 30},
        {"maneuver": {"type": "roundabout", "modifier": "right", "exit": 2, "location": coords[35]}, "name": "",
         "distance": 100, "duration": 20},
        {"maneuver": {"type": "arrive", "modifier": "left", "location": coords[-1]}, "name": "Avenida Reforma",
         "distance": 0, "duration": 0},
    ]
    return {"code": "Ok", "routes": [{"distance": 1560.0, "duration": 140.0, "geometry": {"coordinates": coords},
                                      "legs": [{"steps": steps}]}]}, pts


def overpass_answer():
    """A circuit lap in 3 ways plus a pit lane, and a far karting track."""
    import math as m
    lap = []
    cx, cy, r = 19.4061, -99.0925, 0.006
    for i in range(121):
        a = 2 * m.pi * i / 120
        lap.append((cx + r * m.sin(a), cy + r * 1.5 * m.cos(a)))
    def way(i, pts, tags):
        return {"type": "way", "id": i, "tags": tags, "geometry": [{"lat": a, "lon": b} for a, b in pts]}
    els = [way(1, lap[0:41], {"highway": "raceway", "name": "Autódromo Hermanos Rodríguez"}),
           way(2, lap[40:81], {"highway": "raceway", "name": "Autódromo Hermanos Rodríguez"}),
           way(3, lap[80:121], {"highway": "raceway"}),
           way(4, [lap[5], (lap[5][0] + 0.001, lap[5][1]), lap[12]], {"highway": "raceway", "raceway": "pit_lane"})]
    kart = [(19.5 + 0.0005 * m.sin(2 * m.pi * i / 40), -99.2 + 0.0008 * m.cos(2 * m.pi * i / 40)) for i in range(41)]
    els.append(way(9, kart, {"leisure": "track", "sport": "karting", "name": "Kartódromo"}))
    return {"elements": els}


RACEMX_MAP_HTML = """<html><head><title>Baja 1000 2026 Course Map</title></head><body>
<h2>Map: the 2026 Baja 1000 course, start to finish</h2><ol>
<li><strong><a href="#sjc">San José del Cabo, Avenida Centenario</a></strong>: start and finish line.
 <a href="https://www.google.com/maps/search/?api=1&amp;query=23.0637%2C-109.6948" target="_blank">Google Maps</a></li>
<li><strong><a href="#pulmo">Cabo Pulmo</a></strong>: East Cape, early in the race.
 <a href="https://www.google.com/maps/search/?api=1&amp;query=23.4454%2C-109.424">Google Maps</a></li>
<li><strong><a href="#lb">Los Barriles</a></strong>: Sea of Cortez coast.
 <a href="https://www.google.com/maps/search/?api=1&amp;query=23.6818%2C-109.6995">Google Maps</a></li>
</ol></body></html>"""

VENUES_JSON = json.dumps({"name": "Race.mx venues", "venues": [
    {"name": "Autódromo Hermanos Rodríguez", "location": "Mexico City, CDMX", "surface": "Asphalt",
     "length_km": 4.304, "latitude": 19.4061, "longitude": -99.0925,
     "url": "https://race.mx/pistas/autodromo-hermanos-rodriguez/"},
    {"name": "Ensenada – SCORE Baja Race Start/Finish", "location": "Ensenada, Baja California",
     "surface": "Dirt / Off-Road", "length_km": None, "latitude": 31.8667, "longitude": -116.6,
     "url": "https://race.mx/pistas/ensenada-score-baja-start-finish/"}]})

SCORE_PAGE_HTML = """<html><head><title>Final Full Course GPS files 6.5.26 | SCORE</title></head><body>
<h3>Complete Pro</h3>
<a href="https://danieltoddhorne.com/score/2026/baja500/642026/fc/26B5H-COMPLETE PROC-0604.kml">KML</a>
<a href="https://danieltoddhorne.com/score/2026/baja500/642026/fc/26B5H-COMPLETE PROC-0604.GPX">GPX</a>
<a href="https://danieltoddhorne.com/score/2026/baja500/642026/fc/26B5H-COMPLETE PROC-0604.usr.zip">USR Zipped</a>
<h3>Sportsman</h3>
<a href="https://danieltoddhorne.com/score/2026/baja500/642026/fc/26B5H-COMPLETE SPTM-0604.kml">KML</a>
<a href="https://danieltoddhorne.com/score/2026/baja500/642026/fc/26B5H-COMPLETE SPTM-0604.GPX">GPX</a>
</body></html>"""

SCORE_2021_HTML = """<html><head><title>GPS Files 2021 Baja 1000</title></head><body>
<p><strong>Full Course</strong></p><p><a href="https://score-raceinfo.com/2021/baja1000/gps/r/f.GPX">GPX Files</a>
<a href="https://score-raceinfo.com/2021/baja1000/gps/r/f.kmz">KMZ Files</a></p></body></html>"""
