"""MAIN independent verification of the WS5 W2 groom/hair/guide lane — drives the REAL handler
dispatch path (houdini_executor _REGISTRY) headless. Builds the procedural fixture (grid+normal skin
-> hairgen guides -> guided dense hairs), then calls all 29 endpoints and asserts: none raises, each
builds a node wired on input 0, the core styling/authoring ops cook with counts>0, and a sample of
index- and string-token menus land. Endpoints that legitimately need a VDB / interp-mesh / muscle
input we can't supply here must return cooked:false gracefully (never crash). Exit 1 on ANY failure."""
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


def wired0(node):
    ins = node.inputs()
    return bool(ins) and ins[0] is not None


# ── fixture: skin -> guides -> dense hairs (the probe's procedural recipe) ──────────────────────────
geo = hou.node("/obj").createNode("geo", "groom_fix")
grid = geo.createNode("grid"); grid.parm("rows").set(20); grid.parm("cols").set(20)
nrm = geo.createNode("normal"); nrm.setInput(0, grid)
skin = nrm.path()
hg = geo.createNode("hairgen::2.0"); hg.setInput(0, nrm)
if hg.parm("density"):
    hg.parm("density").set(20)
hg.cook(force=True)
guides = hg.path()
check(len(hg.geometry().prims()) > 0, f"fixture guides cooked ({len(hg.geometry().prims())} prims)")
# dense hairs for the hair_* consumers
hairs_r = call("hair_generate", {"input": skin, "guides": guides, "name": "dense_hairs"})
hairs = hairs_r["node"]
check(hairs_r.get("points", 0) > 0, f"hair_generate (dense) cooked ({hairs_r.get('points')}pts)")

# ── per-endpoint invocation map: (endpoint, params, must_cook) ──────────────────────────────────────
CASES = [
    ("guide_initialize",          {"input": guides, "skin": skin, "windamount": 1.0}, True),
    ("guide_reguide",             {"input": guides, "skin": skin, "densityscale": 50}, True),
    ("guide_process",             {"input": guides, "skin": skin, "op1": "frizz", "blend": 0.5}, True),
    ("guide_mask",                {"input": guides, "skin": skin, "usenoisemask": True}, True),
    ("guide_group",               {"input": guides, "skin": skin}, True),
    ("guide_find_strays",         {"input": guides}, True),
    ("guide_clump_center",        {"input": guides}, True),
    ("guide_skin_attrib_lookup",  {"input": guides, "skin": skin}, True),
    ("guide_tangent_space",       {"input": guides, "skin": skin}, True),
    ("guide_volume",              {"input": guides, "skin": skin}, True),
    ("guide_partition",           {"input": guides, "skin": skin}, True),
    ("guide_interpolation_mesh",  {"input": guides, "skin": skin}, True),
    ("guide_groom",               {"input": guides, "skin": skin}, True),
    # capture/deform node: needs a rest+anim skin/guide pair to produce output (like feather_deform);
    # with only a rest skin it builds+wires and returns cooked:false gracefully.
    ("guide_deform",              {"input": guides, "rest_skin": skin, "mode": "skin"}, False),
    ("hair_clump",                {"input": hairs, "skin": skin, "clumpsize": 0.15}, True),
    ("hair_comb",                 {"input": hairs, "op": "lift", "lift": 0.5}, True),
    ("hair_volume_rasterize",     {"input": hairs, "voxelsize": 0.1}, True),
    ("hair_card_generate",        {"input": hairs, "skin": skin, "numcards": 50}, True),
    # extra-input ops: supply what we can from the fixture; cooked:false is acceptable (graceful).
    ("guide_fill",                {"input": guides}, False),
    ("guide_grow_to_surface",     {"input": guides, "target_surface": skin}, False),
    ("guide_surface",            {"input": guides}, False),
    ("guide_transfer",            {"input": guides, "source_skin": skin, "target_skin": skin}, False),
    ("groom_blend",               {"input": guides, "skin_a": skin, "guides_b": guides, "blend": 0.5}, False),
    ("guide_collide_vdb",         {"input": guides, "skin": skin}, False),
    ("guide_advect",              {"input": guides, "skin": skin}, False),
    ("fur_setup",                 {"input": skin, "guides": guides}, False),
    ("hair_growth_field",         {"input": guides, "skin": skin}, False),
    ("fiber_groom",               {"input": guides}, False),
]
MADE = {}
for name, p, must in CASES:
    try:
        res = call(name, p)
        MADE[name] = res["node"]
        n = hou.node(res["node"])
        ok = (n is not None) and wired0(n)
        if must:
            ok = ok and res.get("cooked") and res.get("points", 0) > 0
            check(ok, f"{name} cooked ({res.get('points')}pts {res.get('prims')}prim)")
        else:
            check(ok, f"{name} built+wired (cooked={res.get('cooked')}; extra input may be needed)")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── menu-bite checks (index + string-token) ─────────────────────────────────────────────────────────
gp = hou.node(MADE.get("guide_process", ""))
if gp:
    check(gp.parm("op1").evalAsString() == "frizz", "guide_process index-menu op1='frizz' applied")
hc = hou.node(MADE.get("hair_clump", ""))
if hc:
    check(hc.parm("method").eval() in (0, 1), "hair_clump index-menu method resolves")
hgf = hou.node(MADE.get("hair_growth_field", ""))
if hgf and hgf.parm("guideadvectiontype"):
    # string-token menu (kind ms) — default '4th rk'; just confirm it holds a valid token
    check(hgf.parm("guideadvectiontype").evalAsString() in
          ("fwd euler", "2nd rk", "3rd rk", "4th rk"), "hair_growth_field string-menu token valid")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)
