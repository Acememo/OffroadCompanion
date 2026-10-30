"""The spectators' models (mod/offroad_companion/art/offroadcompanion/), as the course markers' (tools/make_markers.py:
its Mesh and Collada writer; tools/make_cdae.py then writes the .cdae):

  fan_<a..l>.dae      a standing spectator, 1.6-1.8 m: arms down, waving, cheering, filming with a phone; shirts,
                      skin, caps and hats varied (low poly: boxes, as the signs)
  canopy_<color>.dae  a 3 x 3 m pop-up canopy (the shade every Baja race camp sits under)
  chair_<color>.dae   a folding camp chair
  cooler.dae          a cooler
  flag_checker.dae    a checkered flag on a 3.5 m pole (start / finish); flag_orange.dae: an orange one (pits, camps)
  (at night: the user, 2026-10-25: "add some lights to the spectators to make it more immersive at night")
  campfire.dae        a fire ring: stones, logs, ashes; flames.dae its flames (a glowing material: night only)
  light_tower.dae     a towable light tower (start, finish, checkpoint crews), its lamps facing -y; lamps.dae their
                      lit faces (glowing)
  lantern.dae         a camping lantern hanging under a canopy's roof (glowing)
  (the Lots crowds: the user, 2026-10-25, photos of SCORE Baja races: the course lined with people behind an orange
  safety fence, canopies and parked trucks behind them)
  crowd_<a..h>.dae    a 2.5 m stretch of a spectator line: 2 .. 8 people in one to three rows, filming, cheering,
                      waving (one model for many, so a long line is a few hundred objects, not thousands)
  fence_orange.dae    a 5 m stretch of orange plastic safety fence on posts (its mesh see-through where the game can)
  pickup_<color>.dae, suv_<color>.dae   a parked pickup / SUV, nose to the course
  flag_mexico.dae     a Mexican flag on a 3.5 m pole; canopy_green.dae another canopy colour

Every model faces -y (the course is in front of a spectator), origin at its feet, z up, metres. One material per
model (egps_<name>) pointing at <name>.png: a few colour swatches.
Run: python3 tools/make_crowds.py   (then EARTH_ROOT=... python3 tools/make_cdae.py)
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_markers import OUT, Mesh, write_dae  # noqa: E402

TEX = 64
# swatch cells: 4 x 4 of 16 px; region (u0, v0, u1, v1) of cell k
def cell(k):
    cx, cy = k % 4, k // 4
    u0, u1 = (cx * 16 + 2) / TEX, (cx * 16 + 14) / TEX
    v1, v0 = 1 - (cy * 16 + 2) / TEX, 1 - (cy * 16 + 14) / TEX
    return (u0, v0, u1, v1)


SW_SHIRT, SW_PANTS, SW_SKIN, SW_HAIR, SW_SHOES, SW_CAP, SW_PHONE, SW_EXTRA = (cell(k) for k in range(8))
DEFAULT_SW = (SW_SHIRT, SW_PANTS, SW_SKIN, SW_HAIR, SW_SHOES, SW_CAP, SW_PHONE)


def texture(path, colors):
    """colors: list of RGB per cell (up to 16)."""
    im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
    d = ImageDraw.Draw(im)
    for k, c in enumerate(colors):
        cx, cy = k % 4, k // 4
        d.rectangle([cx * 16, cy * 16, cx * 16 + 15, cy * 16 + 15], fill=c)
    im.save(path)


def figure(pose="down", cap=None, height=1.75, build=1.0, sw=None):
    """A standing person facing -y. pose: down | wave | cheer | phone | phoneup. cap: None | 'cap' | 'hat'. sw: the
    swatches (shirt, pants, skin, hair, shoes, cap, phone), default the one-person atlas's."""
    SW_SHIRT, SW_PANTS, SW_SKIN, SW_HAIR, SW_SHOES, SW_CAP, SW_PHONE = sw or DEFAULT_SW
    m = Mesh()
    k = height / 1.75
    w = build
    # legs (pants) and shoes
    for sx in (-1, 1):
        x0, x1 = sx * 0.03 * w, sx * 0.16 * w
        x0, x1 = min(x0, x1), max(x0, x1)
        m.box(x0, -0.09, 0.0, x1, 0.08, 0.07 * k, SW_SHOES)
        m.box(x0, -0.07, 0.07 * k, x1, 0.07, 0.86 * k, SW_PANTS)
    # torso (shirt), neck, head (skin), hair
    m.box(-0.2 * w, -0.12 * w, 0.86 * k, 0.2 * w, 0.12 * w, 1.42 * k, SW_SHIRT)
    m.box(-0.05, -0.05, 1.42 * k, 0.05, 0.05, 1.5 * k, SW_SKIN)
    m.box(-0.1, -0.11, 1.5 * k, 0.1, 0.11, 1.73 * k, SW_SKIN)
    m.box(-0.105, -0.06, 1.66 * k, 0.105, 0.12, 1.76 * k, SW_HAIR)
    if cap == "cap":
        m.box(-0.11, -0.115, 1.68 * k, 0.11, 0.115, 1.77 * k, SW_CAP)
        m.box(-0.09, -0.25, 1.68 * k, 0.09, -0.115, 1.7 * k, SW_CAP)          # the brim, forward
    elif cap == "hat":
        m.box(-0.22, -0.22, 1.68 * k, 0.22, 0.22, 1.7 * k, SW_CAP)           # a wide brim (sun hat)
        m.box(-0.11, -0.11, 1.7 * k, 0.11, 0.11, 1.82 * k, SW_CAP)
    # arms: sleeve (shirt) to the elbow, then skin
    def arm_down(sx):
        x0, x1 = sorted((sx * 0.2 * w, sx * 0.29 * w))
        m.box(x0, -0.05, 1.15 * k, x1, 0.05, 1.42 * k, SW_SHIRT)
        m.box(x0, -0.045, 0.82 * k, x1, 0.045, 1.15 * k, SW_SKIN)

    def arm_up(sx, spread=0.0):
        x0, x1 = sorted((sx * (0.2 + spread) * w, sx * (0.29 + spread) * w))
        m.box(x0, -0.05, 1.38 * k, x1, 0.05, 1.65 * k, SW_SHIRT)
        m.box(x0, -0.045, 1.65 * k, x1, 0.045, 2.0 * k, SW_SKIN)

    if pose == "down":
        arm_down(-1)
        arm_down(1)
    elif pose == "wave":
        arm_down(-1)
        arm_up(1, 0.05)
    elif pose == "cheer":
        arm_up(-1, 0.05)
        arm_up(1, 0.05)
    elif pose == "phone":
        arm_down(-1)
        x0, x1 = 0.2 * w, 0.29 * w
        m.box(x0, -0.05, 1.18 * k, x1, 0.05, 1.42 * k, SW_SHIRT)        # upper arm down
        m.box(x0 - 0.06, -0.4, 1.22 * k, x1 - 0.06, -0.05, 1.31 * k, SW_SKIN)     # forearm forward
        m.box(x0 - 0.1, -0.44, 1.26 * k, x1 - 0.02, -0.42, 1.42 * k, SW_PHONE)    # the phone, held up
    elif pose == "phoneup":                                                    # filming over the crowd's heads
        arm_down(-1)
        arm_up(1, 0.0)
        x0, x1 = 0.2 * w, 0.29 * w
        m.box(x0 - 0.04, -0.06, 1.98 * k, x1 + 0.04, -0.04, 2.14 * k, SW_PHONE)
    return m


def canopy():
    """A 3 x 3 m pop-up canopy: four legs, a pyramid roof (both faces), a valance."""
    m = Mesh()
    h, a, top = 2.25, 1.5, 2.85
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (a - 0.03), sy * (a - 0.03)
            m.box(x - 0.025, y - 0.025, 0.0, x + 0.025, y + 0.025, h + 0.05, cell(1))
    corners = [(-a, -a), (a, -a), (a, a), (-a, a)]
    k0 = len(m.p)
    roof = cell(0)
    u = ((roof[0] + roof[2]) / 2, (roof[1] + roof[3]) / 2)
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        for face in (1, -1):                        # outside, then inside (seen from under)
            k = len(m.p)
            nz = 0.8 * face
            pts = [(x0, y0, h), (x1, y1, h), (0.0, 0.0, top)]
            for q in pts:
                m.p.append(q)
                m.n.append((0.0, 0.0, nz))
                m.uv.append(u)
            m.t += [k, k + 1, k + 2] if face == 1 else [k, k + 2, k + 1]
    del k0
    for i in range(4):                              # the valance: a 0.22 m strip round the edge, both faces
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        nx, ny = (y1 - y0) / (2 * a), -(x1 - x0) / (2 * a)
        m.quad((x0, y0, h - 0.22), (x1, y1, h - 0.22), (x1, y1, h), (x0, y0, h), (nx, ny, 0), cell(2))
        m.quad((x1, y1, h - 0.22), (x0, y0, h - 0.22), (x0, y0, h), (x1, y1, h), (-nx, -ny, 0), cell(2))
    return m


def chair():
    """A folding camp chair facing -y (fabric seat and back, metal legs, arms)."""
    m = Mesh()
    leg = cell(1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box(sx * 0.25 - 0.015, sy * 0.22 - 0.015, 0.0, sx * 0.25 + 0.015, sy * 0.22 + 0.015, 0.45, leg)
        m.box(sx * 0.27 - 0.03, -0.24, 0.62, sx * 0.27 + 0.03, 0.22, 0.66, leg)        # arm rests
    m.box(-0.25, -0.22, 0.42, 0.25, 0.22, 0.46, cell(0))                                  # seat
    m.box(-0.25, 0.2, 0.46, 0.25, 0.24, 0.95, cell(0))                                    # back
    return m


def cooler():
    m = Mesh()
    m.box(-0.3, -0.2, 0.0, 0.3, 0.2, 0.34, cell(0))
    m.box(-0.31, -0.21, 0.34, 0.31, 0.21, 0.42, cell(1))
    return m


def flag():
    """A 1.2 x 0.8 m flag on a 3.5 m pole, the flag along +x from the pole, both faces."""
    m = Mesh()
    m.box(-0.025, -0.025, 0.0, 0.025, 0.025, 3.5, cell(9))      # (the pole's swatch: below the flag art)
    m.board(0.03, 1.23, 2.65, 3.45, (0.0, 0.5, 1.0, 1.0), None, cell(9), y=-0.004, t=0.008,
            back_mirror=(0.0, 0.5, 1.0, 1.0))
    return m


def pyramid(m, cx, cy, z0, r, h, uvr):
    """A four-sided pyramid (a flame's tongue), every face both ways."""
    u = ((uvr[0] + uvr[2]) / 2, (uvr[1] + uvr[3]) / 2)
    base = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
    for i in range(4):
        (x0, y0), (x1, y1) = base[i], base[(i + 1) % 4]
        nx, ny = (y1 - y0), -(x1 - x0)
        ln = max(1e-9, (nx * nx + ny * ny) ** 0.5)
        for face in (1, -1):
            k = len(m.p)
            for q in ((x0, y0, z0), (x1, y1, z0), (cx, cy, z0 + h)):
                m.p.append(q)
                m.n.append((face * nx / ln, face * ny / ln, 0.3))
                m.uv.append(u)
            m.t += [k, k + 1, k + 2] if face == 1 else [k, k + 2, k + 1]


def campfire():
    """A fire ring 1.2 m across: eight stones, three logs crossed over the ashes."""
    m = Mesh()
    import math
    m.box(-0.45, -0.45, 0.0, 0.45, 0.45, 0.03, cell(2))                         # ashes
    for i in range(8):
        a = i * math.pi / 4 + 0.2
        x, y = 0.58 * math.cos(a), 0.58 * math.sin(a)
        s = 0.11 + 0.03 * (i % 3)
        m.box(x - s, y - s, 0.0, x + s, y + s, 0.12 + 0.04 * (i % 2), cell(0))   # stones
    for i in range(3):                                                           # logs, leaning together
        a = i * 2 * math.pi / 3
        x, y = 0.22 * math.cos(a), 0.22 * math.sin(a)
        m.box(x - 0.07, y - 0.07, 0.02, x + 0.07, y + 0.07, 0.16, cell(1))
    return m


def flames():
    """The fire's flames: tongues of orange round taller yellow ones (glowing)."""
    m = Mesh()
    import math
    for i in range(5):
        a = i * 2 * math.pi / 5
        pyramid(m, 0.14 * math.cos(a), 0.14 * math.sin(a), 0.05, 0.11, 0.45 + 0.12 * (i % 3), cell(0))
    pyramid(m, 0.0, 0.0, 0.05, 0.09, 0.85, cell(1))
    pyramid(m, 0.05, -0.04, 0.05, 0.06, 0.65, cell(1))
    return m


TOWER_H = 6.5            # the lamps' height (crowds.lua: its light there)
LAMP_X = (-0.75, -0.25, 0.25, 0.75)


def light_tower():
    """A towable light tower: a trailer (body, wheels, drawbar, outriggers), a mast, four lamps on a bar facing -y."""
    m = Mesh()
    m.box(-0.65, -1.1, 0.35, 0.65, 1.1, 1.25, cell(0))                     # the body (generator)
    m.box(-0.66, -1.11, 1.25, 0.66, 1.11, 1.3, cell(1))                    # its lid's edge
    for sx in (-1, 1):
        m.box(sx * 0.65, -0.3, 0.0, sx * 0.85, 0.3, 0.6, cell(3))           # wheels
        m.box(sx * 0.65 - 0.06, -1.7 if sx < 0 else 1.6, 0.0, sx * 0.65 + 0.06,
              -1.6 if sx < 0 else 1.7, 0.5, cell(1))                       # (jack stands)
    m.box(-0.05, 1.1, 0.4, 0.05, 2.3, 0.5, cell(1))                         # the drawbar
    m.box(-1.9, -0.05, 0.25, 1.9, 0.05, 0.33, cell(1))                      # outriggers
    for sx in (-1, 1):
        m.box(sx * 1.9 - 0.06, -0.06, 0.0, sx * 1.9 + 0.06, 0.06, 0.3, cell(1))
    m.box(-0.08, 0.3, 1.3, 0.08, 0.46, TOWER_H + 0.15, cell(1))             # the mast
    m.box(-1.0, 0.3, TOWER_H + 0.15, 1.0, 0.42, TOWER_H + 0.25, cell(1))    # the lamp bar
    for x in LAMP_X:
        m.box(x - 0.2, 0.05, TOWER_H - 0.15, x + 0.2, 0.3, TOWER_H + 0.2, cell(1))   # lamp housings
    return m


def lamps():
    """The light tower's four lamp faces, just in front of their housings (glowing)."""
    m = Mesh()
    for x in LAMP_X:
        m.box(x - 0.17, 0.03, TOWER_H - 0.12, x + 0.17, 0.05, TOWER_H + 0.17, cell(0))
    return m


LANTERN_Z = 2.0          # its middle (crowds.lua: its light there): under a canopy's 2.25 m edge


def lantern():
    """A camping lantern hanging from a canopy's peak (glowing: the whole of it)."""
    m = Mesh()
    m.box(-0.01, -0.01, LANTERN_Z + 0.14, 0.01, 0.01, 2.8, cell(1))             # its cord, up to the roof
    m.box(-0.07, -0.07, LANTERN_Z - 0.12, 0.07, 0.07, LANTERN_Z + 0.12, cell(0))  # the glowing body
    m.box(-0.08, -0.08, LANTERN_Z + 0.12, 0.08, 0.08, LANTERN_Z + 0.15, cell(1))  # cap
    m.box(-0.08, -0.08, LANTERN_Z - 0.15, 0.08, 0.08, LANTERN_Z - 0.12, cell(1))  # base
    return m


# -- the detailed people and vehicles (the user, 2026-10-25: "a bit more realistic without impacting performance too
# much"): rounded limbs with elbows and knees, hands, a shaped torso, a head with hair, eyes and a nose, caps and wide
# sombreros; round wheels, a grille, mirrors. Drawn near the camera only: the simple models above stay as each shape's
# far detail level (tools/make_cdae.py: LOD_PX), so a crowd far off costs what it did.
from hdshapes import chain, disc, ellipsoid, rbox, tube  # noqa: E402

LOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "lod")   # (not shipped: make_cdae reads it)


def figure_hd(pose="down", cap=None, height=1.75, build=1.0, sw=None):
    """figure()'s person in detail (~500 triangles), the same size, pose and colours."""
    SHIRT, PANTS, SKIN, HAIR, SHOES, CAP, DARK = sw or DEFAULT_SW
    m = Mesh()
    k, w = height / 1.75, build
    for sx in (-1, 1):                                                          # legs and shoes
        chain(m, [(sx * 0.09 * w, 0.0, 0.92 * k), (sx * 0.095 * w, -0.015, 0.49 * k), (sx * 0.1 * w, 0.0, 0.1 * k)],
              [0.078 * w, 0.054 * w, 0.044 * w], PANTS)
        x0, x1 = sorted((sx * (0.1 * w - 0.05), sx * (0.1 * w + 0.05)))
        rbox(m, x0, -0.17, 0.0, x1, 0.07, 0.1, SHOES, 0.02)
    tube(m, (0, 0, 0.84 * k), (0, 0, 1.0 * k), (0.165 * w, 0.11 * w), (0.17 * w, 0.11 * w), PANTS, 8, cap1=False)
    tube(m, (0, 0, 0.98 * k), (0, 0, 1.3 * k), (0.165 * w, 0.105 * w), (0.188 * w, 0.118 * w), SHIRT, cap1=False)
    tube(m, (0, 0, 1.3 * k), (0, 0, 1.45 * k), (0.188 * w, 0.118 * w), (0.15 * w, 0.095 * w), SHIRT, cap0=False)
    for sx in (-1, 1):
        ellipsoid(m, (sx * 0.165 * w, 0.0, 1.4 * k), (0.065 * w, 0.06 * w, 0.06 * w), SHIRT, 6, 2, z0=-0.3)
    tube(m, (0, 0, 1.43 * k), (0, 0, 1.54 * k), 0.046, 0.044, SKIN, 6, cap0=False, cap1=False)      # neck
    hz = 1.635 * k
    ellipsoid(m, (0, 0.0, hz), (0.088, 0.1, 0.12), SKIN, 8, 5, uvr_top=HAIR, top_from=0.3)
    ellipsoid(m, (0, 0.035, hz + 0.01), (0.09, 0.075, 0.1), HAIR, 6, 3, z0=-0.2, z1=0.9)   # the hair at the back
    for sx in (-1, 1):
        m.box(sx * 0.032 - 0.011, -0.1, hz + 0.012, sx * 0.032 + 0.011, -0.093, hz + 0.026, DARK)   # eyes
    m.box(-0.012, -0.112, hz - 0.03, 0.012, -0.095, hz + 0.005, SKIN)                            # nose
    # arms: shoulder, elbow, wrist by pose; a short sleeve, skin below it, a hand
    S = {sx: (sx * 0.2 * w, 0.0, 1.4 * k) for sx in (-1, 1)}
    down = {sx: ((sx * 0.235 * w, 0.02, 1.13 * k), (sx * 0.245 * w, -0.01, 0.88 * k)) for sx in (-1, 1)}
    up = {sx: ((sx * 0.3 * w, -0.02, 1.64 * k), (sx * 0.33 * w, -0.05, 1.9 * k)) for sx in (-1, 1)}
    arms = dict(down)
    phone_at = None
    if pose == "cheer":
        arms = dict(up)
    elif pose == "wave":
        arms[1] = ((0.34 * w, 0.0, 1.55 * k), (0.37 * w, -0.04, 1.82 * k))
    elif pose == "phone":
        arms[1] = ((0.24 * w, 0.02, 1.16 * k), (0.12 * w, -0.3, 1.3 * k))
        phone_at = (0.1 * w, -0.39, 1.33 * k)
    elif pose == "phoneup":
        arms[1] = ((0.27 * w, -0.08, 1.64 * k), (0.2 * w, -0.16, 1.93 * k))
        phone_at = (0.19 * w, -0.2, 2.05 * k)
    for sx in (-1, 1):
        s, (e, wr) = S[sx], arms[sx]
        sl = tuple(s[j] + 0.55 * (e[j] - s[j]) for j in range(3))
        tube(m, s, sl, 0.064 * w, 0.056 * w, SHIRT, 6, cap0=False)
        chain(m, [sl, e, wr], [0.05 * w, 0.045 * w, 0.037], SKIN, 6)
        d = tuple((wr[j] - e[j]) for j in range(3))
        ln = sum(x * x for x in d) ** 0.5 or 1.0
        hand = tuple(wr[j] + d[j] / ln * 0.06 for j in range(3))
        ellipsoid(m, hand, (0.035, 0.03, 0.045), SKIN, 5, 3)
    if phone_at:
        x, y, z = phone_at
        rbox(m, x - 0.035, y - 0.008, z - 0.07, x + 0.035, y + 0.008, z + 0.07, DARK, 0.006)
    if cap == "cap":
        ellipsoid(m, (0, 0.0, hz + 0.02), (0.096, 0.108, 0.1), CAP, 8, 2, z0=0.0, z1=1.0)
        rbox(m, -0.075, -0.24, hz + 0.02, 0.075, -0.09, hz + 0.034, CAP, 0.005)
    elif cap == "hat":
        disc(m, (0, 0, hz + 0.06), 0.27, 0.014, CAP, 12)
        tube(m, (0, 0, hz + 0.06), (0, 0, hz + 0.2), 0.105, 0.088, CAP, 8, cap0=False)
    return m


def windows(m, y0, y1, top, half, glass, rear=True, pillars=1):
    """Thin panes set into a cab from y0 (front) to y1 (back), its roof at top, half wide: a windscreen, side windows
    between pillars, a back window. The body shows round them (one dark block read as a black box)."""
    z0, z1 = 1.24, top - 0.1
    t = 0.012
    rbox(m, -half + 0.12, y0 - t, z0 + 0.02, half - 0.12, y0 + 0.004, z1, glass, 0.004)        # windscreen
    if rear:
        rbox(m, -half + 0.14, y1 - 0.004, z0 + 0.04, half - 0.14, y1 + t, z1 - 0.02, glass, 0.004)
    n = pillars
    span = (y1 - 0.12) - (y0 + 0.15)
    for i in range(n):                                                                         # side windows
        a = y0 + 0.15 + span * i / n + (0.06 if i else 0.0)
        b = y0 + 0.15 + span * (i + 1) / n - (0.06 if i < n - 1 else 0.0)
        for sx in (-1, 1):
            x0, x1 = sorted((sx * (half - 0.004), sx * (half + t)))
            rbox(m, x0, a, z0, x1, b, z1, glass, 0.004)


def vehicle_hd(kind):
    """vehicle()'s pickup / SUV in detail: a bevelled body, round wheels with hubs, a grille, mirrors, a roof bar."""
    m = Mesh()
    body, glass, tyre, trim, lamp = cell(0), cell(1), cell(2), cell(3), cell(4)
    w = 0.98
    rbox(m, -w, -2.75, 0.5, w, 2.75, 1.08, body, 0.08)
    if kind == "pickup":
        rbox(m, -w + 0.06, -1.15, 1.08, w - 0.06, 0.55, 1.85, body, 0.1)
        windows(m, -1.15, 0.55, 1.85, w - 0.06, glass, rear=True)
        for sx in (-1, 1):
            x0, x1 = sorted((sx * w, sx * (w - 0.08)))
            rbox(m, x0, 0.6, 1.08, x1, 2.75, 1.34, body, 0.03)
        rbox(m, -w, 2.66, 1.08, w, 2.75, 1.34, body, 0.03)
        rbox(m, -0.7, -0.9, 1.85, 0.7, -0.75, 1.93, trim, 0.02)                 # a light bar on the roof
    else:
        rbox(m, -w + 0.06, -1.15, 1.08, w - 0.06, 2.62, 1.92, body, 0.1)
        windows(m, -1.15, 2.62, 1.92, w - 0.06, glass, rear=True, pillars=2)
        rbox(m, -0.75, -0.6, 1.92, -0.65, 2.3, 1.98, trim, 0.01)                 # roof rails
        rbox(m, 0.65, -0.6, 1.92, 0.75, 2.3, 1.98, trim, 0.01)
    rbox(m, -w - 0.03, -2.86, 0.4, w + 0.03, -2.7, 0.72, trim, 0.04)            # bumpers
    rbox(m, -w - 0.03, 2.7, 0.4, w + 0.03, 2.86, 0.72, trim, 0.04)
    rbox(m, -0.5, -2.77, 0.74, 0.5, -2.73, 1.0, trim, 0.01)                     # grille
    for sx in (-1, 1):
        rbox(m, sx * 0.7 - 0.17, -2.78, 0.8, sx * 0.7 + 0.17, -2.73, 0.98, lamp, 0.02)   # headlights
        rbox(m, sx * 0.85 - 0.1, 2.73, 0.8, sx * 0.85 + 0.1, 2.78, 1.0, cell(5), 0.01)    # tail lights
        x0, x1 = sorted((sx * w, sx * (w + 0.16)))
        rbox(m, x0, -1.05, 1.3, x1, -0.95, 1.45, body, 0.02)                    # mirrors
        for y in (-1.85, 1.75):                                                 # wheels: tyre, rim
            disc(m, (sx * (w - 0.06), y, 0.4), 0.4, 0.3, tyre, 14, axis=(1.0, 0.0, 0.0))
            disc(m, (sx * (w + 0.1), y, 0.4), 0.22, 0.02, trim, 10, axis=(1.0, 0.0, 0.0))
    return m


# -- the Lots crowds ---------------------------------------------------------------------------------------------------
TEX8 = 128


def cell8(k):
    """Cell k of an 8 x 8 atlas of 16 px cells (TEX8 px): (u0, v0, u1, v1)."""
    cx, cy = k % 8, k // 8
    u0, u1 = (cx * 16 + 2) / TEX8, (cx * 16 + 14) / TEX8
    v1, v0 = 1 - (cy * 16 + 2) / TEX8, 1 - (cy * 16 + 14) / TEX8
    return (u0, v0, u1, v1)


def texture8(path, colors):
    im = Image.new("RGB", (TEX8, TEX8), (128, 128, 128))
    d = ImageDraw.Draw(im)
    for k, c in enumerate(colors):
        cx, cy = k % 8, k // 8
        d.rectangle([cx * 16, cy * 16, cx * 16 + 15, cy * 16 + 15], fill=c)
    im.save(path)


def add(m, part, dx, dy, yaw):
    """Mesh part turned by yaw (rad, about z) and moved by (dx, dy), added to m."""
    import math
    c, s = math.cos(yaw), math.sin(yaw)
    k = len(m.p)
    for (x, y, z), (nx, ny, nz), uv in zip(part.p, part.n, part.uv):
        m.p.append((c * x - s * y + dx, s * x + c * y + dy, z))
        m.n.append((c * nx - s * ny, s * nx + c * ny, nz))
        m.uv.append(uv)
    m.t += [k + i for i in part.t]


# name -> people in the front row, the second, the third (a 2.5 m stretch of the line, x -1.25 .. 1.25, facing -y)
STRIPS = {"crowd_a": (2, 0, 0), "crowd_b": (3, 0, 0), "crowd_c": (3, 1, 0), "crowd_d": (2, 2, 0),
          "crowd_e": (4, 2, 0), "crowd_f": (4, 3, 0), "crowd_g": (5, 3, 0), "crowd_h": (4, 3, 1)}
POSES = ["phone", "phoneup", "phoneup", "cheer", "wave", "down", "down", "phone"]


def strip_people(name):
    """[(pose, cap, height, build, palette (shirt, pants, skin, hair, cap), x, y, yaw)] of a strip, the same every run."""
    import random
    rnd = random.Random(name)
    rows = STRIPS[name]
    out = []
    for r, n in enumerate(rows):
        for i in range(n):
            x = -1.25 + (i + 0.5) * 2.5 / n + rnd.uniform(-0.12, 0.12) + (0.2 if r % 2 else 0.0)
            pal = (rnd.randrange(len(SHIRTS)), rnd.randrange(len(PANTS)), rnd.randrange(len(SKINS)),
                   rnd.randrange(len(HAIRS)), rnd.randrange(len(CAPS)))
            cap = rnd.choice([None, "cap", "cap", "hat", "hat"])
            out.append((rnd.choice(POSES), cap, rnd.uniform(1.58, 1.88), rnd.uniform(0.88, 1.18), pal,
                        max(-1.1, min(1.1, x)), 0.15 + r * 0.62 + rnd.uniform(-0.08, 0.08), rnd.uniform(-0.3, 0.3)))
    return out


def strip(name, hd=True):
    m = Mesh()
    for j, (pose, cap, h, b, _pal, x, y, yaw) in enumerate(strip_people(name)):
        sw = tuple(cell8(j * 8 + q) for q in range(7))
        add(m, (figure_hd if hd else figure)(pose, cap, h, b, sw=sw), x, y, yaw)
    return m


def strip_texture(name):
    def write(path):
        cols = []
        for (_p, _c, _h, _b, (sh, pa, sk, ha, ca), *_r) in strip_people(name):
            cols += [SHIRTS[sh], PANTS[pa], SKINS[sk], HAIRS[ha], (40, 36, 34), CAPS[ca], (20, 20, 24), (0, 0, 0)]
        texture8(path, cols)
    return write


FENCE_L, FENCE_H = 5.0, 1.0


def fence():
    """5 m of orange safety fence (x -2.5 .. 2.5) at y 0, both faces, on three steel posts."""
    m = Mesh()
    reps = FENCE_L / 0.5                                 # (the mesh tile repeats every 0.5 m: the atlas wraps)
    m.quad((-2.5, 0, 0.05), (2.5, 0, 0.05), (2.5, 0, FENCE_H), (-2.5, 0, FENCE_H), (0, -1, 0), (0.0, 0.5, reps, 1.0))
    m.quad((2.5, 0.002, 0.05), (-2.5, 0.002, 0.05), (-2.5, 0.002, FENCE_H), (2.5, 0.002, FENCE_H), (0, 1, 0),
           (0.0, 0.5, reps, 1.0))
    for x in (-2.5, 0.0, 2.5):
        m.box(x - 0.02, 0.005, 0.0, x + 0.02, 0.045, FENCE_H + 0.15, cell(12))
    return m


def fence_texture(path):
    """Top half: one 0.5 m tile of the fence's diamond mesh (holes see-through: alpha 0, a dark orange where the game
    shows no see-through); the bottom-left cell: the posts' steel."""
    im = Image.new("RGBA", (64, 64), (150, 70, 20, 0))
    d = ImageDraw.Draw(im)
    orange = (255, 102, 0, 255)
    for k in range(-8, 16):                              # diagonal strands both ways, 8 px apart
        d.line([(k * 8, 0), (k * 8 + 32, 32)], fill=orange, width=2)
        d.line([(k * 8 + 32, 0), (k * 8, 32)], fill=orange, width=2)
    d.rectangle([0, 0, 63, 2], fill=orange)
    d.rectangle([0, 29, 63, 31], fill=orange)
    d.rectangle([0, 48, 15, 63], fill=(150, 152, 156, 255))
    im.save(path)


def vehicle(kind):
    """A parked pickup or SUV, its nose to -y (toward the course), wheels on the ground: body cell 0, glass 1, tyres
    2, trim 3, lamps 4."""
    m = Mesh()
    body, glass, tyre, trim, lamp = cell(0), cell(1), cell(2), cell(3), cell(4)
    w = 0.98
    m.box(-w, -2.75, 0.5, w, 2.75, 1.08, body)                          # the body's lower part, nose to tail
    if kind == "pickup":
        m.box(-w + 0.06, -1.15, 1.08, w - 0.06, 0.55, 1.85, body)       # the cab
        m.box(-w + 0.04, -1.16, 1.2, w - 0.04, -0.95, 1.78, glass)      # windscreen
        m.box(-w - 0.005, -1.05, 1.2, w + 0.005, 0.45, 1.75, glass)     # side windows
        for sx in (-1, 1):                                              # the bed's walls
            m.box(sx * w - (0.07 if sx > 0 else 0), 0.6, 1.08, sx * w + (0.07 if sx < 0 else 0), 2.75, 1.32, body)
        m.box(-w, 2.65, 1.08, w, 2.75, 1.32, body)
    else:
        m.box(-w + 0.06, -1.15, 1.08, w - 0.06, 2.6, 1.9, body)         # the cabin, to the tail
        m.box(-w + 0.04, -1.16, 1.2, w - 0.04, -0.95, 1.8, glass)
        m.box(-w - 0.005, -1.0, 1.22, w + 0.005, 2.4, 1.78, glass)
        m.box(-w + 0.1, 2.55, 1.25, w - 0.1, 2.62, 1.75, glass)          # rear window
    m.box(-w - 0.02, -2.85, 0.42, w + 0.02, -2.72, 0.72, trim)          # bumpers
    m.box(-w - 0.02, 2.72, 0.42, w + 0.02, 2.85, 0.72, trim)
    for sx in (-1, 1):
        m.box(sx * 0.62 - 0.22, -2.77, 0.82, sx * 0.62 + 0.22, -2.74, 0.98, lamp)   # headlights
        for y in (-1.85, 1.75):                                         # wheels
            x0, x1 = sorted((sx * (w - 0.18), sx * (w + 0.06)))
            m.box(x0, y - 0.4, 0.0, x1, y + 0.4, 0.8, tyre)
    return m


VEHICLES = {"pickup_white": (238, 238, 236), "pickup_silver": (172, 176, 180), "pickup_red": (150, 22, 28),
            "pickup_black": (28, 28, 30), "suv_white": (230, 230, 228), "suv_gray": (105, 108, 112),
            "suv_blue": (34, 56, 112), "suv_maroon": (96, 26, 32)}


SKINS = [(236, 196, 160), (198, 145, 100), (150, 100, 66), (98, 64, 42), (224, 172, 128)]
HAIRS = [(40, 30, 22), (90, 60, 30), (20, 18, 16), (150, 120, 80), (60, 45, 35)]
SHIRTS = [(200, 30, 40), (30, 70, 160), (240, 240, 235), (25, 25, 28), (250, 190, 20), (40, 140, 70),
          (240, 110, 20), (120, 120, 125), (90, 40, 120), (0, 150, 170), (230, 90, 140), (160, 30, 30)]
PANTS = [(40, 55, 90), (30, 30, 34), (120, 100, 70), (70, 75, 80), (50, 70, 110), (150, 130, 95)]
CAPS = [(25, 25, 28), (200, 30, 40), (240, 240, 235), (30, 70, 160), (190, 160, 110)]
FANS = [  # name, pose, cap, height, build, shirt, pants, skin, hair, cap colour
    ("fan_a", "down", "cap", 1.78, 1.05, 0, 0, 0, 0, 0),
    ("fan_b", "wave", None, 1.68, 0.95, 1, 1, 1, 1, 0),
    ("fan_c", "cheer", "cap", 1.82, 1.1, 2, 2, 2, 2, 1),
    ("fan_d", "phone", None, 1.72, 1.0, 3, 3, 3, 3, 0),
    ("fan_e", "down", "hat", 1.75, 1.15, 4, 4, 4, 4, 4),
    ("fan_f", "cheer", None, 1.65, 0.9, 5, 0, 0, 1, 0),
    ("fan_g", "wave", "cap", 1.8, 1.0, 6, 1, 2, 2, 2),
    ("fan_h", "phone", "cap", 1.7, 0.95, 7, 5, 1, 3, 3),
    ("fan_i", "down", None, 1.62, 0.9, 8, 2, 3, 4, 0),
    ("fan_j", "cheer", "hat", 1.76, 1.05, 9, 3, 4, 0, 4),
    ("fan_k", "wave", None, 1.74, 1.0, 10, 4, 0, 2, 0),
    ("fan_l", "down", "cap", 1.85, 1.2, 11, 1, 2, 0, 1),
]
CANOPIES = {"canopy_red": (200, 32, 38), "canopy_blue": (32, 80, 170), "canopy_white": (238, 238, 232),
            "canopy_green": (36, 118, 64)}
CHAIRS = {"chair_blue": (40, 70, 140), "chair_green": (50, 110, 60), "chair_red": (170, 40, 40)}
METAL = (160, 162, 166)


def flag_texture(path, kind):
    im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
    d = ImageDraw.Draw(im)
    if kind == "checker":                           # the flag: the top half, 8 x 4 squares
        for i in range(8):
            for j in range(4):
                d.rectangle([i * 8, j * 8, i * 8 + 7, j * 8 + 7], fill=(20, 20, 20) if (i + j) % 2 else (245, 245, 240))
    elif kind == "mexico":                         # green, white, red, upright thirds (the emblem: a hint of it)
        d.rectangle([0, 0, 20, 31], fill=(0, 104, 71))
        d.rectangle([21, 0, 42, 31], fill=(245, 245, 240))
        d.rectangle([43, 0, 63, 31], fill=(206, 17, 38))
        d.ellipse([27, 11, 36, 20], fill=(140, 96, 52))
    else:
        d.rectangle([0, 0, 63, 31], fill=(255, 106, 0))
        d.rectangle([0, 12, 63, 19], fill=(20, 20, 20))
    d.rectangle([16, 32, 31, 47], fill=METAL)               # (cell 9's swatch: the pole)
    im.save(path)


def lods():
    """name -> the far detail level's mesh (the simple model) of each detailed one."""
    out = {}
    for name, pose, cap, h, b, *_r in FANS:
        out[name] = lambda pose=pose, cap=cap, h=h, b=b: figure(pose, cap, h, b)
    for name in STRIPS:
        out[name] = lambda name=name: strip(name, hd=False)
    for name in VEHICLES:
        out[name] = lambda kind=name.split("_")[0]: vehicle(kind)
    return out


def models():
    out = {}
    for name, pose, cap, h, b, sh, pa, sk, ha, ca in FANS:
        cols = [SHIRTS[sh], PANTS[pa], SKINS[sk], HAIRS[ha], (40, 36, 34), CAPS[ca], (20, 20, 24), (0, 0, 0)]
        out[name] = (lambda p, cols=cols: texture(p, cols), lambda pose=pose, cap=cap, h=h, b=b: figure_hd(pose, cap, h, b))
    for name, c in CANOPIES.items():
        out[name] = (lambda p, c=c: texture(p, [c, METAL, c]), canopy)
    for name, c in CHAIRS.items():
        out[name] = (lambda p, c=c: texture(p, [c, (30, 30, 32)]), chair)
    out["cooler"] = (lambda p: texture(p, [(30, 80, 170), (240, 240, 235)]), cooler)
    out["flag_checker"] = (lambda p: flag_texture(p, "checker"), flag)
    out["flag_orange"] = (lambda p: flag_texture(p, "orange"), flag)
    out["campfire"] = (lambda p: texture(p, [(118, 112, 104), (92, 62, 38), (52, 48, 46)]), campfire)
    out["flames"] = (lambda p: texture(p, [(255, 110, 20), (255, 210, 80)]), flames)
    out["light_tower"] = (lambda p: texture(p, [(232, 190, 30), (70, 72, 76), (0, 0, 0), (22, 22, 24)]), light_tower)
    out["lamps"] = (lambda p: texture(p, [(255, 250, 235)]), lamps)
    out["lantern"] = (lambda p: texture(p, [(255, 214, 140), (40, 42, 44)]), lantern)
    for name in STRIPS:
        out[name] = (strip_texture(name), lambda name=name: strip(name))
    out["fence_orange"] = (fence_texture, fence)
    for name, c in VEHICLES.items():
        out[name] = (lambda p, c=c: texture(p, [c, (22, 26, 32), (18, 18, 18), (150, 152, 156), (250, 245, 220),
                                                 (170, 20, 20)]),
                     lambda kind=name.split("_")[0]: vehicle_hd(kind))
    out["flag_mexico"] = (lambda p: flag_texture(p, "mexico"), flag)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(LOD_DIR, exist_ok=True)
    for name, (tex, model) in models().items():
        tex(os.path.join(OUT, f"{name}.png"))
        write_dae(os.path.join(OUT, f"{name}.dae"), model(), f"egps_{name}", f"{name}.png")
    for name, model in lods().items():
        write_dae(os.path.join(LOD_DIR, f"{name}.dae"), model(), f"egps_{name}", f"{name}.png")
    print("written to", os.path.normpath(OUT), ":", ", ".join(sorted(models())))


if __name__ == "__main__":
    main()
