"""Track sources: each lists items and loads one as a track (trackparse.build's dict)."""
from . import files, osm, racemx, score

CATALOG = [
    {"id": score.ID, "title": score.TITLE, "needsPosition": False, "hint": "Baja 1000 / 500 / 400 / San Felipe course files"},
    {"id": racemx.ID, "title": racemx.TITLE, "needsPosition": False, "hint": "Mexico circuits and the Baja 1000 route order"},
    {"id": osm.ID, "title": osm.TITLE, "needsPosition": True, "hint": "Real circuit outlines near the car"},
    {"id": files.BAJATRACKER_ID, "title": "Baja Tracker", "needsPosition": False, "hint": "Private team maps: import the file"},
    {"id": files.LOCAL_ID, "title": "My files (tracks folder)", "needsPosition": False, "hint": "GPX / KML / KMZ you saved"},
    {"id": files.URL_ID, "title": "Link to a course file", "needsPosition": False, "hint": "Paste a GPX / KML / KMZ link"},
]


def list_items(source, fetcher, ctx, tracks_dir):
    if source == score.ID:
        return score.list_items(fetcher, ctx)
    if source == racemx.ID:
        return racemx.list_items(fetcher, ctx)
    if source == osm.ID:
        return osm.list_items(fetcher, ctx)
    if source == files.LOCAL_ID:
        return files.list_local(tracks_dir, ctx)
    if source == files.BAJATRACKER_ID:
        return files.bajatracker_info(tracks_dir)
    if source == files.URL_ID:
        return {"items": [], "note": "Paste a link to a GPX, KML, KMZ or GeoJSON file."}
    raise ValueError(f"unknown source {source!r}")


def get(source, ref, fetcher, ctx, tracks_dir):
    if source == score.ID:
        return score.get(fetcher, ref, ctx)
    if source == racemx.ID:
        return racemx.get(fetcher, ref, ctx)
    if source == osm.ID:
        return osm.get(fetcher, ref, ctx)
    if source == files.LOCAL_ID:
        return files.get_local(tracks_dir, ref)
    if source in (files.URL_ID, files.BAJATRACKER_ID):
        return files.get_url(fetcher, ref)
    raise ValueError(f"unknown source {source!r}")
