"""The course markers as BeamNG's own binary shapes (.cdae), next to their .dae (mod/.../art/offroadcompanion/).

A TSStatic takes a .cdae shapeName directly, without the game's Collada import (BeamNG.Earth gives the game its
generated shapes this way). Written with BeamNG.Earth's own writer (server/cdae.py), so the files are what the engine
itself would compile from the .dae. Run after tools/make_markers.py:
    EARTH_ROOT=/path/to/BeamNG.Earth python3 tools/make_cdae.py
"""
import glob
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mod", "offroad_companion", "art", "offroadcompanion")
NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
LOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "lod")     # (tools/make_crowds.py's)
# the detailed models' switch to their simple far level: the shape's size on screen (px) below which the simple one is
# drawn (a person ~45 px: about 40 m away on a 1080p screen; a stretch of crowd and a truck from a little further)
LOD_PX = [("fan_", 45), ("crowd_", 75), ("pickup_", 90), ("suv_", 90)]


def read_dae(path):
    """(positions (n, 3), normals (n, 3), uvs (n, 2), tris (m, 3), material) of a one-mesh dae: one vertex per
    triangle corner."""
    root = ET.parse(path).getroot()
    mesh = root.find(".//c:mesh", NS)
    src = {s.get("id"): np.array(s.find("c:float_array", NS).text.split(), float) for s in mesh.findall("c:source", NS)}
    tri = mesh.find("c:triangles", NS)
    inputs = tri.findall("c:input", NS)
    stride = max(int(i.get("offset")) for i in inputs) + 1
    idx = np.array(tri.find("c:p", NS).text.split(), int).reshape(-1, stride)
    cols = {}
    for i in inputs:
        sem, off, sid = i.get("semantic"), int(i.get("offset")), i.get("source")[1:]
        if sem == "VERTEX":
            sid = mesh.find("c:vertices/c:input", NS).get("source")[1:]
            cols["P"] = src[sid].reshape(-1, 3)[idx[:, off]]
        elif sem == "NORMAL":
            cols["N"] = src[sid].reshape(-1, 3)[idx[:, off]]
        elif sem == "TEXCOORD":
            cols["UV"] = src[sid].reshape(-1, 2)[idx[:, off]]
    mat = root.find(".//c:instance_material", NS).get("target").lstrip("#")
    n = len(cols["P"])
    return cols["P"], cols.get("N"), cols["UV"], np.arange(n).reshape(-1, 3), mat


def main():
    earth = os.environ.get("EARTH_ROOT")
    if not earth:
        sys.exit("set EARTH_ROOT to a BeamNG.Earth checkout (its server/cdae.py writes the shapes)")
    sys.path.insert(0, os.path.join(earth, "server"))
    import cdae
    for dae in sorted(glob.glob(os.path.join(ART, "*.dae"))):
        P, N, UV, T, mat = read_dae(dae)
        out = dae[:-4] + ".cdae"
        name = os.path.basename(dae)[:-4]
        lods, note = None, ""
        lod = os.path.join(LOD_DIR, os.path.basename(dae))
        if os.path.isfile(lod):         # a detailed model: its simple one drawn once it is small on screen
            Pl, _Nl, UVl, Tl, _m = read_dae(lod)
            px = next(v for k, v in LOD_PX if name.startswith(k))
            lods = [(px, {"positions": Pl, "tris": Tl, "uvs": UVl})]
            note = f", far ({px} px down): {len(Tl)}"
        size = cdae.write(out, P, T, normals=N, uvs=UV, material=mat, object_name="marker", lods=lods)
        back = cdae.read(out)
        print(f"{os.path.basename(out)}: {len(T)} triangles{note}, material {mat}, {size} bytes, read back "
              f"{type(back).__name__}")


if __name__ == "__main__":
    main()
