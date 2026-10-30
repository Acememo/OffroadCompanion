"""Small geodesy helpers for course lines (metres on a local equirectangular plane: plenty below ~50 km per step)."""
import math

R_EARTH = 6371008.8
MILE_M = 1609.344


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def cumulative(points):
    """[0, d1, d1+d2, ...] metres along points [(lat, lon, ...)]."""
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + haversine(a[0], a[1], b[0], b[1]))
    return out


class Plane:
    """A local x (east) / y (north) metre plane around a reference latitude."""

    def __init__(self, lat_ref, lon_ref=0.0):
        self.lat_ref, self.lon_ref = lat_ref, lon_ref
        self.kx = math.radians(1) * R_EARTH * math.cos(math.radians(lat_ref))
        self.ky = math.radians(1) * R_EARTH

    def xy(self, lat, lon):
        return (lon - self.lon_ref) * self.kx, (lat - self.lat_ref) * self.ky


def simplify(points, tol_m):
    """Ramer-Douglas-Peucker on [(lat, lon, ...)] (iterative, extra fields kept)."""
    n = len(points)
    if n < 3 or tol_m <= 0:
        return list(points)
    pl = Plane(points[0][0], points[0][1])
    xy = [pl.xy(p[0], p[1]) for p in points]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tol_m * tol_m
    while stack:
        a, b = stack.pop()
        ax, ay = xy[a]
        bx, by = xy[b]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = xy[i]
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2)) if L2 > 0 else 0.0
            d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > best:
                best, bi = d, i
        if bi > 0 and best > tol2:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(points, keep) if k]


def project(points, cum, lat, lon, i0=0, i1=None, s_lo=None, s_hi=None):
    """Nearest spot on polyline points (segments i0..i1, and only the stretch s_lo..s_hi metres along when given)
    to (lat, lon): (s metres along, distance m, segment i)."""
    if len(points) == 1:
        return 0.0, haversine(points[0][0], points[0][1], lat, lon), 0
    pl = Plane(lat, lon)
    px, py = 0.0, 0.0
    best = (math.inf, 0.0, 0)
    i1 = len(points) - 1 if i1 is None else min(i1, len(points) - 1)
    for i in range(max(0, i0), i1):
        seg = cum[i + 1] - cum[i]
        t_lo, t_hi = 0.0, 1.0
        if seg > 0 and s_lo is not None:
            t_lo = max(0.0, (s_lo - cum[i]) / seg)
        if seg > 0 and s_hi is not None:
            t_hi = min(1.0, (s_hi - cum[i]) / seg)
        if t_lo > t_hi:
            continue
        ax, ay = pl.xy(points[i][0], points[i][1])
        bx, by = pl.xy(points[i + 1][0], points[i + 1][1])
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = ((px - ax) * dx + (py - ay) * dy) / L2 if L2 > 0 else 0.0
        t = max(t_lo, min(t_hi, t))
        d2 = (ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2
        if d2 < best[0]:
            best = (d2, cum[i] + t * seg, i)
    return best[1], math.sqrt(best[0]), best[2]
