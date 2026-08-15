"""MAIN independent verification of the WS5 W5 CHOP procedural-motion lane (46 nodes) via the REAL
handler dispatch path. CHOP context = a chopnet under /obj (NOT a SOP geo); readback = tracks/samples.
Fixture: chop_wave builds a fresh chopnet with a periodic channel; generators reuse that chopnet;
operators wire to the wave channel (child_after into the same net). Asserts: none raises, each cooks
or gracefully reports (tracks/samples + errors), the generators and single-input channel-math ops
produce tracks>0, and a couple of index/string menus land. Exit 1 on ANY failure."""
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


# ── fixture: chop_wave -> fresh chopnet with a 'chan1' periodic channel ──────────────────────────────
g = call("chop_wave", {"name": "chop_fix", "wave_type": "sin", "amp": 2.0})
check(g.get("tracks", 0) >= 1 and g.get("samples", 0) > 0,
      f"fixture chop_wave cooked ({g.get('tracks')}trk {g.get('samples')}smp)")
wave = g["node"]
net = g["chopnet"]

MUST = {
    # generators (cook standalone in the chopnet)
    "chop_wave", "chop_noise", "chop_constant", "chop_waveform", "chop_channel",
    # single-input channel-math operators (cook on the one wave channel)
    "chop_math", "chop_filter", "chop_limit", "chop_lag", "chop_shift",
    "chop_cycle", "chop_resample", "chop_invert", "chop_slope", "chop_stretch", "chop_trim",
    "chop_extend", "chop_null", "chop_delay", "chop_area", "chop_spectrum", "chop_multiply",
}
# chop_hold + function/lookup/blend/warp/copy/composite need a 2nd channel input → graceful (cooked:false)
# generators reuse the fixture chopnet; operators wire to the wave channel
GEN = {"chop_noise", "chop_constant", "chop_waveform", "chop_channel", "chop_spline", "chop_pulse"}
CASES = [
    ("chop_noise", {}), ("chop_constant", {}), ("chop_waveform", {}), ("chop_channel", {}),
    ("chop_spline", {}), ("chop_pulse", {}),
    ("chop_oscillator", {}), ("chop_math", {}), ("chop_function", {}), ("chop_filter", {}),
    ("chop_limit", {}), ("chop_lag", {}), ("chop_lookup", {}), ("chop_cycle", {}),
    ("chop_blend", {}), ("chop_merge", {}), ("chop_warp", {}), ("chop_resample", {}),
    ("chop_shift", {}), ("chop_hold", {}), ("chop_spectrum", {}), ("chop_multiply", {}),
    ("chop_invert", {}), ("chop_extend", {}), ("chop_stretch", {}), ("chop_trim", {}),
    ("chop_area", {}), ("chop_envelope", {}), ("chop_interp", {}), ("chop_delay", {}),
    ("chop_slope", {}), ("chop_fan", {}), ("chop_count", {}), ("chop_null", {}),
    ("chop_vector", {}), ("chop_attribute", {}), ("chop_copy", {}), ("chop_shuffle", {}),
    ("chop_reorder", {}), ("chop_rename", {}), ("chop_delete", {}), ("chop_switch", {}),
    ("chop_layer", {}), ("chop_composite", {}), ("chop_trigger", {}),
]
MADE = {}
for name, extra in CASES:
    p = dict(extra)
    if name in GEN:
        p["chopnet"] = net
    else:
        p["input"] = wave
    try:
        res = call(name, p)
        MADE[name] = res.get("node")
        n = hou.node(res["node"]) if res.get("node") else None
        base = n is not None
        if name not in GEN:  # operator must be wired to input 0
            base = base and n.inputs() and n.inputs()[0] is not None
        if name in MUST:
            ok = base and res.get("tracks", 0) > 0 and not res.get("errors")
            check(ok, f"{name} cooked ({res.get('tracks')}trk {res.get('samples')}smp)")
        else:
            check(base, f"{name} built+wired (trk={res.get('tracks')} err={bool(res.get('errors'))})")
    except Exception as ex:  # noqa: BLE001
        check(False, f"{name} raised: {ex}")

# ── menu-bite checks ────────────────────────────────────────────────────────────────────────────────
wv = hou.node(wave)
if wv:
    check(wv.parm("wavetype").evalAsString() == "sin", "chop_wave index-menu wave_type='sin' applied")

print(f"\n==== {len(OK)} ok / {len(FAIL)} FAIL ====")
sys.exit(1 if FAIL else 0)
