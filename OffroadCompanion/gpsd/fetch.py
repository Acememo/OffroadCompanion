"""The companion's one door to the network: polite per-host pacing, a small disk cache, one User-Agent.

The public services used here all ask for the same things: identify yourself, no more than about one request a
second, cache what you can. Every request goes through Fetcher.get(); a test passes a fake with the same method.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

def _version():
    """The companion's version (OffroadCompanion/VERSION: the release zip is named after it)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"),
                  encoding="utf-8") as f:
            return f.read().strip() or "0"
    except OSError:
        return "0"


VERSION = _version()
USER_AGENT = f"OffroadCompanion/{VERSION} (+https://github.com/TecnaGamer/BeamNG.Earth; a BeamNG.Earth add-on)"

# seconds between two requests to the same host (OSRM FOSSGIS and Overpass both ask for ~1/s or less)
HOST_INTERVAL = {
    "routing.openstreetmap.de": 1.1,
    "router.project-osrm.org": 1.1,
    "overpass-api.de": 2.0,
    "overpass.private.coffee": 1.0,
    "score-raceinfo.com": 1.0,
    "race.mx": 1.0,
    "s3.amazonaws.com": 0.25,       # (terrain tiles: a public bucket)
    "photon.komoot.io": 0.5,
    "api.open-meteo.com": 1.0,      # (the ground's wetness: once an hour or so per place)        # (search: made for search-as-you-type; the app sends one search at a time)
    "nominatim.openstreetmap.org": 1.1,   # (search on Enter only: its policy is 1/s at most, no autocomplete)
}
DEFAULT_INTERVAL = 1.0
TIMEOUT_S = 30
MAX_BYTES = 64 * 1024 * 1024


class FetchError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


class Response:
    def __init__(self, body, url, content_type="", from_cache=False):
        self.body, self.url, self.content_type, self.from_cache = body, url, content_type, from_cache

    def text(self):
        for enc in ("utf-8", "latin-1"):
            try:
                return self.body.decode(enc)
            except UnicodeDecodeError:
                continue
        return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.text())


class Fetcher:
    def __init__(self, cache_dir=None, offline=False):
        self.cache_dir = cache_dir
        self.offline = offline
        self._last = {}
        self._lock = threading.Lock()
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    # -- cache -------------------------------------------------------------------------------------------------
    def _cache_path(self, url, data):
        key = hashlib.sha1((url + "\0" + (data or "")).encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, key[:2], key)

    def _cache_read(self, url, data, ttl):
        if not self.cache_dir or ttl is None:
            return None
        p = self._cache_path(url, data)
        try:
            st = os.stat(p)
        except OSError:
            return None
        if ttl >= 0 and time.time() - st.st_mtime > ttl and not self.offline:
            return None
        try:
            with open(p, "rb") as f:
                body = f.read()
            with open(p + ".type", "r", encoding="utf-8") as f:
                ctype = f.read()
        except OSError:
            ctype = ""
        return Response(body, url, ctype, from_cache=True)

    def _cache_write(self, url, data, resp):
        if not self.cache_dir:
            return
        p = self._cache_path(url, data)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(resp.body)
        os.replace(tmp, p)
        with open(p + ".type", "w", encoding="utf-8") as f:
            f.write(resp.content_type or "")

    # -- network -----------------------------------------------------------------------------------------------
    def _pace(self, host):
        interval = HOST_INTERVAL.get(host, DEFAULT_INTERVAL)
        with self._lock:
            now = time.monotonic()
            wait = self._last.get(host, -1e9) + interval - now
            self._last[host] = max(now, self._last.get(host, -1e9) + interval)
        if wait > 0:
            time.sleep(wait)

    def forget(self, url, data=None):
        """The cached copy of url dropped (a bad answer kept: a web page instead of a file)."""
        if not self.cache_dir:
            return
        p = self._cache_path(url, data)
        for f in (p, p + ".type"):
            try:
                os.remove(f)
            except OSError:
                pass

    def get(self, url, ttl=None, data=None, accept=None, timeout=None, headers=None):
        """GET (or POST form `data`, a str) url -> Response. ttl: seconds a cached copy stays good (None: no
        cache, -1: forever); headers: more request headers (a User-Agent of its own). Raises FetchError."""
        cached = self._cache_read(url, data, ttl)
        if cached is not None:
            return cached
        if self.offline:
            raise FetchError(f"offline and not cached: {url}")
        host = urllib.parse.urlsplit(url).hostname or ""
        self._pace(host)
        headers = {"User-Agent": USER_AGENT, **(headers or {})}
        if accept:
            headers["Accept"] = accept
        body_bytes = data.encode("utf-8") if isinstance(data, str) else data
        if body_bytes is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(_quote_url(url), data=body_bytes, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or TIMEOUT_S) as r:
                body = r.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise FetchError(f"too large: {url}")
                resp = Response(body, r.geturl(), r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            raise FetchError(f"HTTP {e.code} from {host}", e.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FetchError(f"cannot reach {host}: {getattr(e, 'reason', e)}") from None
        if ttl is not None:
            try:
                self._cache_write(url, data, resp)
            except OSError:
                pass
        return resp


def _quote_url(url):
    """SCORE's file names have spaces ("26B5H-COMPLETE PROC-0604.kml"): quote the path, keep what is quoted."""
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/:@!$&'()*+,;=-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
