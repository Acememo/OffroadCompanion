"""Every country's flag for the crowds (the user, 2026-11-12: "add the flags from all of the other countries, so they
appear with their flag like the Mexican one does now"): mod/offroad_companion/art/offroadcompanion/flags/flag_<cc>.cdae
(the crowds' flag on its 3.5 m pole, make_crowds.flag, its material egps_flag_<cc>) and flag_<cc>.png, and
lua/ge/extensions/offroadCompanion/countries.lua: the country names BeamNG.Earth's status bar can show (each country's
name in 78 languages) -> its ISO 3166-1 code, and the codes that have a flag.

Sources (both MIT, npm): flag-icons (the flags, 4x3 SVG: github.com/lipis/flag-icons) and i18n-iso-countries (the
names: github.com/michaelwittig/node-i18n-iso-countries). Their licences go with the flags (flags/LICENSE.txt).

    npm pack flag-icons i18n-iso-countries      (unpacked: <dir>/fi/package, <dir>/ic/package)
    EARTH_ROOT=/path/to/BeamNG.Earth python3 tools/make_flags.py <flag-icons package dir> <i18n-iso-countries package dir>
"""
import glob
import io
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_crowds  # noqa: E402
from make_cdae import read_dae  # noqa: E402
from make_markers import write_dae  # noqa: E402

ART = os.path.join(HERE, "..", "mod", "offroad_companion", "art", "offroadcompanion", "flags")
LUA = os.path.join(HERE, "..", "mod", "offroad_companion", "lua", "ge", "extensions", "offroadCompanion", "countries.lua")
TEX = 128                    # the flag in the top half (128 x 64), the pole's swatch where make_crowds' cell 9 is
METAL = make_crowds.METAL
# names the status bar may show that the 78 languages' lists do not have
EXTRA = {"usa": "us", "united states of america": "us", "estados unidos mexicanos": "mx", "uk": "gb",
         "great britain": "gb", "russian federation": "ru", "korea, republic of": "kr", "south korea": "kr",
         "north korea": "kp", "czech republic": "cz", "türkiye": "tr", "turkiye": "tr"}


def key(name):
    """A name as the mod compares it: ASCII letters lowered (Lua's string.lower), trimmed."""
    return "".join(c.lower() if c.isascii() else c for c in str(name)).strip()


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def texture(svg_path, out_path):
    import cairosvg
    png = cairosvg.svg2png(url=svg_path, output_width=TEX * 2, output_height=TEX * 3 // 2)     # (its own 4 x 3)
    flag = Image.open(io.BytesIO(png)).convert("RGB").resize((TEX, TEX // 2), Image.LANCZOS)
    im = Image.new("RGB", (TEX, TEX), (128, 128, 128))
    im.paste(flag, (0, 0))
    s = TEX // 64
    im.paste(METAL, (16 * s, 32 * s, 32 * s, 48 * s))         # (make_crowds.cell(9): the pole)
    im.save(out_path, optimize=True)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    fi, ic = sys.argv[1], sys.argv[2]
    earth = os.environ.get("EARTH_ROOT")
    if not earth:
        sys.exit("set EARTH_ROOT to a BeamNG.Earth checkout (its server/cdae.py writes the shapes)")
    sys.path.insert(0, os.path.join(earth, "server"))
    import cdae
    names = {}
    for path in sorted(glob.glob(os.path.join(ic, "langs", "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for code, nm in sorted(data["countries"].items()):
            for n in (nm if isinstance(nm, list) else [nm]):
                names.setdefault(key(n), code.lower())
    for n, code in EXTRA.items():
        names.setdefault(key(n), code)
    codes = sorted(set(names.values()))
    os.makedirs(ART, exist_ok=True)
    made = []
    for code in codes:
        svg = os.path.join(fi, "flags", "4x3", f"{code}.svg")
        if not os.path.isfile(svg):
            continue
        name = f"flag_{code}"
        texture(svg, os.path.join(ART, f"{name}.png"))
        tmp = os.path.join(ART, f".{name}.dae")
        write_dae(tmp, make_crowds.flag(), f"egps_{name}", f"{name}.png")
        P, N, UV, T, mat = read_dae(tmp)
        os.unlink(tmp)
        cdae.write(os.path.join(ART, f"{name}.cdae"), P, T, normals=N, uvs=UV, material=mat, object_name="marker")
        made.append(code)
    with open(os.path.join(ART, "LICENSE.txt"), "w", encoding="utf-8") as f:
        f.write("The flags' pictures: flag-icons (https://github.com/lipis/flag-icons)\n\n")
        with open(os.path.join(fi, "LICENSE"), encoding="utf-8") as g:
            f.write(g.read())
        f.write("\n\nThe country names (countries.lua): i18n-iso-countries "
                "(https://github.com/michaelwittig/node-i18n-iso-countries)\n\n")
        with open(os.path.join(ic, "LICENSE"), encoding="utf-8") as g:
            f.write(g.read())
    lines = ["-- Made by tools/make_flags.py (do not edit): country names -> ISO 3166-1 codes (names as crowds.flagFor",
             "-- compares them: ASCII letters lowered), and the codes with a flag (art/offroadcompanion/flags/).",
             "-- The names: i18n-iso-countries (MIT); the flags: flag-icons (MIT): flags/LICENSE.txt.",
             "local M = {}", "M.names = {"]
    for n in sorted(names):
        if n:
            lines.append(f"  [{lua_str(n)}] = {lua_str(names[n])},")
    lines.append("}")
    lines.append("M.flags = {")
    for i in range(0, len(made), 12):
        lines.append("  " + " ".join(f"[{lua_str(c)}] = true," for c in made[i:i + 12]))
    lines.append("}")
    lines.append("return M")
    with open(LUA, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(made)} flags in {os.path.normpath(ART)}, {len(names)} names in {os.path.normpath(LUA)}")


if __name__ == "__main__":
    main()
