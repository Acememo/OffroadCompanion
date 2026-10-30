"""The course markers' models and textures (mod/offroad_companion/art/offroadcompanion/), and the wheel ruts' texture.

Modelled on how desert races are marked (SCORE's rules: the GPS file is the course, checkpoints have a stop sign;
the car / truck course marking guides: orange arrows on stakes at the turns, on the inside, a double arrow for
45-75 degrees, pink beyond; pink "danger ahead" signs ~150 ft before a hazard; speed zone and resume-race-speed
signs), the user 2026-10-22: "make the markers more realistic, as they use on SCORE's Baja":

  sign_vcp.dae        an orange corrugated board "VCP" on a wooden lath stake (VCPs are GPS points on the real
                      course: a course sign where they are, both sides)
  sign_cp.dae         a red STOP sign over a CHECKPOINT plate, on a metal post (a physical checkpoint)
  banner_start.dae    a START banner across the course between two poles, 12 m apart
  banner_finish.dae   the FINISH banner, checkered
  arrow1_{l,r}.dae    an orange board with one arrow (a turn under 45 degrees), on a stake
  arrow2_{l,r}.dae    two arrows (45-75 degrees)
  arrow3_{l,r}.dae    a pink board with two arrows (sharper: the danger colour)
  sign_danger.dae     a pink DANGER AHEAD board
  sign_zone.dae       a SPEED ZONE board; sign_zone_end.dae: RESUME RACE SPEED
  stake.dae           a 1.5 m wooden stake, its top painted fluorescent pink, an orange cap (far apart: distance)
  ruts.png            a dark, soft-edged strip (wheel ruts along the dirt track where it blends into the ground)

Every model faces -y (the game turns each to face the drivers coming), origin at the foot of its stake / the middle
of the course for a banner, z up, metres. One material per model (egps_<name>), made by the game at runtime
pointing at <name>.png. Collada as BeamNG.Earth's server/dae.py writes it; tools/make_cdae.py then writes the .cdae.
Run: python3 tools/make_markers.py
"""
import glob
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mod", "offroad_companion", "art", "offroadcompanion")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEX = 512

ORANGE = (255, 106, 0)
PINK = (255, 40, 150)
BLACK = (20, 20, 20)
WHITE = (245, 245, 240)
RED = (200, 16, 30)
GREEN = (24, 150, 60)
WOOD = (160, 118, 72)
METAL = (170, 172, 176)
BACK = (232, 232, 226)

# atlas regions (u0, v0, u1, v1), v up (Collada): the front art in the top half, colour swatches below
FRONT = (0.0, 0.5, 1.0, 1.0)            # 512 x 256: a 2:1 board
SQUARE = (0.0, 0.5, 0.5, 1.0)           # 256 x 256 (the STOP octagon)
PLATE = (0.5, 0.75, 1.0, 1.0)           # 256 x 128 (the CHECKPOINT plate)
SW_WOOD = (0.02, 0.02, 0.08, 0.08)
SW_METAL = (0.12, 0.02, 0.18, 0.08)
SW_BACK = (0.22, 0.02, 0.28, 0.08)
SW_PINK = (0.32, 0.02, 0.38, 0.08)
SW_ORANGE = (0.42, 0.02, 0.48, 0.08)
SW_EDGE = (0.52, 0.02, 0.58, 0.08)


def px(r):
    u0, v0, u1, v1 = r
    return int(u0 * TEX), int((1 - v1) * TEX), int(u1 * TEX), int((1 - v0) * TEX)


def font(size):
    return ImageFont.truetype(FONT, size)


def fit_text(d, text, box, size, fill):
    """text (lines split at |) centred in box, as large as fits up to size."""
    x0, y0, x1, y1 = box
    lines = text.split("|")
    while size > 8:
        f = font(size)
        hs = [d.textbbox((0, 0), ln, font=f) for ln in lines]
        gap = size * 0.18
        th = sum(b[3] - b[1] for b in hs) + gap * (len(lines) - 1)
        if max(d.textlength(ln, font=f) for ln in lines) <= (x1 - x0) * 0.94 and th <= (y1 - y0) * 0.92:
            break
        size -= 2
    y = (y0 + y1) / 2 - th / 2
    for ln, b in zip(lines, hs):
        w = d.textlength(ln, font=f)
        d.text(((x0 + x1 - w) / 2, y - b[1]), ln, font=f, fill=fill)
        y += b[3] - b[1] + gap


def swatches(d, edge=BLACK, back=BACK):
    for r, c in ((SW_WOOD, WOOD), (SW_METAL, METAL), (SW_BACK, back), (SW_PINK, PINK), (SW_ORANGE, ORANGE),
                 (SW_EDGE, edge)):
        x0, y0, x1, y1 = px(r)
        d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill=c)


def arrow(d, box, right=True, fill=BLACK):
    """A bold arrow pointing right (or left) in box."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cy = (y0 + y1) / 2
    shaft = h * 0.22
    head = w * 0.38
    pts = [(x0, cy - shaft), (x1 - head, cy - shaft), (x1 - head, y0), (x1, cy), (x1 - head, y1), (x1 - head, cy + shaft),
           (x0, cy + shaft)]
    if not right:
        pts = [(x0 + x1 - x, y) for x, y in pts]
    d.polygon(pts, fill=fill)


def board_texture(path, bg, draw_front, edge=BLACK):
    im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = px(FRONT)
    d.rectangle([x0, y0, x1, y1], fill=edge)
    d.rectangle([x0 + 10, y0 + 10, x1 - 10, y1 - 10], fill=bg)
    draw_front(d, (x0 + 22, y0 + 22, x1 - 22, y1 - 22))
    swatches(d, edge, back=bg)      # corrugated plastic: the colour goes through
    im.save(path)


class Mesh:
    def __init__(self):
        self.p, self.n, self.uv, self.t = [], [], [], []

    def quad(self, a, b, c, d, nrm, uvr, mirror=False):
        """Corners a b c d counter-clockwise seen from the side the normal points to (a: bottom left as seen from
        there), uvr: atlas region (u left to right, v bottom to top as seen)."""
        u0, v0, u1, v1 = uvr
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        if mirror:
            uvs = [(u1, v0), (u0, v0), (u0, v1), (u1, v1)]
        k = len(self.p)
        for q, uv in zip((a, b, c, d), uvs):
            self.p.append(q)
            self.n.append(nrm)
            self.uv.append(uv)
        self.t += [k, k + 1, k + 2, k, k + 2, k + 3]

    def box(self, x0, y0, z0, x1, y1, z1, uvr, top=True):
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, -1, 0), uvr)
        self.quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (1, 0, 0), uvr)
        self.quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (0, 1, 0), uvr)
        self.quad((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (-1, 0, 0), uvr)
        if top:
            self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, 1), uvr)

    def board(self, x0, x1, z0, z1, front, back, edge, y=0.0, t=0.006, back_mirror=None):
        """A thin board facing -y (front art) at y .. y + t, its back art (back_mirror: the front art again, reading
        right from behind) and edges."""
        y0, y1 = y, y + t
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, -1, 0), front)
        if back_mirror is not None:
            self.quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (0, 1, 0), back_mirror)
        else:
            self.quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (0, 1, 0), back)
        self.quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (1, 0, 0), edge)
        self.quad((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (-1, 0, 0), edge)
        self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, 1), edge)
        self.quad((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0), (0, 0, -1), edge)

    def octagon(self, cx, cz, r, y, uvr, normal_y=-1):
        """A flat octagon (corners r from the centre) facing -y, textured from the square region uvr."""
        import math
        u0, v0, u1, v1 = uvr
        k0 = len(self.p)
        self.p.append((cx, y, cz))
        self.n.append((0, normal_y, 0))
        self.uv.append(((u0 + u1) / 2, (v0 + v1) / 2))
        for i in range(8):
            a = math.radians(22.5 + 45 * i)
            x, z = math.cos(a), math.sin(a)
            self.p.append((cx + r * x, y, cz + r * z))
            self.n.append((0, normal_y, 0))
            self.uv.append(((u0 + u1) / 2 + (u1 - u0) / 2 * x, (v0 + v1) / 2 + (v1 - v0) / 2 * z))
        for i in range(8):
            a, b = k0 + 1 + i, k0 + 1 + (i + 1) % 8
            # counter-clockwise seen from -y: the angle grows from +x to +z, which seen from -y is counter-clockwise
            self.t += [k0, a, b]


def write_dae(path, mesh, material, texture):
    def floats(rows):
        return " ".join("%.4f" % v for r in rows for v in r)
    nv, nt = len(mesh.p), len(mesh.t) // 3
    p = " ".join(f"{i} {i} {i}" for i in mesh.t)
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
<library_images><image id="img0"><init_from>{texture}</init_from></image></library_images>
<library_effects><effect id="{material}-fx"><profile_COMMON><newparam sid="surf0"><surface type="2D"><init_from>img0</init_from></surface></newparam><newparam sid="samp0"><sampler2D><source>surf0</source></sampler2D></newparam><technique sid="common"><lambert><diffuse><texture texture="samp0" texcoord="UVMap"/></diffuse></lambert></technique></profile_COMMON></effect></library_effects>
<library_materials><material id="{material}" name="{material}"><instance_effect url="#{material}-fx"/></material></library_materials>
<library_geometries><geometry id="g0" name="marker"><mesh>
<source id="g0-pos"><float_array id="g0-pos-a" count="{nv * 3}">{floats(mesh.p)}</float_array>
<technique_common><accessor source="#g0-pos-a" count="{nv}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="g0-nrm"><float_array id="g0-nrm-a" count="{nv * 3}">{floats(mesh.n)}</float_array>
<technique_common><accessor source="#g0-nrm-a" count="{nv}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="g0-uv"><float_array id="g0-uv-a" count="{nv * 2}">{floats(mesh.uv)}</float_array>
<technique_common><accessor source="#g0-uv-a" count="{nv}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common></source>
<vertices id="g0-vtx"><input semantic="POSITION" source="#g0-pos"/></vertices>
<triangles material="mat0" count="{nt}"><input semantic="VERTEX" source="#g0-vtx" offset="0"/><input semantic="NORMAL" source="#g0-nrm" offset="1"/><input semantic="TEXCOORD" source="#g0-uv" offset="2" set="0"/><p>{p}</p></triangles>
</mesh></geometry></library_geometries>
<library_visual_scenes><visual_scene id="scene"><node id="marker" name="marker"><instance_geometry url="#g0"><bind_material><technique_common><instance_material symbol="mat0" target="#{material}"/></technique_common></bind_material></instance_geometry></node></visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>
'''
    with open(path, "w") as f:
        f.write(xml)


# -- the models ------------------------------------------------------------------------------------------------------
BOARD_W, BOARD_H, BOARD_TOP = 0.9, 0.45, 1.5     # a 36 x 18 in corrugated board on a lath stake
STAKE = (0.05, 0.025)


def staked_board():
    """A corrugated board facing -y on a wooden lath stake behind it (the art: FRONT)."""
    m = Mesh()
    w, d = STAKE
    m.box(-w / 2, 0.006, 0.0, w / 2, 0.006 + d, BOARD_TOP + 0.03, SW_WOOD)
    m.board(-BOARD_W / 2, BOARD_W / 2, BOARD_TOP - BOARD_H, BOARD_TOP, FRONT, SW_BACK, SW_EDGE)
    return m


def stop_sign():
    """A STOP octagon (0.75 m across) over a CHECKPOINT plate, on a metal post; both face -y."""
    m = Mesh()
    m.box(-0.03, 0.01, 0.0, 0.03, 0.07, 2.42, SW_METAL)
    m.octagon(0.0, 2.02, 0.39, -0.002, SQUARE)
    m.octagon(0.0, 2.02, 0.39, 0.008, SW_METAL, normal_y=1)
    # the back octagon faces +y: its triangles reversed
    k = len(m.t) - 24
    for i in range(k, len(m.t), 3):
        m.t[i + 1], m.t[i + 2] = m.t[i + 2], m.t[i + 1]
    m.board(-0.4, 0.4, 1.4, 1.62, PLATE, SW_METAL, SW_EDGE, y=-0.004)
    return m


def banner():
    """A banner 12 m wide, 1 m tall across the course (z 3.6-4.6) between two poles; readable from both sides."""
    m = Mesh()
    for x in (-6.1, 6.1):
        m.box(x - 0.06, -0.06, 0.0, x + 0.06, 0.06, 4.75, SW_METAL)
    m.board(-6.0, 6.0, 3.6, 4.6, FRONT, None, SW_EDGE, y=-0.01, t=0.02, back_mirror=FRONT)
    return m


def stake():
    m = Mesh()
    m.box(-0.035, -0.035, 0.0, 0.035, 0.035, 1.1, SW_WOOD)
    m.box(-0.036, -0.036, 1.1, 0.036, 0.036, 1.44, SW_PINK)
    m.box(-0.04, -0.04, 1.44, 0.04, 0.04, 1.5, SW_ORANGE)
    return m


def ruts(path):
    """64 x 256: dark brown, opaque in the middle of the strip fading to nothing at its edges, a little grain."""
    import random
    random.seed(7)
    w, h = 64, 256
    im = Image.new("RGBA", (w, h))
    pxs = im.load()
    for y in range(h):
        g = random.uniform(0.85, 1.1)
        for x in range(w):
            t = abs((x + 0.5) / w - 0.5) * 2
            a = max(0.0, 1.0 - t ** 2.2) * 0.78 * random.uniform(0.85, 1.0)
            pxs[x, y] = (int(70 * g), int(52 * g), int(36 * g), int(255 * a))
    im.filter(ImageFilter.GaussianBlur(0.8)).save(path)


def textures():
    """name -> (texture writer, model maker)."""
    out = {}

    def text_board(name, bg, text, fg=BLACK, edge=BLACK, size=150):
        out[name] = (lambda p: board_texture(p, bg, lambda d, b: fit_text(d, text, b, size, fg), edge), staked_board)

    text_board("sign_vcp", ORANGE, "VCP", size=190)
    text_board("sign_danger", PINK, "DANGER|AHEAD", size=120)
    text_board("sign_zone", WHITE, "SPEED|ZONE", fg=BLACK, edge=RED, size=120)
    text_board("sign_zone_end", WHITE, "RESUME|RACE SPEED", fg=BLACK, edge=GREEN, size=120)

    for n, bg, two in (("arrow1", ORANGE, False), ("arrow2", ORANGE, True), ("arrow3", PINK, True)):
        for side, right in (("l", False), ("r", True)):
            def draw(d, b, right=right, two=two):
                x0, y0, x1, y1 = b
                if two:
                    h = (y1 - y0) / 2
                    arrow(d, (x0 + 30, y0 + 6, x1 - 30, y0 + h - 8), right)
                    arrow(d, (x0 + 30, y0 + h + 8, x1 - 30, y1 - 6), right)
                else:
                    arrow(d, (x0 + 30, y0 + 20, x1 - 30, y1 - 20), right)
            out[f"{n}_{side}"] = (lambda p, bg=bg, draw=draw: board_texture(p, bg, draw), staked_board)

    def stop_tex(p):
        im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
        d = ImageDraw.Draw(im)
        import math
        x0, y0, x1, y1 = px(SQUARE)
        cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
        oct_ = [(cx + r * math.cos(math.radians(22.5 + 45 * i)), cy - r * math.sin(math.radians(22.5 + 45 * i)))
                for i in range(8)]
        d.polygon(oct_, fill=WHITE)
        inner = [(cx + (r - 12) * math.cos(math.radians(22.5 + 45 * i)),
                  cy - (r - 12) * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
        d.polygon(inner, fill=RED)
        fit_text(d, "STOP", (x0 + 30, y0 + 60, x1 - 30, y1 - 60), 90, WHITE)
        a0, b0, a1, b1 = px(PLATE)
        d.rectangle([a0, b0, a1, b1], fill=BLACK)
        d.rectangle([a0 + 6, b0 + 6, a1 - 6, b1 - 6], fill=WHITE)
        fit_text(d, "CHECKPOINT", (a0 + 10, b0 + 8, a1 - 10, b1 - 8), 90, BLACK)
        swatches(d)
        im.save(p)
    out["sign_cp"] = (stop_tex, stop_sign)

    def banner_tex(text, bg, checkered):
        def write(p):
            im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
            # the banner is 12:1, its art region 2:1: drawn 6x wider, then squeezed into it
            wide = Image.new("RGB", (TEX * 6, TEX // 2), bg)
            d = ImageDraw.Draw(wide)
            W, H = wide.size
            if checkered:
                sq = H // 6
                for row in (0, 5):
                    for i in range(W // sq + 1):
                        if (i + row) % 2 == 0:
                            d.rectangle([i * sq, row * sq, (i + 1) * sq, (row + 1) * sq], fill=BLACK)
                fit_text(d, text, (W * 0.2, sq * 1.2, W * 0.8, H - sq * 1.2), 400, BLACK)
            else:
                d.rectangle([0, 0, W, 10], fill=WHITE)
                d.rectangle([0, H - 10, W, H], fill=WHITE)
                fit_text(d, text, (W * 0.2, 20, W * 0.8, H - 20), 400, WHITE)
            im.paste(wide.resize((TEX, TEX // 2), Image.LANCZOS), (0, 0))
            dd = ImageDraw.Draw(im)
            swatches(dd)
            im.save(p)
        return write
    out["banner_start"] = (banner_tex("START", GREEN, False), banner)
    out["banner_finish"] = (banner_tex("FINISH", WHITE, True), banner)

    def stake_tex(p):
        im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
        swatches(ImageDraw.Draw(im))
        im.save(p)
    out["stake"] = (stake_tex, stake)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for old in glob.glob(os.path.join(OUT, "marker_*")):      # (the earlier box-sign posts)
        os.remove(old)
    for name, (tex, model) in textures().items():
        tex(os.path.join(OUT, f"{name}.png"))
        write_dae(os.path.join(OUT, f"{name}.dae"), model(), f"egps_{name}", f"{name}.png")
    ruts(os.path.join(OUT, "ruts.png"))
    print("written to", os.path.normpath(OUT), ":", ", ".join(sorted(textures())))


if __name__ == "__main__":
    main()
