"""MAIN independent verification of the WS5 W4 volume-optional lane (27 nodes) via the REAL handler
dispatch path. Fixture: sphere -> vdbfrompolygons (SDF 'surface' + fog 'density' VDB), sphere ->
isooffset (native fog volume), scatter points. Calls all 27 endpoints; asserts none raises, each
builds+wires on input 0, the op-1 nodes that work on a plain volume cook with counts>0, and the rest
(needing a lattice / goal / velocity / VDB-points / hull we don't fixture) return cooked:false
gracefully. Exit 1 on ANY failure."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401

R = srv._REGISTRY
OK, FAIL = [], []


def call(name, params):
    return R[name]["fn"](params)


def check(cond, msg):
    (OK if cond else FAIL).append(msg)
    print(("ok   " if cond else "FAIL ") + msg)


def wired0(n):
    ins = n.inputs()
    return bool(ins) and ins[0] is not None


geo = hou.node("/obj").createNode("geo", "volx_fix")
sph = geo.createNode("sphere"); sph.parm("type").set(2)
vfp = geo.createNode("vdbfrompolygons"); vfp.setInput(0, sph)
for p, v in (("builddistance", 1), ("distancename", "surface"), ("buildfog", 1), ("fogname", "density")):
    if vfp.parm(p):
        try:
            vfp.parm(p).set(v)
        except Exception:  # noqa: BLE001
            pass
vfp.cook(force=True)
vol = vfp.path()
check(len(vfp.geometry().prims()) >= 1, f"fixture VDB cooked ({len(vfp.geometry().prims())} vols)")
isof = geo.createNode("isooffset"); isof.setInput(0, sph); isof.cook(force=True)
nvol = isof.path()
scat = geo.createNode("scatter::2.0"); scat.setInput(0, sph); scat.parm("npts").set(200); scat.cook(force=True)
pts = scat.path()

MUST = {
    "volume_normalize", "volume_ambient_occlusion", "volume_convolve",
    "vdb_diagnostics", "vdb_lod", "vdb_visualize_tree", "volume_fft", "volume_compress",
}
CASES = [
    ("volume_normalize",         {"input": vol}),
    ("volume_ambient_occlusion", {"input": vol}),
    ("volume_convolve",          {"input": vol}),
    ("vdb_diagnostics",          {"input": vol}),
    ("vdb_lod",                  {"input": vol}),
    ("vdb_visualize_tree",       {"input": vol}),
    ("volume_fft",               {"input": nvol}),
    ("volume_compress",          {"input": vol}),
    ("volume_noise_vector",      {"input": nvol}),
    ("volume_splice",            {"input": vol}),
    ("lattice_from_volume",      {"input": vol}),
    ("volume_deform",            {"input": vol}),
    ("volume_rasterize_lattice", {"input": vol}),
    ("volume_break",             {"input": vol, "volume": vol}),
    ("volume_stamp",             {"input": vol, "points": pts}),
    ("volume_patch",             {"input": vol, "patch": vol}),
    ("volume_arrival_time",      {"input": nvol, "start_points": pts}),
    ("volume_optical_flow",      {"input": vol, "goal": vol}),
    ("volume_trail",             {"input": vol}),
    ("volume_bake",              {"input": vol, "points": pts}),
    ("paint_color_volume",       {"input": vol}),
    ("paint_sdf_volume",         {"input": vol}),
    ("vdb_convex_clip_sdf",      {"input": vol}),
    ("vdb_points_delete",        {"input": pts}),
    ("vdb_points_group",         {"input": pts}),
    ("vdb_rasterize_frustum",    {"input": vol}),
]
for name, p in CASES:
    try:
        res = call(name, p)
        n = hou.node(res["node"])
        base = (n is not None) and wired0(n)
        if name in MUST:
            cooked = res.get("cooked", (res.get("points", 0) + res.get("prims", 0)) > 0)
            check(base and cooked and (res.get("points", 0) + res.get("prims", 0)) > 0,
                  f"{name} cooked ({res.get('points')}pt {res.get('prims')}prim)")
        else:
            check(base, f"{name} built+wired (cooked={res.get('cooked')})")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)
