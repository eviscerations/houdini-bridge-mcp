"""MAIN verification of WS5 W6b LOP materials/lights/variants/shot (27 nodes) via the REAL dispatch
path. LOP context = /stage; readback = node.stage().Traverse(). Lights (generators) must author a
light prim; material/variant/edit/shot ops chain onto a base cube stage and must not raise (they
build+wire, cooking gracefully where a material/variant context is absent). Exit 1 on ANY failure."""
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


base = call("usd_prim_cube", {"primpath": "/cube1"})
basenode = base["node"]
check(bool(base.get("prims")), "fixture cube stage")

# standalone light generators that author a light prim -> must produce prims
for name in ["usd_light_distant", "usd_light_portal", "usd_shadow_catcher"]:
    try:
        res = call(name, {})
        check(bool(res.get("prims")), f"{name} authored ({len(res.get('prims') or [])} prims)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")
# context-dependent lights (verified functional with proper input): mixer needs lights, geometry
# light wraps geometry, filter library is an (initially empty) container — assert cooked, not prims>0.
try:
    _lstage = call("usd_light_distant", {})["node"]
    mx = call("usd_light_mixer", {"input": _lstage})
    check(mx.get("cooked") and bool(mx.get("prims")), f"usd_light_mixer cooked on a light stage ({len(mx.get('prims') or [])} prims)")
    gl = call("usd_light_geometry", {"input": basenode})
    check(gl.get("cooked") and bool(gl.get("prims")), f"usd_light_geometry cooked wrapping geometry ({len(gl.get('prims') or [])} prims)")
    lf = call("usd_light_filter_library", {})
    check(lf.get("cooked") and not lf.get("errors"), "usd_light_filter_library cooked (empty container ok)")
except Exception as ex:  # noqa: BLE001
    check(False, f"context-light raised: {ex}")

# everything else: build + return without raising (chain onto the cube where they take input)
GEN_OPT = ["usd_edit_material", "usd_edit_material_properties", "usd_unassign_material",
           "usd_add_variant", "usd_draw_mode", "usd_configure_property", "usd_configure_stage",
           "usd_edit_properties", "usd_store_parameter_values", "usd_edit_xform", "usd_layer_break"]
OP_REQ = ["usd_material_variation", "usd_vary_material_assignment", "usd_explore_variants",
          "usd_create_lod", "usd_auto_select_lod", "usd_set_extents", "usd_set_variant",
          "usd_copy_property", "usd_shot_split", "usd_shot_switch"]
for name in GEN_OPT + OP_REQ:
    try:
        p = {"input": basenode} if name in OP_REQ else {}
        res = call(name, p)
        check(hou.node(res["node"]) is not None, f"{name} built (cooked={res.get('cooked')})")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# menu / attr bite: distant light intensity via xn__ _lop_author
di = call("usd_light_distant", {"intensity": 3.0})
check(bool(di.get("prims")) and any("distant" in p.lower() or "light" in p.lower() for p in di["prims"]),
      "usd_light_distant authored a DistantLight prim")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)
