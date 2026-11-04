"""A clean, drivable corridor along the course, inside BeamNG.Earth's server (earthpatch.py; numpy).

Three things BeamNG.Earth builds from map data can stand in a race course's way:

  buildings          footprints (and building parts) within CLEAR_M of the course line are left out of the cell's
                     data, so they are never built (nor their yard fences, nor their collision meshes);
  short bridges      a road the map calls a bridge (Overture's is_bridge flag or a level above 0), at most
                     FLATTEN_MAX_M long, that the course crosses where the course is not itself on a road (a creek
                     crossing: in the map a bridge, often a ford or a low culvert in the world, and in the game a deck
                     with parapet walls the course runs into) is made a ground road there: no deck, no parapets, the
                     ground graded to it like any road, so the course crosses at grade. A course passing under a
                     bridge along a road (an underpass) keeps it;
  low overpasses     a short bridge over the road the course is on, or a motorway's the course passes under off the
                     roads (a wash under the highway), too low to pass under (HEADROOM_M), is a
                     junction at grade instead. Its ends are judged on the ground as BeamNG.Earth grades it: the road
                     below graded flat across its core and blended up 1:2 to the natural ground, so the ends of an
                     overpass over a highway in a cutting sit at the highway's height and its deck a metre over it
                     (the user's Carretera Tijuana - Ensenada, 2026-10-21);
  retaining walls    BeamNG.Earth's walls beside roads cut into the ground are left out where the course runs into
                     them (crossing them within CLEAR_M + WALL_PAD_M) and wherever one stands on the road the course
                     follows (a crossing road's wall reaching into a highway's lanes); walls alongside it stay;
  props              (BeamNG.Earth 1.8) its mapped props on the road tiles that stand in the way: a chain-link fence
                     or noise wall the course crosses (a gap where it goes through, the way a ranch gate is), yard
                     containers, barns, billboards, cell and water towers, picnic tables and bus shelters within
                     CLEAR_M (+ the prop's own half size, PROP_PAD_M) of the course line: props_off.

Pure given its inputs (feature tables, the course's lines); new tables are made, the cell's own are never changed.
"""
import math

import numpy as np

CLEAR_M = 6.0               # from the course line: room for a race truck and the GPS line's own error
ROUTE_CLEAR_M = 4.5         # from a GPS road route's centre line (it is on the road: buildings standing in the lanes)
FLATTEN_MAX_M = 150.0       # longer bridges (big rivers, valleys) are kept
CROSS_DEG = 30.0            # the course crosses a bridge at least this steeply (else it runs along it)
UNDERPASS_PAD_M = 5.0       # the course on a ground road (within its half width + this, aligned): an underpass ...
HEADROOM_M = 5.0            # ... kept when the deck can get this high over that road; lower, it is a wall across the
DECK_MAX_GRADE = 0.06       # road (BeamNG.Earth's decks climb at most this from their abutments: roads.DECK_MAX_GRADE,
                            # so a short overpass whose ends lie at the road's height in the elevation data, a highway
                            # in a cutting the 30 m data does not show, stays a metre over it) and the crossing is
                            # built at grade instead
HEADROOM_MARGIN_M = 1.5     # the deck's smoothing and grading's blending take some off: kept only with this to spare
SHOULDER_M = 1.0            # grading.SHOULDER_M: flat beyond the carriageway ...
SLOPE_RUN = 2.0             # ... then grading.SLOPE_RUN: 1:2 up to the natural ground
PROFILE_SIGMA_M = 12.0      # grading.SIGMA_M: a road's height profile smoothed along it
PROFILE_REACH_M, PROFILE_STEP_M = 24.0, 4.0
AT_GRADE_REACH_M = 12.0     # roads.AT_GRADE_REACH_M: a road this near an abutment is crossed at grade by BeamNG.Earth
WALL_PAD_M = 4.0
ON_ROAD_PAD_M = 1.0         # a wall within the followed road's half width + shoulder + this stands on it
SKIP_BRIDGE_CLASSES = {"motorway"}      # (off the roads only: an overpass of any class over the road is judged)


class Plane:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = math.radians(1) * 6371008.8 * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * 6371008.8

    def ll(self, x, y):
        return self.lon0 + x / self.kx, self.lat0 + y / self.ky

    def xy(self, lonlat):
        a = np.asarray(lonlat, np.float64)
        return np.stack([(a[:, 0] - self.lon0) * self.kx, (a[:, 1] - self.lat0) * self.ky], axis=1)


def course_lines(course, bounds, pad_m):
    """The course's lines (each (n, 2) lon / lat) near bounds (lon0, lat0, lon1, lat1), pad_m around."""
    x0, y0, x1, y1 = bounds
    dlat = pad_m / 111320.0
    dlon = pad_m / (111320.0 * max(0.05, math.cos(math.radians((y0 + y1) / 2))))
    ks = sorted(course.windows_in((x0 - dlon, y0 - dlat, x1 + dlon, y1 + dlat)))
    out, run = [], None
    for k in ks:
        a, b = course.inner(k)
        if run is not None and run[1] == a:
            run[1] = b
        else:
            if run:
                out.append(run)
            run = [a, b]
    if run:
        out.append(run)
    return [np.stack([np.asarray(course.lon[a:b + 1]), np.asarray(course.lat[a:b + 1])], axis=1)
            for a, b in out if b > a]


# (1.8's mapped props: fences.py, worldprops.py, picnic.py, shelters.py) group -> its half size (m) past CLEAR_M
PROP_PAD_M = {"chainlink": 1.5, "noisewall": 2.5, "container": 6.5, "barn": 7.0, "billboard": 3.0, "celltower": 3.0,
              "watertower": 6.0, "picnictable": 1.5, "picnicgrill": 1.0, "busshelter": 2.5}


def props_off(rows, lines, clear_m):
    """BeamNG.Earth's prop rows ([group, x, y, z, ...] in a frame) without those of PROP_PAD_M's groups within
    clear_m (+ their pad) of the lines ((n, 2) each, the same frame); the rest as they are, in order. Pure."""
    rows = list(rows or ())
    lines = [np.asarray(ln, np.float64) for ln in lines if len(ln) >= 2]
    if not rows or not lines:
        return rows
    pick = [i for i, r in enumerate(rows) if len(r) >= 3 and str(r[0]) in PROP_PAD_M]
    if not pick:
        return rows
    p = np.array([[float(rows[i][1]), float(rows[i][2])] for i in pick], np.float64)
    a = np.concatenate([ln[:-1] for ln in lines])
    b = np.concatenate([ln[1:] for ln in lines])
    d = np.full(len(p), np.inf)
    for j in range(0, len(a), 512):
        d = np.minimum(d, _seg_dist(p, a[j:j + 512], b[j:j + 512]).min(axis=1))
    pad = np.array([PROP_PAD_M[str(rows[i][0])] for i in pick])
    drop = {pick[k] for k in np.flatnonzero(d <= clear_m + pad)}
    return [r for i, r in enumerate(rows) if i not in drop]


def _seg_dist(p, a, b):
    """Distances (m) of points p (P, 2) to segments a -> b (S, 2) each: (P, S)."""
    d = b - a
    L2 = np.maximum((d * d).sum(axis=1), 1e-12)
    t = np.clip(((p[:, None, :] - a[None, :, :]) * d[None, :, :]).sum(axis=2) / L2[None, :], 0, 1)
    q = a[None, :, :] + t[:, :, None] * d[None, :, :]
    return np.hypot(*(q - p[:, None, :]).transpose(2, 0, 1))


def _cross(a1, a2, b1, b2):
    """(S1, S2) bool: segment a1->a2 [i] properly crosses b1->b2 [j]."""
    def orient(p, q, r):
        return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])
    A1, A2 = a1[:, None, :], a2[:, None, :]
    B1, B2 = b1[None, :, :], b2[None, :, :]
    o1, o2 = orient(A1, A2, B1), orient(A1, A2, B2)
    o3, o4 = orient(B1, B2, A1), orient(B1, B2, A2)
    # touching counts (a course vertex right on the road); both segments on one line (all zero) does not
    return (o1 * o2 <= 0) & (o3 * o4 <= 0) & ~((o1 == 0) & (o2 == 0))


def seg_seg_dist(a1, a2, b1, b2):
    """Min distance between any segment of a and any of b (0 when they cross)."""
    if len(a1) == 0 or len(b1) == 0:
        return math.inf
    if _cross(a1, a2, b1, b2).any():
        return 0.0
    d = min(_seg_dist(a1, b1, b2).min(), _seg_dist(a2, b1, b2).min(),
            _seg_dist(b1, a1, a2).min(), _seg_dist(b2, a1, a2).min())
    return float(d)


def inside(points, ring):
    """(P,) bool: points (P, 2) inside the closed ring (k, 2) (even-odd)."""
    x, y = points[:, 0][:, None], points[:, 1][:, None]
    a, b = ring[None, :-1, :], ring[None, 1:, :]
    cond = (a[..., 1] > y) != (b[..., 1] > y)
    xint = a[..., 0] + (y - a[..., 1]) * (b[..., 0] - a[..., 0]) / np.where(b[..., 1] == a[..., 1], 1e-12,
                                                                             b[..., 1] - a[..., 1])
    return ((cond & (x < xint)).sum(axis=1) % 2) == 1


# -- feature tables ---------------------------------------------------------------------------------------------
def subset(mapgeom, f, keep):
    """Features f with only the rows `keep` (sorted indices). Attributes, rules, own / clipped / en follow."""
    keep = np.asarray(keep, np.int64)
    part_counts = [int(f.part_off[i + 1] - f.part_off[i]) for i in keep]
    ring_counts = [int(f.ring_off[p + 1] - f.ring_off[p]) for i in keep for p in range(f.part_off[i], f.part_off[i + 1])]
    coord_idx = [np.arange(f.coord_off[r], f.coord_off[r + 1]) for i in keep
                 for p in range(f.part_off[i], f.part_off[i + 1]) for r in range(f.ring_off[p], f.ring_off[p + 1])]
    coord_counts = [len(c) for c in coord_idx]
    ci = np.concatenate(coord_idx) if coord_idx else np.zeros(0, np.int64)
    out = mapgeom.Features(
        f.layer, f.ids[keep], f.kind[keep],
        np.r_[0, np.cumsum(part_counts)].astype(np.int64), np.r_[0, np.cumsum(ring_counts)].astype(np.int64),
        np.r_[0, np.cumsum(coord_counts)].astype(np.int64), f.lonlat[ci],
        f.en[ci] if f.en is not None else None,
        f.own[keep] if f.own is not None else None, f.clipped[keep] if f.clipped is not None else None)
    out.attrs = {k: np.asarray(v)[keep] for k, v in f.attrs.items()}
    remap = np.full(len(f), -1, np.int64)
    remap[keep] = np.arange(len(keep))
    rules = {}
    for name, t in f.rules.items():
        fe = np.asarray(t.feature, np.int64)
        m = remap[fe] >= 0 if len(fe) else np.zeros(0, bool)
        rules[name] = mapgeom.RuleTable(remap[fe[m]].astype(np.int32), np.asarray(t.value)[m],
                                        np.asarray(t.start)[m], np.asarray(t.end)[m])
    out.rules = rules
    return out


def _feature_boxes(f):
    """(n, 4) lon0, lat0, lon1, lat1 of every feature (all its coordinates)."""
    n = len(f)
    if n == 0:
        return np.zeros((0, 4))
    c0 = f.coord_off[f.ring_off[f.part_off[:-1]]]
    c1 = f.coord_off[f.ring_off[f.part_off[1:]]]
    out = np.full((n, 4), np.nan)
    for i, (a, b) in enumerate(zip(c0, c1)):
        if b > a:
            ll = f.lonlat[a:b]
            out[i] = (ll[:, 0].min(), ll[:, 1].min(), ll[:, 0].max(), ll[:, 1].max())
    return out


# -- buildings --------------------------------------------------------------------------------------------------------
def buildings_off(f, lines, clear_m=CLEAR_M):
    """Indices of the features of f (building footprints / parts) within clear_m of the course lines. Pure."""
    if f is None or len(f) == 0 or not lines:
        return []
    allpts = np.concatenate(lines)
    lat0, lon0 = float(allpts[:, 1].mean()), float(allpts[:, 0].mean())
    pl = Plane(lat0, lon0)
    segs = [pl.xy(ln) for ln in lines]
    s1 = np.concatenate([s[:-1] for s in segs])
    s2 = np.concatenate([s[1:] for s in segs])
    sbox = np.stack([np.minimum(s1, s2).min(axis=0), np.maximum(s1, s2).max(axis=0)])
    boxes = _feature_boxes(f)
    pad_lat = clear_m / 111320.0
    pad_lon = clear_m / (111320.0 * max(0.05, math.cos(math.radians(lat0))))
    c0 = pl.xy(np.stack([boxes[:, 0] - pad_lon, boxes[:, 1] - pad_lat], axis=1))
    c1 = pl.xy(np.stack([boxes[:, 2] + pad_lon, boxes[:, 3] + pad_lat], axis=1))
    cand = np.flatnonzero(np.isfinite(boxes[:, 0]) & (c1[:, 0] >= sbox[0, 0]) & (c0[:, 0] <= sbox[1, 0]) &
                          (c1[:, 1] >= sbox[0, 1]) & (c0[:, 1] <= sbox[1, 1]))
    out = []
    for i in cand:
        lo = np.minimum(s1, s2)
        hi = np.maximum(s1, s2)
        near = (hi[:, 0] >= c0[i, 0]) & (lo[:, 0] <= c1[i, 0]) & (hi[:, 1] >= c0[i, 1]) & (lo[:, 1] <= c1[i, 1])
        if not near.any():
            continue
        a1, a2 = s1[near], s2[near]
        hit = False
        for part in f.parts(int(i)):
            if not part or len(part[0]) < 2:
                continue
            ring = pl.xy(part[0])
            if len(ring) >= 4 and np.allclose(ring[0], ring[-1]) and inside(np.concatenate([a1, a2[-1:]]), ring).any():
                hit = True
            elif seg_seg_dist(ring[:-1], ring[1:], a1, a2) <= clear_m:
                hit = True
            if hit:
                break
        if hit:
            out.append(int(i))
    return out


# -- toll plazas: kept ---------------------------------------------------------------------------------------------
# BeamNG.Earth (1.5.5) draws a toll plaza as West Coast USA's toll booths: from the map's islands (low "buildings")
# with the booths (building parts) standing on them (server buildings._toll_islands, these thresholds). The clearing
# left them out (they stand in the lanes the route runs through), so no booth was drawn; they are kept now, with
# the plaza's flat footprint (never drawn; on the Golden Gate the booths are its parts).
TOLL_ISLAND_MAX_H = 1.0
TOLL_ISLAND_MIN_L = 8.0
TOLL_ISLAND_MAX_W = 4.0
TOLL_BOOTH_H = (2.0, 8.0)
TOLL_BOOTH_MAX_AREA = 40.0
FLAT_FOOTPRINT_M = 0.1
FLOOR_M = 3.0


def _attr(f, name, i):
    a = f.attrs.get(name) if f is not None else None
    if a is None:
        return np.nan
    try:
        return float(a[i])
    except (TypeError, ValueError):
        return np.nan


def _cls(f, i):
    a = f.attrs.get("class") if f is not None else None
    return str(a[i]) if a is not None else ""


def _top(f, i):
    """A footprint's or part's top (m above the ground), or nan."""
    h = _attr(f, "height", i)
    if np.isfinite(h) and h > 0:
        return h
    nf = _attr(f, "num_floors", i)
    return nf * FLOOR_M if np.isfinite(nf) and nf > 0 else np.nan


def _outer(f, i, pl):
    parts = f.parts(int(i))
    if not parts or not parts[0] or len(parts[0][0]) < 4:
        return None
    return pl.xy(np.asarray(parts[0][0], np.float64))


def _obox(ring):
    """(centre, unit long axis, half length, half width) of a ring (k, 2), closed or not."""
    q = ring[:-1] if len(ring) > 1 and np.allclose(ring[0], ring[-1]) else ring
    c = q.mean(axis=0)
    d = q - c
    w, v = np.linalg.eigh(d.T @ d)
    u = v[:, int(np.argmax(w))]
    n = np.array([-u[1], u[0]])
    a, b = d @ u, d @ n
    return c + u * (a.max() + a.min()) / 2 + n * (b.max() + b.min()) / 2, u, (a.max() - a.min()) / 2, \
        (b.max() - b.min()) / 2


def _on(p, box, pad=1.0):
    c, u, hl, hw = box
    d = np.asarray(p, np.float64) - c
    return abs(float(d @ u)) <= hl + pad and abs(float(d[0] * u[1] - d[1] * u[0])) <= hw + pad


def _area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2


def toll_plaza(blds, parts, lat0, lon0):
    """The ids to keep of a toll plaza among footprints (blds: list of Features) and building parts (parts): the
    islands (low, long, narrow footprints with a booth on them), their booths (small parts 2-8 m tall centred on an
    island), and flat footprints (under FLAT_FOOTPRINT_M: a plaza's area, never drawn). Pure."""
    pl = Plane(lat0, lon0)
    keep = set()
    islands = []
    for f in blds:
        if f is None or len(f) == 0:
            continue
        for i in range(len(f)):
            h = _top(f, i)
            if _cls(f, i) == "toll_booth" or (np.isfinite(h) and h < FLAT_FOOTPRINT_M):
                keep.add(str(f.ids[i]))
                continue
            if not (np.isfinite(h) and 0 < h <= TOLL_ISLAND_MAX_H):
                continue
            r = _outer(f, i, pl)
            if r is None:
                continue
            box = _obox(r)
            if 2 * box[2] >= TOLL_ISLAND_MIN_L and 2 * box[3] <= TOLL_ISLAND_MAX_W:
                islands.append((str(f.ids[i]), box))
    booths = []
    for f in parts:
        if f is None or len(f) == 0:
            continue
        for i in range(len(f)):
            if _cls(f, i) == "toll_booth":
                keep.add(str(f.ids[i]))
                continue
            top = _top(f, i)
            if not (np.isfinite(top) and TOLL_BOOTH_H[0] <= top <= TOLL_BOOTH_H[1]):
                continue
            r = _outer(f, i, pl)
            if r is None or _area(r) > TOLL_BOOTH_MAX_AREA:
                continue
            q = r[:-1] if np.allclose(r[0], r[-1]) else r
            booths.append((str(f.ids[i]), q.mean(axis=0)))
    for iid, box in islands:
        on = [bid for bid, c in booths if _on(c, box)]
        if on:
            keep.add(iid)
            keep.update(on)
    return keep


def toll_like(f, i):
    """Could feature i of f (a footprint or a part) belong to a toll plaza (worth reading its neighbours for)?"""
    h = _top(f, i)
    if np.isfinite(h) and (h <= TOLL_ISLAND_MAX_H or TOLL_BOOTH_H[0] <= h <= TOLL_BOOTH_H[1]):
        return True
    return _cls(f, i) == "toll_booth"


# -- bridges ----------------------------------------------------------------------------------------------------------
def bridges_to_flatten(roadsmod, f, lines, ground_fn=None, flatten_max_m=FLATTEN_MAX_M, elev_fn=None):
    """Indices of the road features of f whose bridge the course crosses off-road, or over the road the course is on
    too low to pass under (see the module doc). ground_fn(lon, lat) -> (M, 5) lon0, lat0, lon1, lat1, half width of
    the ground roads near the crossing (the underpass test; asked about the crossing point itself, so every cell
    holding the bridge decides alike); elev_fn(lats, lons) -> heights (m): the headroom test (without it an
    underpass is kept). Pure given those."""
    if f is None or len(f) == 0 or not lines:
        return []
    allpts = np.concatenate(lines)
    pl = Plane(float(allpts[:, 1].mean()), float(allpts[:, 0].mean()))
    cs = [pl.xy(ln) for ln in lines]
    c1 = np.concatenate([s[:-1] for s in cs])
    c2 = np.concatenate([s[1:] for s in cs])
    cls = f.attrs.get("class")
    out = []
    sin_tol = math.sin(math.radians(CROSS_DEG))
    for i in range(len(f)):
        rng = roadsmod.level_ranges(f, i)
        if not any(k == "bridge" for _, _, k in rng):
            continue
        skip_offroad = cls is not None and str(cls[i]) in SKIP_BRIDGE_CLASSES
        parts = roadsmod.bridge_parts(f, i)
        if not parts:
            continue
        length = 0.0
        hit = None
        for p in parts:
            q = pl.xy(np.asarray(p, np.float64)[:, :2])
            length += float(np.hypot(*np.diff(q, axis=0).T).sum())
            X = _cross(c1, c2, q[:-1], q[1:])
            if X.any() and hit is None:
                ci, bj = np.argwhere(X)[0]
                u = c2[ci] - c1[ci]
                v = q[bj + 1] - q[bj]
                s = abs(u[0] * v[1] - u[1] * v[0]) / max(1e-9, np.hypot(*u) * np.hypot(*v))
                if s >= sin_tol:
                    # the crossing point: the course on a ground road there is an underpass
                    a, b = c1[ci], c2[ci]
                    e = b - a
                    d1 = e[0] * (q[bj][1] - a[1]) - e[1] * (q[bj][0] - a[0])
                    d2 = e[0] * (q[bj + 1][1] - a[1]) - e[1] * (q[bj + 1][0] - a[0])
                    t = d1 / (d1 - d2) if d1 != d2 else 0.5
                    seg = np.hypot(*np.diff(q, axis=0).T)
                    arc = float(seg[:bj].sum() + t * seg[bj])
                    hit = (q[bj] + t * (q[bj + 1] - q[bj]), u / max(1e-9, np.hypot(*u)), q, arc, float(seg.sum()))
        if hit is None or length > flatten_max_m:
            continue
        g = None
        P, udir, q, arc, total = hit
        if ground_fn is not None:
            g = np.asarray(ground_fn(*pl.ll(float(P[0]), float(P[1]))), np.float64)
        under = False
        if g is not None and len(g):
            gs = (pl.xy(g[:, 0:2]), pl.xy(g[:, 2:4]), g[:, 4])
            d = _seg_dist(P[None, :], gs[0], gs[1])[0]
            gv = gs[1] - gs[0]
            gl = np.maximum(np.hypot(*gv.T), 1e-9)
            align = np.abs(gv @ udir) / gl
            aligned = align >= math.cos(math.radians(35.0))
            if np.any((d <= gs[2] + UNDERPASS_PAD_M) & aligned):
                # the course drives under it on a road: kept when the deck can be high enough over that road
                under = True
                if elev_fn is None:
                    continue
                if min(arc, total - arc) > AT_GRADE_REACH_M:
                    below = (gs[0][aligned], gs[1][aligned], gs[2][aligned])
                    if headroom(pl, q, arc, total, P, elev_fn, below) >= HEADROOM_M + HEADROOM_MARGIN_M:
                        continue
        if not under and skip_offroad:
            # a motorway's bridge the course passes under off the roads (a wash under the highway): kept when its deck
            # can stand high enough over the course's ground there, else a crossing at grade. On 30 m elevation a
            # narrow wash is half filled in, and the deck stood a metre over it: a wall across the course (the user's
            # Libramiento de Ensenada, 2026-10-31, a truck wedged against the deck's end)
            if elev_fn is None or min(arc, total - arc) <= AT_GRADE_REACH_M:
                continue
            if headroom(pl, q, arc, total, P, elev_fn) >= HEADROOM_M + HEADROOM_MARGIN_M:
                continue
        out.append(i)
    return out


def headroom(pl, q, arc, total, P, elev_fn, below=None):
    """The most a deck along q (plane metres; the crossing at arc of total) can stand over the ground at P: from each
    abutment's ground height, climbing at DECK_MAX_GRADE, the lower of the two (BeamNG.Earth caps its decks so).
    An abutment's height as BeamNG.Earth's grading gives it: the ground along the road through it (the bridge line,
    and straight on past its end) graded by the road(s) below (below: (a, b, half widths) in the plane; flat at the
    road's height over its core, rising 1:SLOPE_RUN from there, never over the natural ground), then smoothed along
    the road (a profile of PROFILE_SIGMA_M: the low ground over the road below pulls an abutment beside it down)."""
    zP = float(np.atleast_1d(elev_fn([float(pl.ll(P[0], P[1])[1])], [float(pl.ll(P[0], P[1])[0])]))[0])
    reach = []
    for k, along in ((0, arc), (1, total - arc)):
        end = q[0] if k == 0 else q[-1]
        nxt = q[1] if k == 0 else q[-2]
        u = end - nxt
        u = u / max(1e-9, float(np.hypot(*u)))
        t = np.arange(-PROFILE_REACH_M, PROFILE_REACH_M + 0.1, PROFILE_STEP_M)
        pts = end[None, :] + t[:, None] * u[None, :]
        lon, lat = pl.ll(pts[:, 0], pts[:, 1])
        z = np.asarray(elev_fn(list(np.atleast_1d(lat)), list(np.atleast_1d(lon))), np.float64)
        if below is not None and len(below[0]):
            a, b, hw = below
            d = (_seg_dist(pts, a, b) - (hw + SHOULDER_M)[None, :]).min(axis=1)
            z = np.minimum(z, zP + np.maximum(0.0, d) / SLOPE_RUN)
        w = np.exp(-0.5 * (t / PROFILE_SIGMA_M) ** 2)
        zk = float((w * z).sum() / w.sum())
        reach.append(zk + DECK_MAX_GRADE * along)
    return min(reach) - zP


def flatten(mapgeom, f, idx):
    """f with the bridge flags (is_bridge) and the levels above 0 of the features idx taken away: ground roads."""
    if not idx:
        return f
    sel = np.zeros(len(f), bool)
    sel[np.asarray(idx, np.int64)] = True
    rules = dict(f.rules)
    t = rules.get("flags")
    if t is not None and len(t.feature):
        vals = np.asarray(t.value).astype(object)
        fe = np.asarray(t.feature, np.int64)
        for j in np.flatnonzero(sel[fe]):
            vals[j] = str(vals[j]).replace("is_bridge", "")
        rules["flags"] = mapgeom.RuleTable(np.asarray(t.feature), np.asarray(vals.astype(str)),
                                           np.asarray(t.start), np.asarray(t.end))
    t = rules.get("level")
    if t is not None and len(t.feature):
        fe = np.asarray(t.feature, np.int64)
        try:
            lv = np.asarray(t.value, np.float64)
        except (TypeError, ValueError):
            lv = np.array([float(v) if str(v).strip() not in ("", "nan") else 0.0 for v in t.value])
        keep = ~(sel[fe] & (lv > 0))
        rules["level"] = mapgeom.RuleTable(np.asarray(t.feature)[keep], np.asarray(t.value)[keep],
                                           np.asarray(t.start)[keep], np.asarray(t.end)[keep])
    out = mapgeom.Features(f.layer, f.ids, f.kind, f.part_off, f.ring_off, f.coord_off, f.lonlat, f.en, f.own,
                           f.clipped)
    out.attrs, out.rules = dict(f.attrs), rules
    return out


# -- retaining walls ------------------------------------------------------------------------------------------------
def followed(road_segs, course_xy, pad=UNDERPASS_PAD_M, align_deg=35.0):
    """The road segments a course runs along: road_segs (a (M, 2), b (M, 2), half widths (M,)) in the course's frame;
    a segment whose middle is within its half width + pad of a course segment roughly parallel to it. -> mask (M,)."""
    a, b, hw = road_segs
    if not len(a) or not course_xy:
        return np.zeros(len(a), bool)
    ca = np.concatenate([c[:-1] for c in course_xy if len(c) >= 2])
    cb = np.concatenate([c[1:] for c in course_xy if len(c) >= 2])
    mid = (a + b) / 2
    D = _seg_dist(mid, ca, cb)                                 # (M, S)
    rv = b - a
    cv = cb - ca
    cos = np.abs(rv @ cv.T) / np.maximum(np.hypot(*rv.T)[:, None] * np.hypot(*cv.T)[None, :], 1e-9)
    return ((D <= (hw + pad)[:, None]) & (cos >= math.cos(math.radians(align_deg)))).any(axis=1)


def cut_walls(walls, course_xy, clear_m=CLEAR_M + WALL_PAD_M, on_m=2.5, cross_deg=CROSS_DEG, on_roads=None):
    """walls (roads.retaining_walls' dicts) without the stretches the course runs into: within clear_m of a course
    segment that crosses the wall's line (at least cross_deg), or within on_m of the course whatever the angle (the
    line through the wall itself). A wall alongside a road the course follows stays. course_xy: (n, 2) lines in the
    walls' frame. on_roads: (a, b, half widths) of the road surfaces the course follows (followed()): a wall standing
    on one (within its half width + shoulder + ON_ROAD_PAD_M) is cut too. Pure."""
    if not walls or not course_xy:
        return walls
    if on_roads is not None and len(on_roads[0]):
        ra, rb, rhw = on_roads
    else:
        ra = None
    a = np.concatenate([c[:-1] for c in course_xy if len(c) >= 2])
    b = np.concatenate([c[1:] for c in course_xy if len(c) >= 2])
    cd = b - a
    cl = np.maximum(np.hypot(*cd.T), 1e-9)
    sin_tol = math.sin(math.radians(cross_deg))
    out = []
    for w in walls:
        base = np.asarray(w["base"], np.float64)[:, :2]
        if len(base) == 0:
            continue
        D = _seg_dist(base, a, b)                         # (P, S)
        wd = np.gradient(base, axis=0) if len(base) > 1 else np.array([[1.0, 0.0]])
        wl = np.maximum(np.hypot(*wd.T), 1e-9)
        s = np.abs(wd[:, 0:1] * cd[None, :, 1] - wd[:, 1:2] * cd[None, :, 0]) / (wl[:, None] * cl[None, :])
        blocked = ((D <= clear_m) & (s >= sin_tol)).any(axis=1) | (D.min(axis=1) <= on_m)
        if ra is not None:
            blocked |= (_seg_dist(base, ra, rb) <= (rhw + SHOULDER_M + ON_ROAD_PAD_M)[None, :]).any(axis=1)
        far = ~blocked
        i = 0
        while i < len(far):
            if not far[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(far) and far[j + 1]:
                j += 1
            if j > i:
                sl = slice(i, j + 1)
                out.append({k: (np.asarray(v)[sl] if hasattr(v, "__len__") and len(v) == len(far) else v)
                            for k, v in w.items()})
            i = j + 1
    return out
