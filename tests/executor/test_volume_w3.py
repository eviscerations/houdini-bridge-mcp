"""MAIN independent verification of the WS5 W3 volume/VDB lane — drives the REAL handler dispatch path
headless. Builds a fixture (sphere -> vdbfrompolygons SDF+fog VDB, plus a point cloud + a curve),
generates a fresh volume + VDB via the two generators, then calls all 30 endpoints. Asserts: none
raises, each builds a node wired on input 0 (operators) or a fresh geo (generators), the core
volume/VDB ops cook with counts>0, and a couple of menus land. Ops needing an input we can't fixture
(camera / brush / specific volume type) return cooked:false gracefully. Exit 1 on ANY failure."""
import sys
import hou
import houdini_executor.server as srv
import houdini_executor.handlers  # noqa: F401  registers every endpoint

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


# ── fixture: sphere -> vdbfrompolygons (SDF 'surface' + fog 'density'), + point cloud + curve ────────
geo = hou.node("/obj").createNode("geo", "vol_fix")
sph = geo.createNode("sphere"); sph.parm("type").set(2)  # polygon
vfp = geo.createNode("vdbfrompolygons"); vfp.setInput(0, sph)
for p, v in (("builddistance", 1), ("distancename", "surface"), ("buildfog", 1), ("fogname", "density")):
    pp = vfp.parm(p)
    if pp is not None:
        try:
            pp.set(v)
        except Exception:  # noqa: BLE001
            pass
vfp.cook(force=True)
vol = vfp.path()
check(len(vfp.geometry().prims()) >= 1, f"fixture VDB cooked ({len(vfp.geometry().prims())} vol prims)")
scat = geo.createNode("scatter::2.0"); scat.setInput(0, sph); scat.parm("npts").set(200); scat.cook(force=True)
pts = scat.path()
line = geo.createNode("line"); line.parm("points").set(5); line.cook(force=True)
crv = line.path()
# a NATIVE fog volume (isooffset) — convertvolume/volumebound need a native volume + iso/value to emit
isof = geo.createNode("isooffset"); isof.setInput(0, sph); isof.cook(force=True)
nvol = isof.path()

MUST = {
    "volume_create", "vdb_create", "volume_analysis", "volume_resample", "volume_convert",
    "vdb_merge", "volume_reduce", "volume_bound", "volume_ramp", "volume_vector_split",
    "points_from_volume", "volume_surface", "vdb_activate_sdf", "vdb_topology_to_sdf",
    "volume_sdf", "volume_noise_fog", "volume_noise_sdf", "volume_adjust_fog", "extrude_volume",
    "volume_feather", "volume_merge",
}
CASES = [
    ("volume_create",                {"name": "gen_vol", "volume_name": "density"}),
    ("vdb_create",                   {"name": "gen_vdb", "grid_name": "surface"}),
    ("volume_analysis",              {"input": vol}),
    ("volume_resample",              {"input": vol}),
    ("volume_convert",               {"input": nvol, "iso": 0.5}),
    ("volume_merge",                 {"input": vol, "merge_volumes": vol}),
    ("vdb_merge",                    {"input": vol}),
    ("volume_reduce",                {"input": vol}),
    ("volume_bound",                 {"input": nvol, "value": 0.1}),
    ("volume_ramp",                  {"input": vol}),
    ("volume_vector_split",          {"input": vol}),
    ("volume_vector_join",           {"input": vol}),
    ("points_from_volume",           {"input": vol}),
    ("volume_surface",               {"input": vol}),
    ("vdb_activate_sdf",             {"input": vol}),
    ("vdb_topology_to_sdf",          {"input": vol}),
    ("volume_sdf",                   {"input": vol}),
    ("volume_noise_fog",             {"input": vol}),
    ("volume_noise_sdf",             {"input": vol}),
    ("volume_adjust_fog",            {"input": vol}),
    ("extrude_volume",               {"input": vol}),
    ("volume_feather",               {"input": vol}),
    ("volume_resize",                {"input": vol}),
    ("volume_from_attrib",           {"input": vol, "point_cloud": pts}),
    ("convert_vdb_points",           {"input": pts}),
    ("paint_fog_volume",             {"input": vol}),
    ("volume_rasterize_curve",       {"input": vol, "curve": crv}),
    ("volume_velocity_from_curves",  {"input": crv}),
    ("volume_velocity_from_surface", {"input": vol}),
    ("vdb_occlusion_mask",           {"input": vol}),
]
MADE = {}
for name, p in CASES:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        n = hou.node(res["node"])
        base_ok = n is not None
        if name not in ("volume_create", "vdb_create"):
            base_ok = base_ok and wired0(n)
        if name in MUST:
            # generators use _finish_geo (no 'cooked' key) — treat counts>0 as cooked
            cooked = res.get("cooked", (res.get("points", 0) + res.get("prims", 0)) > 0)
            ok = base_ok and cooked and (res.get("points", 0) + res.get("prims", 0)) > 0
            check(ok, f"{name} cooked ({res.get('points')}pt {res.get('prims')}prim)")
        else:
            check(base_ok, f"{name} built+wired (cooked={res.get('cooked')})")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── menu-bite checks ────────────────────────────────────────────────────────────────────────────────
va = hou.node(MADE.get("volume_analysis", ""))
if va:
    check(va.geometry() is not None, "volume_analysis produced geometry")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)
