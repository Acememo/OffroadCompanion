"""SCORE International race courses (the Baja 1000, Baja 500, Baja 400, San Felipe 250).

SCORE posts each race's course as GPX / KML / KMZ files on score-raceinfo.com ("Final Full Course GPS files",
"GPS Files" pages, one file per class group: Pro, Sportsman). They are found three ways, any one is enough:
the site's WordPress search API, its search page, and a few known GPS-file pages. Each file found is one item;
when a course comes in several formats GPX is picked (it carries the symbols), then KMZ, then KML.
"""
import re
import urllib.parse

from .. import htmllinks, trackparse

ID = "score"
TITLE = "SCORE International (Baja races)"
HOST = "https://score-raceinfo.com"
ATTRIBUTION = "Course: SCORE International (score-raceinfo.com)"
INDEX_TTL = 6 * 3600
FILE_TTL = 24 * 3600
SEED_PAGES = [
    HOST + "/final-full-course-gps-files-6-5-26/",      # 2026 Baja 500
    HOST + "/gps-files-2021-baja-1000/",
]
RACE_PAGES = [
    HOST + "/59th-baja-1000-nov-9-15-2026/",
    HOST + "/course-map-2026-baja-1000/",
]
NOTE = ("SCORE publishes each race's course files a few weeks before race day (the 2026 Baja 1000 files are due "
        "late October). Pro and Sportsman classes can have different courses.")
_PREF = {".gpx": 0, ".kmz": 1, ".kml": 2, ".geojson": 3}
_GPS_WORDS = re.compile(r"\bgps\b|course[- ]files?|gps[- ]files", re.I)


def _wp_search(fetcher):
    """[(title, link, html)] of posts and pages that mention GPS (WordPress REST API)."""
    out = []
    for kind in ("posts", "pages"):
        url = (f"{HOST}/wp-json/wp/v2/{kind}?search=gps&per_page=30&orderby=date&order=desc"
               "&_fields=title,link,content,date")
        try:
            data = fetcher.get(url, ttl=INDEX_TTL, accept="application/json").json()
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for d in data:
            try:
                out.append((re.sub(r"<[^>]+>", "", d["title"]["rendered"]), d["link"], d["content"]["rendered"],
                            d.get("date", "")))
            except (KeyError, TypeError):
                continue
    return out


def _pages_to_scan(fetcher):
    pages = list(SEED_PAGES)
    for start in [HOST + "/?s=gps"] + RACE_PAGES:
        try:
            text = fetcher.get(start, ttl=INDEX_TTL).text()
        except Exception:
            continue
        _, links = htmllinks.parse(text, start)
        for l in links:
            h = l["href"]
            if urllib.parse.urlsplit(h).hostname != urllib.parse.urlsplit(HOST).hostname:
                continue
            if htmllinks.is_course_file(h):
                continue
            if _GPS_WORDS.search(l["text"]) or "gps" in h.lower():
                if h.split("#")[0] not in pages:
                    pages.append(h.split("#")[0])
    return pages[:25]


def _files_on(title, page_url, html_text):
    """Course files linked from one page: [{ref, name, detail, ext}]."""
    _, links = htmllinks.parse(html_text, page_url)
    out = []
    for l in links:
        h = l["href"]
        if not htmllinks.is_course_file(h):
            continue
        path = urllib.parse.unquote(urllib.parse.urlsplit(h).path)
        base = path.rsplit("/", 1)[-1]
        stem, ext = re.match(r"(.*?)(\.[^.]+)$", base).groups()
        section = l.get("heading") or ""
        if section and section.lower() in (title or "").lower():
            section = ""
        # SCORE's 2021-style one-letter files (s / p / f): name them by their section heading
        label = section if len(stem) <= 2 and section else stem
        out.append({"ref": h, "stem": f"{page_url}|{path.rsplit('.', 1)[0].lower()}", "ext": ext.lower(),
                    "name": f"{title} - {label}".strip(" -"), "page": page_url})
    return out


def list_items(fetcher, ctx):
    found = []
    for title, link, content, _date in _wp_search(fetcher):
        found += _files_on(_title(title), link, content)
    if not found:
        for page in _pages_to_scan(fetcher):
            try:
                text = fetcher.get(page, ttl=INDEX_TTL).text()
            except Exception:
                continue
            title, _ = htmllinks.parse(text, page)
            found += _files_on(_title(title), page, text)
    # one item per course (the best format)
    best = {}
    for f in found:
        k = f["stem"]
        if k not in best or _PREF.get(f["ext"], 9) < _PREF.get(best[k]["ext"], 9):
            best[k] = f
    items = [{"id": f["ref"], "name": f["name"], "detail": f"{f['ext'][1:].upper()} - score-raceinfo.com",
              "kind": "course"} for f in best.values()]
    q = (ctx.get("q") or "").strip().lower()
    if q:
        items = [i for i in items if q in i["name"].lower()]
    return {"items": items, "note": NOTE if items else NOTE + " Nothing was found right now (the site may be down)."}


def _title(t):
    t = re.sub(r"\s*[|–—-]\s*SCORE.*$", "", t or "", flags=re.I).strip()
    return t or "SCORE course"


# A browser's User-Agent for a second try when the site answers a course file with a web page (a site's bot check)
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
GONE = ("SCORE's site sent a web page instead of this course file: SCORE has probably replaced it with a newer one. "
        "Open Courses > SCORE again for the current list.")


def _index_urls():
    """The listing's pages (list_items): dropped from the cache when a file they named is gone."""
    out = [f"{HOST}/wp-json/wp/v2/{kind}?search=gps&per_page=30&orderby=date&order=desc&_fields=title,link,content,date"
           for kind in ("posts", "pages")]
    return out + [HOST + "/?s=gps"] + RACE_PAGES + SEED_PAGES


def _stem(url):
    base = urllib.parse.unquote(urllib.parse.urlsplit(url).path).rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0].lower()


def _from_page(fetcher, ref, page_url, html_text):
    """The course file a web page served in its place points to (WordPress answers a replaced attachment with its
    page): the link with the same name (any format, GPX first), or None."""
    want = _stem(ref)
    found = [f for f in _files_on("", page_url, html_text) if _stem(f["ref"]) == want and f["ref"] != ref]
    found.sort(key=lambda f: _PREF.get(f["ext"], 9))
    for f in found:
        try:
            r = fetcher.get(f["ref"], ttl=FILE_TTL)
        except Exception:
            continue
        if not trackparse.looks_like_html(r.body):
            return r, f["ref"]
        fetcher.forget(f["ref"])
    return None


def get(fetcher, ref, ctx):
    """The course file ref. SCORE's site has answered a file it replaced (or a bot check) with a web page (the user,
    2026-10-26: "some tracks from score worked before but now show this error": "not a valid GPX/KML file
    (mismatched tag ...)"): that page is not kept in the cache, the file it links under the same name is taken, else the
    file is asked for again as a browser would; else the listing is refreshed and the player told why."""
    if not ref.lower().startswith(("http://", "https://")):
        raise trackparse.TrackError("bad SCORE file reference")
    resp = fetcher.get(ref, ttl=FILE_TTL)
    used = ref
    if trackparse.looks_like_html(resp.body):
        fetcher.forget(ref)
        got = _from_page(fetcher, ref, resp.url or ref, resp.text())
        if got is None:
            try:
                again = fetcher.get(ref, ttl=None, headers={"User-Agent": BROWSER_UA, "Accept": "*/*"})
                if not trackparse.looks_like_html(again.body):
                    got = (again, ref)
            except Exception:
                pass
        if got is None:
            for u in _index_urls():
                fetcher.forget(u)
            raise trackparse.TrackError(GONE)
        resp, used = got
    name = urllib.parse.unquote(urllib.parse.urlsplit(used).path).rsplit("/", 1)[-1]
    track = trackparse.parse(resp.body, name, source=ID, source_url=used, attribution=ATTRIBUTION)
    return track
