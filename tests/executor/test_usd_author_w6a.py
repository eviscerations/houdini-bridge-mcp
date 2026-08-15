"""MAIN independent verification of the WS5 W6a LOP/USD authoring lane (37 nodes) via the REAL
handler dispatch path. LOP context = /stage; readback = node.stage().Traverse() prim paths.
Fixture: usd_prim_cube seeds a /stage with a Cube; prim-creation generators each author their prim;
key operators (xform/prune/duplicate/scope) chain onto the cube stage; multi-input ops (graft/
component*/instancer) build+wire and return gracefully. Exit 1 on ANY failure."""
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


# ── fixture: a base /stage with a Cube ───────────────────────────────────────────────────────────────
base = call("usd_prim_cube", {"primpath": "/cube1"})
check(base.get("prims") and any("cube" in p.lower() for p in base["prims"]),
      f"fixture usd_prim_cube authored ({base.get('prims')})")
basenode = base["node"]

PRIM_GEN = [
    "usd_prim_cone", "usd_prim_cylinder", "usd_prim_sphere", "usd_prim_capsule", "usd_prim_mesh",
    "usd_prim_points", "usd_prim_basiscurves", "usd_prim_hermitecurves", "usd_prim_primitive",
]
# operators that cook on a plain cube stage
OP_MUST = ["usd_xform", "usd_prune", "usd_duplicate", "usd_scope", "usd_create_xform"]
# everything else: build + wire + return gracefully (need instancer/material/variant/source context)
OP_GRACE = [
    "usd_instancer", "usd_component_geometry_variants",
    "usd_component_material", "usd_layout", "usd_scene_import", "usd_graft_stages",
    "usd_graft_branches", "usd_restructure_scenegraph", "usd_split_scene", "usd_isolate_scene",
    "usd_collection", "usd_split_primitive", "usd_point_xform", "usd_transform_uv",
    "usd_resample_transforms", "usd_retime_instances", "usd_extract_instances",
    "usd_merge_point_instancers", "usd_split_point_instancers", "usd_modify_point_instances",
    "usd_coordsys",
]

# prim generators — each authors its own prim on /stage
for name in PRIM_GEN:
    try:
        res = call(name, {})
        check(bool(res.get("prims")), f"{name} authored ({len(res.get('prims') or [])} prims)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# usd_component_geometry is a 0-input generator (driven by its own SOP subnet) — no wire required
try:
    res = call("usd_component_geometry", {})
    check(hou.node(res["node"]) is not None, f"usd_component_geometry built ({len(res.get('prims') or [])} prims)")
except Exception as ex:  # noqa: BLE001
    check(False, f"usd_component_geometry raised: {ex}")

# must-cook operators on the cube stage
for name in OP_MUST:
    try:
        p = {} if name == "usd_create_xform" else {"input": basenode}
        res = call(name, p)
        n = hou.node(res["node"])
        wired = (name == "usd_create_xform") or (n.inputs() and n.inputs()[0] is not None)
        check(bool(res.get("prims")) and wired, f"{name} cooked ({len(res.get('prims') or [])} prims)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# graceful operators — must not raise, must build+wire
for name in OP_GRACE:
    try:
        res = call(name, {"input": basenode})
        n = hou.node(res["node"])
        check(n is not None and n.inputs() and n.inputs()[0] is not None,
              f"{name} built+wired ({len(res.get('prims') or [])} prims)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── menu-bite check: usd_prim_cone axis ───────────────────────────────────────────────────────────────
c = call("usd_prim_cone", {"axis": "Z"})
cn = hou.node(c["node"])
if cn and cn.parm("axis"):
    check(cn.parm("axis").evalAsString() in ("Z", "z"), "usd_prim_cone menu axis='Z' applied")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)
