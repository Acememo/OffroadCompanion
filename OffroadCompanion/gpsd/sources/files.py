"""Course files you have: a link (any GPX / KML / KMZ / GeoJSON on the web) or files in the tracks folder.

This is also the way in for Baja Tracker: its race maps are private to each team (a password-protected portal),
so there is nothing public to download. Export or copy the course file your team admin set up (or any course
KML/GPX you were given) into the tracks folder, or paste its link.
"""
import os
import time
import urllib.parse

from .. import trackparse

URL_ID = "url"
LOCAL_ID = "local"
BAJATRACKER_ID = "bajatracker"
EXTS = (".gpx", ".kml", ".kmz", ".geojson", ".json")
MAX_FILE = 200 * 1024 * 1024

BAJATRACKER_NOTE = ("Baja Tracker race maps are private to each team (password protected), so they cannot be "
                    "downloaded here. Ask your team admin for the course as KML/GPX, drop it in the tracks folder "
                    "({dir}) and it shows up under 'My files', or paste its link under 'Link'.")


def list_local(tracks_dir, ctx):
    items = []
    if tracks_dir and os.path.isdir(tracks_dir):
        for root, _dirs, files in os.walk(tracks_dir):
            for f in sorted(files):
                if not f.lower().endswith(EXTS):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, tracks_dir)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                items.append({"id": rel, "name": os.path.splitext(f)[0], "kind": "course",
                              "detail": f"{os.path.splitext(f)[1][1:].upper()} - {st.st_size // 1024} KB - "
                                        f"{time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))}"})
    q = (ctx.get("q") or "").strip().lower()
    if q:
        items = [i for i in items if q in i["name"].lower()]
    note = f"Put GPX / KML / KMZ files in {tracks_dir}." if not items else f"Files in {tracks_dir}."
    return {"items": items, "note": note}


def get_local(tracks_dir, ref):
    base = os.path.realpath(tracks_dir)
    p = os.path.realpath(os.path.join(base, ref))
    if not (p == base or p.startswith(base + os.sep)) or not os.path.isfile(p):
        raise trackparse.TrackError("file not found in the tracks folder")
    if os.path.getsize(p) > MAX_FILE:
        raise trackparse.TrackError("file too large")
    with open(p, "rb") as f:
        data = f.read()
    return trackparse.parse(data, os.path.basename(p), source=LOCAL_ID, source_url="",
                            attribution="Course: your file")


def get_url(fetcher, url):
    url = (url or "").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise trackparse.TrackError("paste a full http(s) link to a GPX, KML, KMZ or GeoJSON file")
    if (parts.hostname or "").lower() in ("localhost", "127.0.0.1", "::1"):
        raise trackparse.TrackError("local addresses are not fetched")
    resp = fetcher.get(url, ttl=3600)
    ctype = (resp.content_type or "").lower()
    if "text/html" in ctype and not resp.body.lstrip()[:5].lower().startswith((b"<?xml", b"<gpx", b"<kml")):
        raise trackparse.TrackError("that link is a web page, not a course file (look for a .gpx / .kml / .kmz "
                                    "download link on it)")
    name = urllib.parse.unquote(parts.path.rsplit("/", 1)[-1]) or parts.netloc
    host = parts.hostname or ""
    return trackparse.parse(resp.body, name, source=URL_ID, source_url=url, attribution=f"Course: {host}")


def bajatracker_info(tracks_dir):
    return {"items": [], "note": BAJATRACKER_NOTE.format(dir=tracks_dir)}
