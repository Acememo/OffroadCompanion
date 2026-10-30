"""Course files -> one track the game can guide along.

Reads GPX (trk/trkseg/trkpt, rte/rtept, wpt), KML (LineString, gx:Track, Point placemarks, any nesting), KMZ (a
zipped KML) and GeoJSON. Off-road race files (SCORE's GPX/KML for the Baja races) are mostly waypoints with
conventional names; those are classified so the game can call them out:

    RM 105            race mile marker            -> racemile (rm=105)
    VCP 181A          virtual checkpoint          -> vcp (must be passed close by)
    CHECK 1 / CP 2    checkpoint                  -> checkpoint
    SZ01 / BEGIN SZ01 speed zone starts           -> speed_start (limit when the name carries one: "SZ01 60")
    END SZ01          speed zone ends             -> speed_end
    DANGER 3-15       hazard (skull symbol too)   -> danger
    START / FINISH, PIT, PRE-RUN markers, everything else -> place

The track is:
    {name, kind: 'course' | 'circuit' | 'waypoints', closed, approximate, points [[lat, lon]], length,
     waypoints [{name, kind, lat, lon, s, off, rm?, limit?}] sorted along the course, zones [{name, s0, s1, limit}],
     rm [[s, rm]...] (race-mile anchors), bounds [s, w, n, e]}
s is metres along the line; off how far the waypoint lies from it.
"""
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from bisect import bisect_left

from . import geo

SIMPLIFY_M = 2.0
MAX_POINTS = 30000
CHAIN_GAP_M = 75.0          # two lines this close end to end are one course
CLOSED_M = 60.0             # first and last point this close: a closed circuit
NEAR_LINE_M = 400.0         # a waypoint farther than this from the line is only a map marker


class TrackError(ValueError):
    pass


# -- waypoint names ---------------------------------------------------------------------------------------------
_RE_RM = re.compile(r"^\s*(?:RM|R\.M\.|MILE|MI)\s*#?\s*(\d+(?:\.\d+)?)\b", re.I)
_RE_VCP = re.compile(r"^\s*VCP\b", re.I)
_RE_CP = re.compile(r"\b(?:CHECK\s*(?:POINT)?|CP|PC)\s*#?\s*\d+", re.I)
_RE_SZ = re.compile(r"\bS\.?Z\.?\s*#?\s*0*(\d+)", re.I)
_RE_SZ_LIMIT = re.compile(r"\bS\.?Z\.?\s*#?\s*\d+\D{1,4}(\d{2,3})\s*(KPH|KMH|KM/H|MPH)?\b", re.I)
_RE_DANGER = re.compile(r"\b(DANGER|PELIGRO|HAZARD|CAUTION|PRECAUCION|PRECAUCIÓN)\b", re.I)
_RE_START = re.compile(r"\b(START|SALIDA|ARRANQUE|ARRANCAR)\b", re.I)
_RE_FINISH = re.compile(r"\b(FINISH|META|LLEGADA)\b", re.I)
_RE_PIT = re.compile(r"\b(PIT|PITS)\b", re.I)
_RE_END = re.compile(r"\b(END|FIN|TERMINA)\b", re.I)


def classify(name, sym=""):
    """(kind, extra dict) for a waypoint name. Pure."""
    n = (name or "").strip()
    extra = {}
    m = _RE_RM.match(n)
    if m:
        extra["rm"] = float(m.group(1))
        return "racemile", extra
    if _RE_VCP.match(n):
        return "vcp", extra
    m = _RE_SZ.search(n)
    if m:
        extra["zone"] = int(m.group(1))
        lim = _RE_SZ_LIMIT.search(n)
        if lim:
            v = int(lim.group(1))
            unit = (lim.group(2) or "KPH").upper()
            kph = v * 1.609344 if unit == "MPH" else v
            if 10 <= kph <= 140:
                extra["limit"] = round(kph)
        return ("speed_end" if _RE_END.search(n) else "speed_start"), extra
    if _RE_DANGER.search(n) or "skull" in (sym or "").lower():
        return "danger", extra
    if _RE_CP.search(n):
        return "checkpoint", extra
    if _RE_FINISH.search(n):
        return "finish", extra
    if _RE_START.search(n) and "PRE-RUN" not in n.upper() and "PRERUN" not in n.upper():
        return "start", extra
    if _RE_PIT.search(n):
        return "pit", extra
    return "place", extra


# -- readers ------------------------------------------------------------------------------------------------------
def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child_text(el, name):
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _xml_root(data):
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        # a stray BOM or leading junk (some exporters): try from the first '<'
        i = data.find(b"<")
        if i > 0:
            try:
                return ET.fromstring(data[i:])
            except ET.ParseError:
                pass
        raise TrackError(f"not a valid GPX/KML file ({e})") from None


def read_gpx(root):
    lines, wpts, name = [], [], ""
    for el in root.iter():
        t = _local(el.tag)
        if t == "metadata" and not name:
            name = _child_text(el, "name")
        elif t == "trk":
            tname = _child_text(el, "name")
            segs = []
            for seg in el:
                if _local(seg.tag) != "trkseg":
                    continue
                pts = _gpx_points(seg, "trkpt")
                if len(pts) >= 2:
                    segs.append(pts)
            # the segments of one track are one line in order (a GPS dropout splits them)
            joined = [p for s in segs for p in s]
            if len(joined) >= 2:
                lines.append({"name": tname, "points": joined})
            name = name or tname
        elif t == "rte":
            pts = _gpx_points(el, "rtept")
            if len(pts) >= 2:
                lines.append({"name": _child_text(el, "name"), "points": pts})
        elif t == "wpt":
            p = _gpx_latlon(el)
            if p:
                wpts.append({"name": _child_text(el, "name"), "sym": _child_text(el, "sym"),
                             "desc": _child_text(el, "desc") or _child_text(el, "cmt"), "lat": p[0], "lon": p[1]})
    return name, lines, wpts


def _gpx_latlon(el):
    try:
        lat, lon = float(el.get("lat")), float(el.get("lon"))
    except (TypeError, ValueError):
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def _gpx_points(parent, tag):
    out = []
    for c in parent:
        if _local(c.tag) == tag:
            p = _gpx_latlon(c)
            if p:
                out.append(p)
    return out


def _kml_coords(text):
    out = []
    for tok in (text or "").split():
        parts = tok.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append((lat, lon))
    return out


def read_kml(root):
    lines, wpts = [], []
    doc_name = ""
    for el in root.iter():
        if _local(el.tag) in ("Document", "Folder") and not doc_name:
            doc_name = _child_text(el, "name")
        if _local(el.tag) != "Placemark":
            continue
        pname = _child_text(el, "name")
        desc = _child_text(el, "description")
        for g in el.iter():
            t = _local(g.tag)
            if t == "LineString" or t == "LinearRing":
                for c in g:
                    if _local(c.tag) == "coordinates":
                        pts = _kml_coords(c.text)
                        if len(pts) >= 2:
                            lines.append({"name": pname, "points": pts})
            elif t == "Track":                       # gx:Track: <gx:coord>lon lat alt</gx:coord>
                pts = []
                for c in g:
                    if _local(c.tag) == "coord":
                        parts = (c.text or "").split()
                        try:
                            pts.append((float(parts[1]), float(parts[0])))
                        except (IndexError, ValueError):
                            pass
                if len(pts) >= 2:
                    lines.append({"name": pname, "points": pts})
            elif t == "Point":
                for c in g:
                    if _local(c.tag) == "coordinates":
                        pts = _kml_coords(c.text)
                        if pts:
                            wpts.append({"name": pname, "sym": "", "desc": desc, "lat": pts[0][0], "lon": pts[0][1]})
    return doc_name, lines, wpts


def read_geojson(obj):
    lines, wpts = [], []
    feats = obj.get("features") if obj.get("type") == "FeatureCollection" else [obj]
    for f in feats or []:
        g = f.get("geometry") if f.get("type") == "Feature" else f
        props = (f.get("properties") or {}) if isinstance(f, dict) else {}
        name = str(props.get("name") or props.get("title") or "")
        if not isinstance(g, dict):
            continue
        t, c = g.get("type"), g.get("coordinates")
        try:
            if t == "LineString":
                lines.append({"name": name, "points": [(float(p[1]), float(p[0])) for p in c]})
            elif t == "MultiLineString":
                for part in c:
                    lines.append({"name": name, "points": [(float(p[1]), float(p[0])) for p in part]})
            elif t == "Point":
                wpts.append({"name": name, "sym": "", "desc": "", "lat": float(c[1]), "lon": float(c[0])})
        except (TypeError, ValueError, IndexError):
            continue
    return str(obj.get("name") or ""), lines, wpts


class WebPageError(TrackError):
    """A web page came instead of a course file (a file moved or replaced on its site, a site's error page)."""


def looks_like_html(data):
    """Do these bytes look like a web page (not GPX / KML)?"""
    head = bytes(data[:4096]).lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith((b"<!doctype html", b"<html")):
        return True
    return b"<html" in head[:1024] or (b"<head" in head and (b"<body" in head or b"<meta" in head or b"<title" in head))


def read_any(data, filename=""):
    """(name, lines, waypoints) from file bytes (format sniffed). Raises TrackError."""
    if not data:
        raise TrackError("empty file")
    if data[:2] != b"PK" and looks_like_html(data):
        raise WebPageError("a web page came instead of the course file")
    if data[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise TrackError("broken KMZ/zip file") from None
        names = [n for n in zf.namelist() if n.lower().endswith((".kml", ".gpx", ".geojson", ".json"))]
        if not names:
            raise TrackError("the zip has no KML/GPX inside")
        names.sort(key=lambda n: (0 if n.lower().endswith("doc.kml") else 1, n.count("/"), n))
        info = zf.getinfo(names[0])
        if info.file_size > 200 * 1024 * 1024:
            raise TrackError("the file inside the zip is too large")
        return read_any(zf.read(names[0]), names[0])
    head = data.lstrip()[:1]
    if head in (b"{", b"["):
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise TrackError("not valid GeoJSON") from None
        if isinstance(obj, dict):
            return read_geojson(obj)
        raise TrackError("unsupported JSON")
    root = _xml_root(data)
    kind = _local(root.tag).lower()
    if kind == "gpx":
        return read_gpx(root)
    if kind == "kml":
        return read_kml(root)
    # some KML exports wrap in <Document> without <kml>
    if kind in ("document", "folder"):
        return read_kml(root)
    raise TrackError(f"unknown file type <{_local(root.tag)}> ({filename or 'download'})")


# -- building the track -------------------------------------------------------------------------------------------
def _length(pts):
    return geo.cumulative(pts)[-1] if len(pts) >= 2 else 0.0


def chain_lines(lines, gap_m=CHAIN_GAP_M):
    """The longest course made of lines that meet end to end (pieces of one course exported per section).
    Starts from the longest line and keeps adding the piece whose end is nearest one of the ends (reversed if
    needed) while it is within gap_m. Pure."""
    if not lines:
        return []
    pool = [list(l["points"]) for l in lines if len(l["points"]) >= 2]
    pool.sort(key=_length, reverse=True)
    course = pool.pop(0)
    # how much of the course runs the way its file drew it: the course keeps the majority's direction (the
    # longest piece can be the one drawn backwards)
    kept, flipped = _length(course), 0.0
    while pool:
        best = None
        E, S = course[-1], course[0]
        for k, ln in enumerate(pool):
            p0, p1 = ln[0], ln[-1]
            # (distance, piece, attach at the course's end?, reverse the piece?)
            for d, at_end, rev in ((geo.haversine(E[0], E[1], p0[0], p0[1]), True, False),
                                   (geo.haversine(E[0], E[1], p1[0], p1[1]), True, True),
                                   (geo.haversine(S[0], S[1], p1[0], p1[1]), False, False),
                                   (geo.haversine(S[0], S[1], p0[0], p0[1]), False, True)):
                if d <= gap_m and (best is None or d < best[0]):
                    best = (d, k, at_end, rev)
        if not best:
            break
        _, k, at_end, rev = best
        ln = pool.pop(k)
        if rev:
            ln = ln[::-1]
            flipped += _length(ln)
        else:
            kept += _length(ln)
        course = course + ln[1:] if at_end else ln[:-1] + course
    return course[::-1] if flipped > kept else course


def _orient(points, wps):
    """The course reversed when its race miles count down along it, or its start marker sits at its end. Pure."""
    if len(points) < 2:
        return points
    cum = geo.cumulative(points)
    rms = sorted([w for w in wps if w["kind"] == "racemile"], key=lambda w: w["rm"])
    if len(rms) >= 2:
        ss = [geo.project(points, cum, w["lat"], w["lon"])[0] for w in rms]
        up = sum(1 for a, b in zip(ss, ss[1:]) if b > a)
        down = sum(1 for a, b in zip(ss, ss[1:]) if b < a)
        if down > up:
            return points[::-1]
        if up > down:
            return points
    st = next((w for w in wps if w["kind"] == "start"), None)
    if st:
        a = geo.haversine(points[0][0], points[0][1], st["lat"], st["lon"])
        b = geo.haversine(points[-1][0], points[-1][1], st["lat"], st["lon"])
        if b < a * 0.5:
            return points[::-1]
    return points


def _dedupe(points):
    out = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > 1e-7 or abs(p[1] - out[-1][1]) > 1e-7:
            out.append(p)
    return out


def _snap(points, cum, w, expect_s=None, window=None):
    """(s, off) of waypoint w on the line; with expect_s, the nearest pass within window of it is preferred (a course
    that crosses itself: race mile 300 is not the pass at race mile 20)."""
    if expect_s is not None and window:
        i0 = max(0, bisect_left(cum, expect_s - window) - 1)
        i1 = min(len(points) - 1, bisect_left(cum, expect_s + window) + 1)
        if i1 > i0:
            s, off, _ = geo.project(points, cum, w["lat"], w["lon"], i0, i1, expect_s - window, expect_s + window)
            if off <= NEAR_LINE_M:
                return s, off
    s, off, _ = geo.project(points, cum, w["lat"], w["lon"])
    return s, off


def _increasing(pairs):
    """The longest run of (s, rm) pairs increasing in both (drops misplaced markers). Pure, O(n^2) on ~200."""
    n = len(pairs)
    if n == 0:
        return []
    best, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if pairs[j][0] < pairs[i][0] and pairs[j][1] < pairs[i][1] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k])
    out = []
    while i >= 0:
        out.append(pairs[i])
        i = prev[i]
    return out[::-1]


def build(name, lines, wpts, source="", source_url="", attribution="", kind_hint=None):
    """The track dict (see the module doc). Raises TrackError when there is nothing to drive."""
    wps = []
    for w in wpts:
        kind, extra = classify(w.get("name"), w.get("sym"))
        d = {"name": (w.get("name") or "").strip() or kind, "kind": kind,
             "lat": round(w["lat"], 6), "lon": round(w["lon"], 6)}
        d.update(extra)
        wps.append(d)

    approximate = False
    points = _dedupe(chain_lines(lines)) if lines else []
    if len(points) < 2:
        # no line in the file: the race-mile markers in order are a rough line (straight between markers)
        rms = sorted([w for w in wps if w["kind"] == "racemile"], key=lambda w: w["rm"])
        if len(rms) >= 3:
            starts = [w for w in wps if w["kind"] == "start"]
            finish = [w for w in wps if w["kind"] == "finish"]
            seq = starts[:1] + rms + finish[:1]
            points = [(w["lat"], w["lon"]) for w in seq]
            approximate = True
        else:
            points = []

    if len(points) >= 2:
        pts = geo.simplify(points, SIMPLIFY_M)
        tol = SIMPLIFY_M
        while len(pts) > MAX_POINTS:
            tol *= 2
            pts = geo.simplify(points, tol)
        points = _orient(pts, wps) if not approximate else pts
        cum = geo.cumulative(points)
        length = cum[-1]
        closed = geo.haversine(points[0][0], points[0][1], points[-1][0], points[-1][1]) <= CLOSED_M and length > 300
        # first pass: race miles anchor the scale (how many metres per course mile this file really has)
        raw_rm = []
        for w in wps:
            if w["kind"] == "racemile":
                s, off = _snap(points, cum, w, w["rm"] * geo.MILE_M, max(3000.0, 0.15 * length))
                w["s"], w["off"] = s, off
                if off <= NEAR_LINE_M:
                    raw_rm.append((s, w["rm"]))
        anchors = _increasing(sorted(raw_rm))
        for w in wps:
            if "s" in w:
                continue
            w["s"], w["off"] = _snap(points, cum, w)
        for w in wps:
            w["s"], w["off"] = round(w["s"], 1), round(w["off"], 1)
        wps.sort(key=lambda w: w["s"])
        kind = kind_hint or ("circuit" if closed and length < 30000 else "course")
    else:
        if not wps:
            raise TrackError("the file has no course line and no waypoints")
        cum, length, closed, anchors = [0.0], 0.0, False, []
        kind = "waypoints"
        # file order is the course order; s = distance along the waypoints
        s = 0.0
        for i, w in enumerate(wps):
            if i:
                s += geo.haversine(wps[i - 1]["lat"], wps[i - 1]["lon"], w["lat"], w["lon"])
            w["s"], w["off"] = round(s, 1), 0.0
        length = s

    zones = _speed_zones(wps)
    lats = [p[0] for p in points] + [w["lat"] for w in wps]
    lons = [p[1] for p in points] + [w["lon"] for w in wps]
    return {
        "name": name or "Course", "source": source, "sourceUrl": source_url, "attribution": attribution,
        "kind": kind, "closed": bool(closed), "approximate": approximate,
        "points": [[round(a, 6), round(b, 6)] for a, b in points],
        "length": round(length, 1), "waypoints": wps, "zones": zones,
        "rm": [[round(s, 1), rm] for s, rm in anchors],
        "bounds": [min(lats), min(lons), max(lats), max(lons)] if lats else None,
    }


def _speed_zones(wps):
    """Pair speed_start / speed_end markers by zone number into [s0, s1] stretches. A zone with only its end marker
    stays a marker (no guessed start). Pure."""
    starts, zones = {}, []
    for w in wps:
        if w["kind"] == "speed_start":
            starts[w.get("zone")] = w
        elif w["kind"] == "speed_end":
            a = starts.pop(w.get("zone"), None)
            if a and a["s"] <= w["s"]:
                zones.append({"name": f"SZ{a.get('zone'):02d}" if a.get("zone") is not None else a["name"],
                              "s0": a["s"], "s1": w["s"], "limit": a.get("limit") or w.get("limit")})
    return zones


def parse(data, filename="", **meta):
    name, lines, wpts = read_any(data, filename)
    if not name and filename:
        name = re.sub(r"\.(kmz|kml|gpx|geojson|json)$", "", filename.rsplit("/", 1)[-1], flags=re.I)
    return build(name, lines, wpts, **meta)


def from_points(name, points, waypoints=(), **meta):
    """A track from a line [(lat, lon)] (OSM raceways) and optional waypoints [{name, lat, lon}]."""
    return build(name, [{"name": name, "points": list(points)}] if points else [],
                 [dict(w, sym=w.get("sym", "")) for w in waypoints], **meta)
