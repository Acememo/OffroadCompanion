"""OpenStreetMap through the Overpass API: one door for the circuits, the streets and the dirt track's roads.

The user, 2026-10-22: "cannot reach overpass.kumi.systems: The read operation timed out". The public servers are often
busy (the main one says so on its own page) and some go away (kumi.systems is no longer on the OpenStreetMap wiki's list
of public instances). So:
  - the worldwide public instances from the wiki, the one that answered last tried first;
  - a server that failed is left alone for BACKOFF_S (unless every server has failed);
  - each try has its own time limit; a server that was busy (HTTP 502 / 504, a timeout) is tried once more, with
    more patience, after a short wait;
  - an answer cached from any server is used before asking any; when none answers, an older cached answer is used.
Raises FetchError naming every server tried and what each said.
"""
import threading
import time
import urllib.parse

from .fetch import FetchError

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",                     # the main instance (FOSSGIS)
    "https://overpass.private.coffee/api/interpreter",             # Private.coffee: no rate limit
]
# (VK Maps' maps.mail.ru was tried too: its certificate chain does not verify on Windows' Python, the user 2026-10-22:
# "CERTIFICATE_VERIFY_FAILED ... self-signed certificate in certificate chain"; kumi.systems no longer answers)
PASSES = ((25, 0.0), (60, 4.0))  # (time limit of each try, s to wait first): a busy server (HTTP 502/504, a timeout)
                                 # often answers a second, patient try
BACKOFF_S = 120
PARALLEL_FIRST = True

_lock = threading.Lock()
_failed = {}                # endpoint -> monotonic time it last failed
_good = None                # the endpoint that answered last


def _host(url):
    return urllib.parse.urlsplit(url).hostname or url


def order(now=None):
    """The endpoints in the order to try: the last good one first, those that failed recently last."""
    now = time.monotonic() if now is None else now
    with _lock:
        good, failed = _good, dict(_failed)
    eps = list(ENDPOINTS)
    if good in eps:
        eps.remove(good)
        eps.insert(0, good)
    fresh = [e for e in eps if now - failed.get(e, -1e9) >= BACKOFF_S]
    tired = [e for e in eps if e not in fresh]
    return fresh + tired


def _cached(fetcher, ep, data, ttl):
    read = getattr(fetcher, "_cache_read", None)
    if read is None:
        return None
    try:
        return read(ep, data, ttl)
    except Exception:
        return None


def run(fetcher, q, ttl=7 * 24 * 3600, what="OpenStreetMap"):
    """The JSON answer of Overpass QL query q."""
    data = "data=" + urllib.parse.quote(q)
    for ep in ENDPOINTS:                         # (an answer cached from any server)
        got = _cached(fetcher, ep, data, ttl)
        if got is not None:
            try:
                return got.json()
            except ValueError:
                pass
    errors = {}
    busy = set(ENDPOINTS)                        # (worth a second, patient try: busy or slow, not broken)

    def one(ep, limit):
        try:
            try:
                r = fetcher.get(ep, ttl=ttl, data=data, timeout=limit)
            except TypeError:                    # (a fetcher without timeout=)
                r = fetcher.get(ep, ttl=ttl, data=data)
            out = r.json()
            if isinstance(out, dict) and out.get("remark") and not out.get("elements"):
                raise FetchError(str(out["remark"])[:120], 504)       # (Overpass's own "runtime error: timeout")
            return ep, out, None
        except (FetchError, ValueError) as e:
            return ep, None, e

    def failed(ep, e):
        with _lock:
            _failed[ep] = time.monotonic()
        host = _host(ep)
        msg = str(e).replace("cannot reach " + host + ": ", "")
        errors[host] = msg
        status = getattr(e, "status", None)
        if status in (429, 502, 503, 504) or "timed out" in msg.lower() or "temporarily" in msg.lower():
            busy.add(ep)

    def won(ep, out):
        global _good
        with _lock:
            _good = ep
            _failed.pop(ep, None)
        return out

    for n, (limit, wait) in enumerate(PASSES):
        eps = [e for e in order() if e in busy]
        if not eps:
            break
        if wait:
            time.sleep(wait)
        busy = set()
        if n == 0 and len(eps) > 1 and PARALLEL_FIRST:
            # the first pass asks every server at once (one request each): the first answer wins, a busy day costs
            # one time limit, not one per server
            import concurrent.futures as cf
            pool = cf.ThreadPoolExecutor(max_workers=len(eps))
            futs = [pool.submit(one, ep, limit) for ep in eps]
            try:
                for f in cf.as_completed(futs):
                    ep, out, e = f.result()
                    if out is not None:
                        return won(ep, out)
                    failed(ep, e)
            finally:
                pool.shutdown(wait=False)
            continue
        for ep in eps:
            ep, out, e = one(ep, limit)
            if out is not None:
                return won(ep, out)
            failed(ep, e)
    for ep in ENDPOINTS:                         # (none answered: an older answer, if any)
        got = _cached(fetcher, ep, data, -1)
        if got is not None:
            try:
                return got.json()
            except ValueError:
                pass
    detail = "; ".join(f"{h}: {m}" for h, m in errors.items())
    import logging
    logging.getLogger("gpsd.overpass").warning("%s: no Overpass server answered (%s)", what, detail)
    # (since about 2026-10-10 the public Overpass servers have been failing for many apps: overpass-api.de refusing or
    # answering 502, the mirrors timing out)
    raise FetchError("OpenStreetMap's map servers (Overpass) are not answering right now; they have been failing for "
                     "many apps lately. Try again later: once they answer, the result is kept for a week. "
                     "Courses from race.mx, SCORE and your own files still load.")


def reset():
    """(tests)"""
    global _good
    with _lock:
        _failed.clear()
        _good = None
