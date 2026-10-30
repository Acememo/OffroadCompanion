"""Rounded low-poly shapes for the detailed spectator and vehicle models (tools/make_crowds.py), on make_markers' Mesh:
tubes (limbs, a torso: round or oval, tapering), ellipsoids (heads, hands), discs (hat brims, wheels). Every triangle is
turned to face outward (its corners' order checked against the normal it should have), with smooth normals, so a
round thing shades round. Colours come from solid swatches: every corner of a part takes its swatch's middle.
"""
import math


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    ln = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def _mid(uvr):
    return ((uvr[0] + uvr[2]) / 2, (uvr[1] + uvr[3]) / 2)


def tri(m, a, b, c, na, nb, nc, uvr):
    """One triangle, its corners ordered so it faces the way its normals point (counter-clockwise seen from there)."""
    face = _cross(_sub(b, a), _sub(c, a))
    want = (na[0] + nb[0] + nc[0], na[1] + nb[1] + nc[1], na[2] + nb[2] + nc[2])
    if _dot(face, want) < 0:
        b, c, nb, nc = c, b, nc, nb
    uv = _mid(uvr)
    k = len(m.p)
    for p, n in ((a, na), (b, nb), (c, nc)):
        m.p.append(p)
        m.n.append(n)
        m.uv.append(uv)
    m.t += [k, k + 1, k + 2]


def frame(axis):
    """Two unit vectors across axis (u: as near world x as can be, v = axis x u)."""
    a = _norm(axis)
    ref = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _norm(_sub(ref, tuple(_dot(ref, a) * x for x in a)))
    v = _cross(a, u)
    return a, u, v


def tube(m, p0, p1, r0, r1, uvr, sides=8, cap0=True, cap1=True):
    """A tapering tube from p0 to p1; r0 / r1 a radius or (rx, ry) (oval: rx along the frame's u, as near world x as
    the axis allows). Capped at either end."""
    rx0, ry0 = (r0, r0) if not isinstance(r0, tuple) else r0
    rx1, ry1 = (r1, r1) if not isinstance(r1, tuple) else r1
    a, u, v = frame(_sub(p1, p0))

    def ring(p, rx, ry):
        pts, nrm = [], []
        for i in range(sides):
            t = 2 * math.pi * i / sides
            c, s = math.cos(t), math.sin(t)
            pts.append(tuple(p[j] + c * rx * u[j] + s * ry * v[j] for j in range(3)))
            nrm.append(_norm(tuple(c / max(rx, 1e-6) * u[j] + s / max(ry, 1e-6) * v[j] for j in range(3))))
        return pts, nrm
    A, NA = ring(p0, rx0, ry0)
    B, NB = ring(p1, rx1, ry1)
    for i in range(sides):
        j = (i + 1) % sides
        tri(m, A[i], A[j], B[j], NA[i], NA[j], NB[j], uvr)
        tri(m, A[i], B[j], B[i], NA[i], NB[j], NB[i], uvr)
    neg = tuple(-x for x in a)
    for cap, P, ctr, n in ((cap0, A, p0, neg), (cap1, B, p1, a)):
        if cap:
            for i in range(sides):
                tri(m, ctr, P[i], P[(i + 1) % sides], n, n, n, uvr)


def chain(m, pts, radii, uvr, sides=6, caps=False):
    """Tubes through pts (a limb: shoulder, elbow, wrist) with radii at each point, joints closed by small balls; its
    ends open (caps=False: hidden in a hip, a shoe, a hand)."""
    for k in range(len(pts) - 1):
        tube(m, pts[k], pts[k + 1], radii[k], radii[k + 1], uvr, sides, cap0=caps and k == 0,
             cap1=caps and k == len(pts) - 2)
    for k in range(1, len(pts) - 1):
        r = radii[k] if not isinstance(radii[k], tuple) else max(radii[k])
        ellipsoid(m, pts[k], (r, r, r), uvr, 6, 2, z0=-0.7, z1=0.7)


def ellipsoid(m, c, r, uvr, seg=8, rings=5, z0=-1.0, z1=1.0, uvr_top=None, top_from=None):
    """An ellipsoid round c, radii r (x, y, z), between heights z0 .. z1 (-1 .. 1 of its own: a part of one), rings
    above top_from (-1 .. 1) in uvr_top (hair on a head)."""
    rx, ry, rz = r
    lat = [math.asin(z0) + (math.asin(z1) - math.asin(z0)) * k / rings for k in range(rings + 1)]

    def pt(la, lo):
        x, y, z = math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)
        return (c[0] + rx * x, c[1] + ry * y, c[2] + rz * z), _norm((x / rx, y / ry, z / rz))
    for k in range(rings):
        sw = uvr_top if (uvr_top is not None and top_from is not None and
                         math.sin((lat[k] + lat[k + 1]) / 2) >= top_from) else uvr
        for i in range(seg):
            lo0, lo1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            (a, na), (b, nb) = pt(lat[k], lo0), pt(lat[k], lo1)
            (cc, nc), (d, nd) = pt(lat[k + 1], lo1), pt(lat[k + 1], lo0)
            if abs(math.cos(lat[k])) > 1e-6:
                tri(m, a, b, cc, na, nb, nc, sw)
            if abs(math.cos(lat[k + 1])) > 1e-6:
                tri(m, a, cc, d, na, nc, nd, sw)


def disc(m, c, r, h, uvr, sides=12, axis=(0.0, 0.0, 1.0), r_top=None):
    """A short cylinder (a hat brim, a wheel) round c along axis, radius r (r_top at its far end), h thick."""
    a = _norm(axis)
    p0 = tuple(c[j] - a[j] * h / 2 for j in range(3))
    p1 = tuple(c[j] + a[j] * h / 2 for j in range(3))
    tube(m, p0, p1, r, r if r_top is None else r_top, uvr, sides)


def rbox(m, x0, y0, z0, x1, y1, z1, uvr, bevel=0.04):
    """A box with its eight edges cut at 45 degrees (bevel m): a car body that catches the light."""
    b = min(bevel, (x1 - x0) / 3, (y1 - y0) / 3, (z1 - z0) / 3)
    # 24 corners: each box corner split three ways; faces = 6 inset rectangles + 12 edge strips + 8 corner triangles
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2

    def P(sx, sy, sz, which):
        x = x1 if sx > 0 else x0
        y = y1 if sy > 0 else y0
        z = z1 if sz > 0 else z0
        if which != 0:
            x -= sx * b
        if which != 1:
            y -= sy * b
        if which != 2:
            z -= sz * b
        return (x, y, z)

    def quad(a, bb, c, d, n):
        tri(m, a, bb, c, n, n, n, uvr)
        tri(m, a, c, d, n, n, n, uvr)
    for axis in range(3):                                  # the six faces
        for s in (-1, 1):
            n = [0.0, 0.0, 0.0]
            n[axis] = float(s)
            pts = []
            for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                sg = [0, 0, 0]
                sg[axis] = s
                o = [k for k in range(3) if k != axis]
                sg[o[0]], sg[o[1]] = s1, s2
                pts.append(P(sg[0], sg[1], sg[2], axis))
            quad(pts[0], pts[1], pts[2], pts[3], tuple(n))
    for ax in range(3):                                    # the twelve edges (along axis ax)
        o = [k for k in range(3) if k != ax]
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                sg0, sg1 = [0, 0, 0], [0, 0, 0]
                sg0[ax], sg1[ax] = -1, 1
                for sg in (sg0, sg1):
                    sg[o[0]], sg[o[1]] = s1, s2
                a0 = P(sg0[0], sg0[1], sg0[2], o[0])
                a1 = P(sg1[0], sg1[1], sg1[2], o[0])
                b0 = P(sg0[0], sg0[1], sg0[2], o[1])
                b1 = P(sg1[0], sg1[1], sg1[2], o[1])
                n = [0.0, 0.0, 0.0]
                n[o[0]], n[o[1]] = s1 * 0.7071, s2 * 0.7071
                quad(a0, a1, b1, b0, tuple(n))
    for sx in (-1, 1):                                     # the eight corners
        for sy in (-1, 1):
            for sz in (-1, 1):
                n = _norm((sx, sy, sz))
                tri(m, P(sx, sy, sz, 0), P(sx, sy, sz, 1), P(sx, sy, sz, 2), n, n, n, uvr)
    del cx, cy, cz
