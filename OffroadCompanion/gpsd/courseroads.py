"""Dirt tracks along a race course where no road runs: where to lay them and how wide. Pure Python (no numpy), so the
same plan comes out in BeamNG.Earth's server (earthpatch.py: the track goes into its road data) and in the companion
(paintsource.py: for BeamNG.Earth's packaged .exe, the game mod draws the track as dirt DecalRoads).

The course is resampled every STEP_M metres and cut into windows of WINDOW samples. Per window:

  1. covered: a sample lies on a road that is already drawn (within its half width + COVER_PAD_M, running the same
     way within COVER_DEG): no track there, the course follows that road;
  2. the paint mask: short covered gaps filled (GAP_FILL samples), short painted runs dropped (MIN_RUN), each run
     reaching EXTEND samples onto the road it leaves or joins;
  3. terrain clearance: at each sample, how far the ground stays near the track's height (and free of trees taller
     than TREE_M, when there is canopy data) on each side, out to SIDE_M: a flat open plain gives the full room, a
     hillside or a canyon floor a few metres, a forest the gap between trees;
  4. width from the clearance (WIDTH_MIN .. WIDTH_MAX m, times the player's size setting), smoothed along the
     course and stepped in WIDTH_Q m;
  5. pieces: each painted run cut where its width steps: {id, w, ll: [[lon, lat]...], z: [m...]}.

Every step for a sample looks at most CONTEXT samples either way, and a window is computed with that much context
around it, so a window's pieces are the same whichever caller, process or order asked first; neighbouring windows'
pieces meet at their shared sample. Deterministic given the course, the roads and the elevation.
"""
import bisect
import hashlib
import math

from . import terrain

ALGO = 4                    # bump when the pieces a course gives change (3: unpaved roads followed from further;
                            # 4: a run's ends bend onto the road it leaves or joins)
STEP_M = 10.0
WINDOW = 100                # samples per window (1 km)
CONTEXT = 20                # samples of context each side (>= every step's reach below)
COVER_PAD_M = 5.0
COVER_DEG = 35.0
# A dirt road beside the course (unpaved: a segment's 6th value 0) is the course's road from further off, a recorded GPS
# line often runs 10-20 m off the dirt road it followed: no second track laid beside it, that road is the course's (the
# user, 2026-10-22: "it should assume it's the same track and roughify the original making no second one"). Paved roads
# keep the narrow rule (a course in the desert beside a highway is not on the highway).
FOLLOW_UNPAVED_M = 25.0
FOLLOW_UNPAVED_DEG = 25.0
GAP_FILL = 3                # a covered run this short between painted ones is painted through
MIN_RUN = 5                 # a painted run shorter than this is left out (the course cutting a corner)
EXTEND = 1                  # samples a run reaches onto the road at each end (where it does not bend onto it, below)
# A painted run that ends where the course takes a road bends onto that road's middle over the last samples, so the
# track joins the road it meets instead of stopping beside it (the user, 2026-10-22: "when a road ends because it
# reaches another road it should connect ... connect with the incoming and then split into the other"); the same where
# a run leaves a road. JOIN_SLOPE_M of sideways move per sample (a road 25 m off: 5 samples, 50 m), at most JOIN_MAX
# samples and at most half the road stretch before the next run (the two never meet on the road).
JOIN_SLOPE_M = 6.0
JOIN_MAX = 5
SIDE_M = 16.0
SIDE_STEP_M = 2.0
RISE_M = 1.0                # the ground within RISE_M + RISE_GRADE x offset of the track's height is room
RISE_GRADE = 0.08
TREE_M = 2.5
WIDTH_MIN, WIDTH_MAX = 3.0, 9.0
WIDTH_Q = 0.5
SMOOTH_MEDIAN, SMOOTH_MEAN = 3, 4    # half windows (samples)
DEM_ZOOM = 15
PAD_M = 80.0                # window bbox padding (the widest track's half width and its grading)
ID_PREFIX = "~egps"         # sorts after Overture's ids (hex / uuid): appended features keep a cell sorted
R_EARTH = 6371008.8
R_MERC = 6378137.0

assert CONTEXT >= SMOOTH_MEDIAN + SMOOTH_MEAN + 1 and CONTEXT > MIN_RUN + 2 * GAP_FILL + JOIN_MAX

# (terrain 8; the user, 2026-11-04, screenshots of a track the width of an ATV and of turns made of straight lines from
# point to point: "it shouldn't be this narrow on the majority of the track ... some turns need to be a bit more curvy
# and less like lines going through points")
CURVES_TV = 8
# Rounded turns: a course file's points are often 50-300 m apart, and the line between them turned on the spot at each
# one. From terrain 8 each such corner is an arc, as a driven trail takes it: as wide as the corner allows (CURVE_R_MAX)
# while staying within CURVE_DEV_M of the course's corner and using at most CURVE_ARM of each straight leading in and
# out; a hairpin keeps its point. The samples keep their distance along the course (the game's course, signs, crowds
# and turn notes count along the course file's own line) and move sideways onto the arc: Course.bend, m left of the
# course file's line, which the game is told with the track's middle (earth_gpsd course_sides).
CURVE_R_MAX = 250.0
CURVE_DEV_M = 12.0
CURVE_ARM = 0.5
CURVE_MIN_DEG = 2.0
# Wider tracks: the room beside the course (clearance) gives the width; from terrain 8 a track has the full width with
# less room (WIDTH_ROOM_V8: open desert with a little relief, a few bushes within 10 m), and is wider at both ends.
WIDTH_MIN_V8, WIDTH_MAX_V8 = 4.0, 10.0
WIDTH_ROOM_V8 = (4.0, 22.0)     # m of room: the narrowest .. the full width from


# -- the course -----------------------------------------------------------------------------------------------------
def course_id(points, scale, tv=None):
    """The course's ground's id: its line, its track size and the terrain version (terrain.VERSION)."""
    tv = terrain.VERSION if tv is None else int(tv)
    h = hashlib.sha1(f"T{tv}|{ALGO}|{scale:.3f}|".encode())
    for la, lo in points:
        h.update(f"{float(la):.6f},{float(lo):.6f};".encode())
    return h.hexdigest()[:12]


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def resample(points, step=STEP_M):
    """(lat list, lon list) every `step` metres along points [(lat, lon)] (first and last kept). Pure."""
    pts = [(float(a), float(b)) for a, b in points]
    if len(pts) < 2:
        return [p[0] for p in pts], [p[1] for p in pts]
    cum = [0.0]
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        cum.append(cum[-1] + haversine(a1, o1, a2, o2))
    total = cum[-1]
    n = max(2, int(math.floor(total / step)) + 1)
    ss = [i * step for i in range(n)]
    if total - ss[-1] > 0.5:
        ss.append(total)
    lat, lon = [], []
    for s in ss:
        j = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
        seg = cum[j + 1] - cum[j]
        f = (s - cum[j]) / seg if seg > 0 else 0.0
        f = min(1.0, max(0.0, f))
        lat.append(pts[j][0] + f * (pts[j + 1][0] - pts[j][0]))
        lon.append(pts[j][1] + f * (pts[j + 1][1] - pts[j][1]))
    return lat, lon


def rounded(points, lat, lon):
    """(lat, lon, bend) of the samples lat / lon (resample(points)) moved sideways onto the course's corners rounded to
    arcs (CURVE_* above), bend m left of the course's own line (0 away from a corner). Pure."""
    pts = []
    for la, lo in points:
        la, lo = float(la), float(lo)
        if not pts or haversine(pts[-1][0], pts[-1][1], la, lo) > 0.01:
            pts.append((la, lo))
    n = len(lat)
    bend = [0.0] * n
    lat, lon = list(lat), list(lon)
    m = len(pts)
    if m < 3 or n < 3:
        return lat, lon, bend
    cum = [0.0]
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        cum.append(cum[-1] + haversine(a1, o1, a2, o2))
    arcs = [None] * m
    for v in range(1, m - 1):
        pl = Plane(pts[v][0], pts[v][1])
        ax, ay = pl.xy(pts[v - 1][0], pts[v - 1][1])
        bx, by = pl.xy(pts[v + 1][0], pts[v + 1][1])
        a, b = math.hypot(ax, ay), math.hypot(bx, by)
        if a < 1e-6 or b < 1e-6:
            continue
        u0 = (-ax / a, -ay / a)                     # (in along the arm before, out along the arm after)
        u1 = (bx / b, by / b)
        dot = max(-1.0, min(1.0, u0[0] * u1[0] + u0[1] * u1[1]))
        delta = math.acos(dot)
        if delta < math.radians(CURVE_MIN_DEG) or delta > math.radians(179.0):
            continue
        half = delta / 2.0
        r = CURVE_R_MAX
        dev = 1.0 / math.cos(half) - 1.0
        if r * dev > CURVE_DEV_M:
            r = CURVE_DEV_M / dev
        t = r * math.tan(half)
        lim = CURVE_ARM * min(a, b)
        if t > lim:
            t = lim
            r = t / math.tan(half)
        if t < 0.5:
            continue
        side = 1.0 if u0[0] * u1[1] - u0[1] * u1[0] > 0 else -1.0     # (+ a left turn: the centre on the left)
        cx, cy = -u0[0] * t - u0[1] * r * side, -u0[1] * t + u0[0] * r * side
        arcs[v] = (pl, cx, cy, r, t, u0, u1)
    total = cum[-1]
    for k in range(n):
        s = min(k * STEP_M, total) if k < n - 1 else total
        j = min(max(bisect.bisect_right(cum, s) - 1, 0), m - 2)
        L = cum[j + 1] - cum[j]
        u = s - cum[j]
        got = None
        if arcs[j] is not None and u < arcs[j][4]:
            pl, cx, cy, r, t, u0, u1 = arcs[j]
            px, py, d = u1[0] * u, u1[1] * u, u1          # (on the arm after vertex j, u past it)
            got = (pl, px, py, cx, cy, r, d)
        elif j + 1 < m - 1 and arcs[j + 1] is not None and L - u < arcs[j + 1][4]:
            pl, cx, cy, r, t, u0, u1 = arcs[j + 1]
            px, py, d = -u0[0] * (L - u), -u0[1] * (L - u), u0     # (on the arm before vertex j + 1)
            got = (pl, px, py, cx, cy, r, d)
        if got is None:
            continue
        pl, px, py, cx, cy, r, d = got
        ex, ey = px - cx, py - cy
        e = math.hypot(ex, ey)
        if e < 1e-9:
            continue
        qx, qy = cx + r * ex / e, cy + r * ey / e
        bend[k] = d[0] * (qy - py) - d[1] * (qx - px)
        lat[k], lon[k] = pl.ll(qx, qy)
    return lat, lon, bend


class Course:
    """A course ready to paint: samples, windows and their boxes (lon0, lat0, lon1, lat1). From terrain CURVES_TV its
    samples lie on the course's corners rounded (rounded(): bend, m left of the file's line, per sample)."""

    def __init__(self, points, scale=1.0, name="Course", tv=None):
        self.name, self.scale = name or "Course", float(scale)
        # the terrain version its ground is made with (terrain.py: one this code still makes; the latest by default)
        tv = terrain.VERSION if tv is None else int(tv)
        self.tv = tv if tv in terrain.VERSIONS else terrain.VERSION
        self.tv_asked = tv
        self.cid = course_id(points, self.scale, self.tv)
        self.lat, self.lon = resample(points)
        self.bend = [0.0] * len(self.lat)
        if self.tv >= CURVES_TV:
            self.lat, self.lon, self.bend = rounded(points, self.lat, self.lon)
        self.n = len(self.lat)
        self.nwin = max(1, int(math.ceil((self.n - 1) / WINDOW)))
        self.boxes = []
        for k in range(self.nwin):
            a, b = self.inner(k)
            la, lo = self.lat[a:b + 1], self.lon[a:b + 1]
            pl = PAD_M / 111320.0
            po = PAD_M / (111320.0 * max(0.05, math.cos(math.radians(sum(la) / len(la)))))
            self.boxes.append((min(lo) - po, min(la) - pl, max(lo) + po, max(la) + pl))

    def inner(self, k):
        """Sample range [a, b] (inclusive) of window k: neighbouring windows share their end sample."""
        return k * WINDOW, min((k + 1) * WINDOW, self.n - 1)

    def context(self, k):
        a, b = self.inner(k)
        return max(0, a - CONTEXT), min(self.n - 1, b + CONTEXT)

    def windows_in(self, bounds):
        """Windows whose box meets bounds (lon0, lat0, lon1, lat1)."""
        x0, y0, x1, y1 = bounds
        return [k for k, (a, b, c, d) in enumerate(self.boxes) if a <= x1 and c >= x0 and b <= y1 and d >= y0]

    def windows_near(self, lat, lon, radius_m):
        dlat = radius_m / 111320.0
        dlon = radius_m / (111320.0 * max(0.05, math.cos(math.radians(lat))))
        return self.windows_in((lon - dlon, lat - dlat, lon + dlon, lat + dlat))


# -- a local plane around a window --------------------------------------------------------------------------------
class Plane:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = math.radians(1) * R_EARTH * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * R_EARTH

    def xy(self, lat, lon):
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def ll(self, x, y):
        return self.lat0 + y / self.ky, self.lon0 + x / self.kx


def directions(x, y):
    """Unit tangent (tx, ty) lists per sample (central differences, one-sided at the ends). Pure."""
    n = len(x)
    tx, ty = [0.0] * n, [1.0] * n
    for i in range(n):
        a, b = max(0, i - 1), min(n - 1, i + 1)
        dx, dy = x[b] - x[a], y[b] - y[a]
        L = math.hypot(dx, dy)
        if L > 1e-9:
            tx[i], ty[i] = dx / L, dy / L
    return tx, ty


# -- 1. covered by a road -----------------------------------------------------------------------------------------
GRID_M = 64.0


def follow_rule(seg):
    """(pad m, cos of the angle) a sample needs to be on segment seg (ax, ay, bx, by, half width[, paved]): a dirt road
    from further off (FOLLOW_UNPAVED_M) when the segment says it is unpaved."""
    if len(seg) > 5 and not seg[5]:
        return FOLLOW_UNPAVED_M, math.cos(math.radians(FOLLOW_UNPAVED_DEG))
    return COVER_PAD_M, math.cos(math.radians(COVER_DEG))


def covered(x, y, tx, ty, segs):
    """Per sample: lies on one of segs [(ax, ay, bx, by, half width[, paved])] running its way (follow_rule). Pure."""
    return [j >= 0 for j in cover_index(x, y, tx, ty, segs)]


def cover_index(x, y, tx, ty, segs):
    """Per sample: the index in segs of the nearest segment it lies on running its way (follow_rule), -1 for none.
    Pure."""
    n = len(x)
    out = [-1] * n
    if segs is None or len(segs) == 0 or n == 0:
        return out
    rules = [follow_rule(sg) for sg in segs]
    grid = {}
    for j, sg in enumerate(segs):
        ax, ay, bx, by, hw = sg[:5]
        r = hw + rules[j][0]
        for gx in range(int(math.floor((min(ax, bx) - r) / GRID_M)), int(math.floor((max(ax, bx) + r) / GRID_M)) + 1):
            for gy in range(int(math.floor((min(ay, by) - r) / GRID_M)), int(math.floor((max(ay, by) + r) / GRID_M)) + 1):
                grid.setdefault((gx, gy), []).append(j)
    for i in range(n):
        px, py = x[i], y[i]
        best = None
        for j in grid.get((int(math.floor(px / GRID_M)), int(math.floor(py / GRID_M))), ()):
            ax, ay, bx, by, hw = segs[j][:5]
            pad, cos_tol = rules[j]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 < 0.0025:
                continue
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            dist = math.hypot(ax + t * dx - px, ay + t * dy - py)
            if dist > hw + pad:
                continue
            if abs(tx[i] * dx + ty[i] * dy) / math.sqrt(L2) >= cos_tol:
                key = (round(dist, 3), ax, ay, bx, by)          # (nearest; the same pick whatever the list's order)
                if best is None or key < best[0]:
                    best = (key, j)
        if best is not None:
            out[i] = best[1]
    return out


def foot(px, py, seg):
    """The nearest point of segment seg (ax, ay, bx, by, ...) to (px, py). Pure."""
    ax, ay, bx, by = seg[:4]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return ax + t * dx, ay + t * dy


# -- 2. the paint mask ----------------------------------------------------------------------------------------------
def _runs(mask):
    """[(start, end_exclusive, value)] of a bool list. Pure."""
    out = []
    i, n = 0, len(mask)
    while i < n:
        j = i
        while j + 1 < n and mask[j + 1] == mask[i]:
            j += 1
        out.append((i, j + 1, bool(mask[i])))
        i = j + 1
    return out


def paint_mask(cov, at_start=True, at_end=True, extend=EXTEND):
    """The samples to paint from the covered ones. at_start / at_end: the list starts / ends at the course's own
    ends (else at a context edge: a run touching it is not known to end there). Pure."""
    paint = [not c for c in cov]
    n = len(paint)
    runs = _runs(paint)
    for j, (a, b, v) in enumerate(runs):            # fill short covered gaps between painted runs
        if not v and 0 < j < len(runs) - 1 and b - a <= GAP_FILL:
            paint[a:b] = [True] * (b - a)
    for a, b, v in _runs(paint):                    # drop short painted runs (both ends known)
        if v and b - a < MIN_RUN and (a > 0 or at_start) and (b < n or at_end):
            paint[a:b] = [False] * (b - a)
    out = list(paint)
    for a, b, v in _runs(paint):                    # reach onto the road at each end
        if v:
            for i in range(max(0, a - extend), min(n, b + extend)):
                out[i] = True
    return out


def joins(paint, cidx, x, y, segs, at_start=True, at_end=True):
    """Where each painted run (paint: from paint_mask(..., extend=0)) bends onto the road it joins or leaves.
    cidx: cover_index per sample. Returns (paint with the bends, mx, my, frac, road_hw): per sample the move (m) from
    the course line, how far onto the road (0 .. 1) and the road's half width (bend samples only). Pure (a sample looks
    at most JOIN_MAX + 2 * JOIN_MAX + 1 samples either way)."""
    n = len(paint)
    out = list(paint)
    mx, my, frac, rhw = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
    runs = _runs(paint)

    def smooth(t):
        return t * t * (3.0 - 2.0 * t)

    def bend(edge, step, gap_len, closed):
        """The run's sample next to the road: edge (first road sample); step +1 (the run ends) / -1 (it starts)."""
        cov_run = 0
        q = edge
        while 0 <= q < n and cidx[q] >= 0 and cov_run < gap_len:
            cov_run += 1
            q += step
        if cov_run == 0:
            return
        fx, fy = foot(x[edge], y[edge], segs[cidx[edge]])
        m = max(1, min(JOIN_MAX, int(math.ceil(math.hypot(fx - x[edge], fy - y[edge]) / JOIN_SLOPE_M - 1e-9))))
        m = min(m, cov_run, (gap_len - 1) // 2 if closed else gap_len)
        for j in range(1, m + 1):
            q = edge + step * (j - 1)
            sg = segs[cidx[q]]
            fx, fy = foot(x[q], y[q], sg)
            f = smooth(j / m)
            mx[q], my[q], frac[q], rhw[q] = f * (fx - x[q]), f * (fy - y[q]), f, float(sg[4])
            out[q] = True

    for r, (a, b, v) in enumerate(runs):
        if not v:
            continue
        if b < n:                                   # the run ends: onto the road after it
            ga, gb, _ = runs[r + 1]
            bend(b, 1, gb - ga, gb < n)             # (closed: another run after the road stretch)
        if a > 0:                                   # the run starts: off the road before it
            ga, gb, _ = runs[r - 1]
            bend(a - 1, -1, gb - ga, ga > 0)
    return out, mx, my, frac, rhw


# -- 3. terrain clearance -------------------------------------------------------------------------------------------
def side_offsets():
    return [k * SIDE_STEP_M for k in range(1, int(SIDE_M / SIDE_STEP_M) + 1)]


def clearance(zc, zl, zr, cl=None, cr=None):
    """Room (m) per sample: zc [n], zl / zr [n][k] the ground at side_offsets() left / right, cl / cr [n][k] canopy
    heights there (None: no tree data). A side's room ends at the first offset whose ground leaves the band
    RISE_M + RISE_GRADE x offset around the track's height or carries a tree. Pure."""
    off = side_offsets()
    band = [RISE_M + RISE_GRADE * d for d in off]

    def side(z0, zs, cs):
        first = len(off)
        for q in range(len(off)):
            if abs(zs[q] - z0) > band[q] or (cs is not None and cs[q] > TREE_M):
                first = q
                break
        return off[first - 1] + SIDE_STEP_M / 2 if first > 0 else SIDE_STEP_M / 2
    return [side(zc[i], zl[i], cl[i] if cl is not None else None) +
            side(zc[i], zr[i], cr[i] if cr is not None else None) for i in range(len(zc))]


# Round the trees (terrain 4; the user, 2026-10-28, a screenshot of trees standing in the middle of the track: "the road
# should go around the trees or if there is no room, then remove the ones on the course"). Where the course line runs
# into trees (the canopy over TREE_M on the line or within WEAVE_CLEAR_M of it), the track moves sideways, up to
# WEAVE_MAX_M, to the nearest free strip of ground at about the line's height: on the side grid (SIDE_STEP_M apart),
# the shift spread over WEAVE_SPREAD samples either way and eased in and out, so the track bends round a tree or a
# grove the way a driven trail does. Where no strip is free, it stays on the line (the trees there are taken off the
# track: earthpatch, the vegetation hook). Pure; each sample's shift looks only at samples within WEAVE_SPREAD + 1.
WEAVE_FROM_TV = 4
WEAVE_MAX_M = 6.0
WEAVE_CLEAR_M = 2.0
WEAVE_SPREAD = 2


def weave_shifts(paint, frac, zc, zl, zr, cc, cl, cr):
    """Per sample: metres left (+) of the course line the track moves round the trees (0: stays). zc [n] / zl / zr
    [n][k] the ground on the line and at side_offsets() left / right; cc [n] / cl / cr the canopy there. Pure."""
    off = side_offsets()
    kk = len(off)
    step = SIDE_STEP_M
    n = len(zc)
    reach = int(round(WEAVE_MAX_M / step))
    near = int(round(WEAVE_CLEAR_M / step))

    def lateral(i):
        """(offsets m left +, canopy, ground) across sample i: right side, line, left side."""
        o = [-off[q] for q in range(kk - 1, -1, -1)] + [0.0] + list(off)
        c = [cr[i][q] for q in range(kk - 1, -1, -1)] + [cc[i]] + list(cl[i])
        z = [zr[i][q] for q in range(kk - 1, -1, -1)] + [zc[i]] + list(zl[i])
        return o, c, z

    raw = [0.0] * n
    for i in range(n):
        if not paint[i] or frac[i] > 0:
            continue
        o, c, z = lateral(i)
        mid = kk

        def free(j):
            if j - near < 0 or j + near >= len(o):
                return False
            if any(c[q] > TREE_M for q in range(j - near, j + near + 1)):
                return False
            return abs(z[j] - z[mid]) <= RISE_M + RISE_GRADE * abs(o[j])
        if free(mid):
            continue
        for d in range(1, reach + 1):
            # (the nearer side first; at the same distance the left, so every computer picks the same)
            if free(mid + d):
                raw[i] = o[mid + d]
                break
            if free(mid - d):
                raw[i] = o[mid - d]
                break
    # spread: a sample takes the largest shift within WEAVE_SPREAD (the side of the nearest), then eased (a 1-2-1 mean)
    wide = [0.0] * n
    for i in range(n):
        best = 0.0
        for d in range(0, WEAVE_SPREAD + 1):
            for j in ((i - d, i + d) if d else (i,)):
                if 0 <= j < n and raw[j] and abs(raw[j]) > abs(best):
                    best = raw[j]
            if best:
                break
        wide[i] = best if paint[i] and frac[i] == 0 else 0.0
    out = [0.0] * n
    for i in range(n):
        if not wide[i] and not any(wide[j] for j in (i - 1, i + 1) if 0 <= j < n):
            continue
        a = wide[i - 1] if i > 0 else wide[i]
        b = wide[i + 1] if i < n - 1 else wide[i]
        v = (a + 2 * wide[i] + b) / 4.0
        out[i] = round(v, 2) if paint[i] and frac[i] == 0 else 0.0
    return out


def shifted_sides(shift, zc, zl, zr, cc, cl, cr):
    """The ground and canopy beside each sample seen from its shifted track (shift m left), on the same side grid: what
    lies past the side grid's reach counts as not room (a high wall). Pure."""
    off = side_offsets()
    kk = len(off)
    step = SIDE_STEP_M
    WALL = 1e9
    nzc, nzl, nzr, ncl, ncr = [], [], [], [], []
    for i in range(len(zc)):
        o = [-off[q] for q in range(kk - 1, -1, -1)] + [0.0] + list(off)
        z = [zr[i][q] for q in range(kk - 1, -1, -1)] + [zc[i]] + list(zl[i])
        c = ([cr[i][q] for q in range(kk - 1, -1, -1)] + [cc[i]] + list(cl[i])) if cl is not None else None
        m = kk + int(round(shift[i] / step))
        nzc.append(z[m])

        def side(sgn):
            zs, cs = [], []
            for q in range(1, kk + 1):
                j = m + sgn * q
                inside = 0 <= j < len(o)
                zs.append(z[j] if inside else WALL)
                cs.append((c[j] if inside else 0.0) if c is not None else 0.0)
            return zs, cs
        a, ca = side(1)
        b, cb = side(-1)
        nzl.append(a)
        nzr.append(b)
        ncl.append(ca)
        ncr.append(cb)
    return nzc, nzl, nzr, (ncl if cl is not None else None), (ncr if cr is not None else None)


def widths(room, scale=1.0, tv=1):
    """Track width per sample from the room: WIDTH_MIN on a ledge, WIDTH_MAX on open ground, times scale, smoothed
    and stepped in WIDTH_Q (terrain CURVES_TV on: WIDTH_*_V8). Pure (only the CONTEXT samples either side reach a
    sample)."""
    full = 2 * (SIDE_M + SIDE_STEP_M / 2)
    lo = 2 * SIDE_STEP_M
    w0, w1 = WIDTH_MIN, WIDTH_MAX
    if tv >= CURVES_TV:
        (lo, full), w0, w1 = WIDTH_ROOM_V8, WIDTH_MIN_V8, WIDTH_MAX_V8
    w = [w0 + (w1 - w0) * min(1.0, max(0.0, (r - lo) / (full - lo))) for r in room]
    n = len(w)
    med = []
    for i in range(n):
        s = sorted(w[max(0, i - SMOOTH_MEDIAN):i + SMOOTH_MEDIAN + 1])
        m = len(s)
        med.append(s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2)
    out = []
    for i in range(n):
        part = med[max(0, i - SMOOTH_MEAN):min(n, i + SMOOTH_MEAN + 1)]
        v = min(14.0, max(2.5, sum(part) / len(part) * scale))
        out.append(math.floor(v / WIDTH_Q + 0.5) * WIDTH_Q)
    return out


# -- 5. pieces ------------------------------------------------------------------------------------------------------
def pieces(cid, k, lat, lon, paint, width, a, b, z=None, off=None):
    """The pieces of window k from its samples a..b (inclusive; lists indexed by sample). Each painted run cut where
    the width steps (the new width from the step's sample on); neighbouring pieces share a sample. Each piece names
    its first sample (i0) and, given off, how far left (m) of the course line each point lies (where it bends onto a
    road). Pure."""
    out = []
    j = 0
    i = a
    while i <= b:
        if not paint[i]:
            i += 1
            continue
        s = i
        while s + 1 <= b and paint[s + 1] and width[s + 1] == width[i]:
            s += 1
        e = s + 1 if (s + 1 <= b and paint[s + 1]) else s      # continues at a new width: ends on its first sample
        if e > i:
            p = {"id": f"{ID_PREFIX}{cid}{k:06d}{j:03d}", "w": float(width[i]), "i0": i,
                 "ll": [[round(float(lon[q]), 7), round(float(lat[q]), 7)] for q in range(i, e + 1)]}
            if z is not None:
                p["z"] = [round(float(z[q]), 2) for q in range(i, e + 1)]
            if off is not None and any(off[q] for q in range(i, e + 1)):
                p["off"] = [round(float(off[q]), 2) for q in range(i, e + 1)]
            out.append(p)
            j += 1
        i = e if e > s else s + 1
    return out


def window_pieces(course, k, road_segs_fn, elev_fn, canopy_fn=None):
    """Window k's pieces. road_segs_fn(lat0, lon0, lat1, lon1, plane) -> [(ax, ay, bx, by, half width)] of the drawn
    roads near (plane metres); elev_fn(lats, lons) -> heights (m); canopy_fn(lats, lons) -> heights (m) or None.
    Raises when data is missing (the caller tries again later)."""
    a, b = course.inner(k)
    c0, c1 = course.context(k)
    lat, lon = course.lat[c0:c1 + 1], course.lon[c0:c1 + 1]
    pl = Plane(sum(lat) / len(lat), sum(lon) / len(lon))
    xy = [pl.xy(la, lo) for la, lo in zip(lat, lon)]
    x, y = [p[0] for p in xy], [p[1] for p in xy]
    tx, ty = directions(x, y)
    pad = (PAD_M + 20.0) / 111320.0
    padlo = pad / max(0.05, math.cos(math.radians(pl.lat0)))
    segs = road_segs_fn(min(lat) - pad, min(lon) - padlo, max(lat) + pad, max(lon) + padlo, pl)
    cidx = cover_index(x, y, tx, ty, segs)
    cov = [j >= 0 for j in cidx]
    at_start, at_end = c0 == 0, c1 == course.n - 1
    paint = paint_mask(cov, at_start=at_start, at_end=at_end, extend=0)
    paint, mx, my, frac, rhw = joins(paint, cidx, x, y, segs, at_start, at_end)
    if not any(paint[a - c0:b - c0 + 1]):
        return []
    # clearance: the ground beside every sample (one elevation call)
    off = side_offsets()
    n, kk = len(x), len(off)
    qx, qy = list(x), list(y)
    for sgn in (1, -1):                                  # left (+ the left normal), then right
        for i in range(n):
            nx, ny = -ty[i] * sgn, tx[i] * sgn
            for d in off:
                qx.append(x[i] + nx * d)
                qy.append(y[i] + ny * d)
    q = [pl.ll(px, py) for px, py in zip(qx, qy)]
    qla, qlo = [p[0] for p in q], [p[1] for p in q]
    z = [float(v) for v in elev_fn(qla, qlo)]
    zc = z[:n]
    zl = [z[n + i * kk:n + (i + 1) * kk] for i in range(n)]
    zr = [z[n + n * kk + i * kk:n + n * kk + (i + 1) * kk] for i in range(n)]
    cl = cr = cc = None
    weave = course.tv >= WEAVE_FROM_TV
    if canopy_fn is not None:
        c = canopy_fn(qla if weave else qla[n:], qlo if weave else qlo[n:])      # (terrain 4: the line's own too)
        if c is not None:
            c = [float(v) for v in c]
            if weave:
                cc, c = c[:n], c[n:]
            cl = [c[i * kk:(i + 1) * kk] for i in range(n)]
            cr = [c[n * kk + i * kk:n * kk + (i + 1) * kk] for i in range(n)]
    shift = [0.0] * n
    if weave and cc is not None:
        shift = weave_shifts(paint, frac, zc, zl, zr, cc, cl, cr)
        if any(shift):
            zc, zl, zr, cl, cr = shifted_sides(shift, zc, zl, zr, cc, cl, cr)
    room = clearance(zc, zl, zr, cl, cr)
    w = widths(room, course.scale, getattr(course, "tv", 1))
    # where a run bends onto a road: the point moved, the width from the track's toward the road's, the height there
    LAT, LON = list(course.lat), list(course.lon)
    OFF = [0.0] * course.n
    bent = [i for i in range(n) if frac[i] > 0]
    for i in bent:
        LAT[c0 + i] = lat[i] + my[i] / pl.ky
        LON[c0 + i] = lon[i] + mx[i] / pl.kx
        OFF[c0 + i] = -ty[i] * mx[i] + tx[i] * my[i]
        e = i - 1 if i > 0 and paint[i - 1] and frac[i - 1] < frac[i] else i + 1     # (the run's side)
        while 0 <= e < n and frac[e] > 0:
            e += 1 if e > i else -1
        we = w[e] if 0 <= e < n else w[i]
        road = max(WIDTH_MIN * course.scale, 2.0 * rhw[i])
        v = we + (min(we, road) - we) * frac[i]                # (never wider than the track)
        w[i] = math.floor(v / WIDTH_Q + 0.5) * WIDTH_Q
    # round the trees (terrain 4): the track's points moved sideways by their shift, their heights there
    woven = [i for i in range(n) if shift[i] and frac[i] == 0]
    for i in woven:
        LAT[c0 + i] = lat[i] + tx[i] * shift[i] / pl.ky
        LON[c0 + i] = lon[i] - ty[i] * shift[i] / pl.kx
        OFF[c0 + i] = shift[i]
    if woven:
        zw = elev_fn([LAT[c0 + i] for i in woven], [LON[c0 + i] for i in woven])
        for i, v in zip(woven, zw):
            zc[i] = float(v)
    if bent:
        zb = elev_fn([LAT[c0 + i] for i in bent], [LON[c0 + i] for i in bent])
        for i, v in zip(bent, zb):
            zc[i] = float(v)
    P = [False] * course.n
    W = [0.0] * course.n
    Z = [0.0] * course.n
    P[c0:c1 + 1], W[c0:c1 + 1], Z[c0:c1 + 1] = paint, w, zc
    return pieces(course.cid, k, LAT, LON, P, W, a, b, Z, OFF)


def mercator(lat, lon):
    """Web Mercator metres of one point."""
    lat = min(85.05, max(-85.05, lat))
    return R_MERC * math.radians(lon), R_MERC * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def piece_box(p):
    xs = [q[0] for q in p["ll"]]
    ys = [q[1] for q in p["ll"]]
    return min(xs), min(ys), max(xs), max(ys)
