"""ML / ONNX inference + analysis handlers (H21 native ML SOPs). DATA-ONLY: every model is loaded
from a single realpath-confined FileReference param; these nodes expose NO code/callback/custom-op
param (verified probe). The heavy TRAINING nodes are PDG/TOP-only and are deliberately NOT exposed --
this lane is inference + inline-regression + PCA.

SAFETY NOTES (probe-verified the hard way):
  * A malformed `.onnx` SEGFAULTS Houdini when `reload`/`setupshapes` is pressed
    (ML_Model::initializeModel) -- a segfault is not a catchable Python exception, so the handlers
    NEVER auto-press those buttons and NEVER force-cook an unvalidated model. `setup_shapes` is an
    explicit opt-in for callers who trust the model. Acquisition is meant to go through the
    hash-pinned downloader allowlist (Stage 2) so the file is known-good.
  * `neuralpointsurface` presets fetch weights from SideFX over the NETWORK on cook (uncontrolled
    egress) -- deferred to the downloader-gated Stage 2, NOT shipped here.
  * NEVER add a provider-library / custom-op / session-options-file param: that converts the bounded
    tensor graph into an exec surface."""

import hou
from houdini_executor.server import (
    endpoint, child_after, clamp, resolve_node, confined_path, bridge_into,
)
from houdini_executor.handlers._parmutil import _try_set

try:
    from houdini_executor.governor import governor_gate, advise
except Exception:  # noqa: BLE001 — governor is advisory telemetry; never block handler import
    def governor_gate(op_label):
        return {"band": "unknown"}

    def advise(result, node=None):
        return result




def _menu_set(node, parm, token):
    """Set a menu parm by token string, falling back to the token's index in the menu items."""
    p = node.parm(parm)
    if p is None:
        return False
    try:
        p.set(str(token))
        return True
    except Exception:
        pass
    try:
        items = list(p.parmTemplate().menuItems())
        if str(token) in items:
            p.set(items.index(str(token)))
            return True
    except Exception:
        pass
    return False


def _cook_report(node):
    """Cook a node and fold any node errors into the result instead of raising. ONLY for nodes that
    are safe to cook here (no model file). Model-loading nodes are NOT cooked in-handler."""
    try:
        g = node.geometry()
        pts, prims = len(g.points()), len(g.prims())
    except Exception:
        pts = prims = None
    try:
        errs = list(node.errors())
    except Exception:
        errs = []
    out = {"node": node.path(), "points": pts, "prims": prims}
    if errs:
        out["errors"] = errs
    return out


# ── ONNX inference (bounded tensor graph; modelfile confined; NOT force-cooked) ────────────────────
@endpoint("onnx_inference")
def onnx_inference(params):
    """Configure a confined ONNX tensor-graph inference node over point attributes or a volume field.
    Bounded graph only -- NO custom ops, NO code. `modelfile` is realpath-confined to the working dir
    (a .onnx from the trusted downloader). The node is BUILT and bound but NOT cooked here: a malformed
    model can segfault Houdini on load, so the model resolves on downstream cook (with a known-good,
    hash-pinned file). Pass setup_shapes=true ONLY when the model is trusted -- it introspects the graph
    (and would crash on a bad file)."""
    governor_gate("onnx_inference")
    n = child_after(params["input"], "onnx", params.get("name"))
    n.parm("modelfile").set(confined_path(str(params["modelfile"])))  # read-confined
    _try_set(n, "input_name1", str(params["input_name"]))
    _menu_set(n, "input_type1", str(params["input_type"]))
    if params.get("input_data"):
        _try_set(n, "input_data1", str(params["input_data"]))
    if params.get("output_name"):
        _try_set(n, "output_name1", str(params["output_name"]))
    if params.get("output_type"):
        _menu_set(n, "output_type1", str(params["output_type"]))
    if params.get("output_data"):
        _try_set(n, "output_data1", str(params["output_data"]))
    if "max_batch" in params:
        _try_set(n, "domaxbatch", True)
        _try_set(n, "maxbatch", int(clamp(int(params["max_batch"]), 1, 4096)))
    if "keep_input" in params:
        _try_set(n, "keepinput", bool(params["keep_input"]))
    if params.get("setup_shapes"):  # opt-in only (trusted model): introspects the graph, may crash on bad files
        try:
            n.parm("reload").pressButton()
            if n.parm("setupshapes") is not None:
                n.parm("setupshapes").pressButton()
        except Exception:
            pass
    # NOTE: return the plain dict, NOT advise(..., n) -- advise cooks the node to sample geo_cost,
    # which would load the (possibly-unvalidated) model and can segfault. No cook here, by design.
    return {"node": n.path(), "built": True, "cooked": False,
            "note": "model resolves on downstream cook; pass a hash-pinned .onnx"}


# ── ML Volume Upres (learned volumetric super-resolution; modelfile confined; NOT force-cooked) ─────
@endpoint("ml_volume_upres")
def ml_volume_upres(params):
    """Configure a learned volumetric super-resolution node -- sim coarse, upres detail (pyro/fluid
    content lane). `modelfile` is a confined .onnx; `volume` is the field name to upres. Not cooked
    in-handler (same malformed-model safety as onnx_inference)."""
    governor_gate("ml_volume_upres")
    n = child_after(params["input"], "ml_volumeupres", params.get("name"))
    n.parm("modelfile").set(confined_path(str(params["modelfile"])))  # read-confined
    if params.get("volume"):
        _try_set(n, "volume", str(params["volume"]))
    if "scale" in params:
        _try_set(n, "scale", clamp(float(params["scale"]), 1.0, 10.0))  # node `scale` is a FLOAT
    if "tile_size" in params:
        _try_set(n, "tilesize", int(clamp(int(params["tile_size"]), 1, 1024)))
    if "padding" in params:
        _try_set(n, "padding", int(clamp(int(params["padding"]), 0, 256)))
    # plain dict, NOT advise(..., n): advise cooks (loads the model) and can segfault -- see onnx_inference.
    return {"node": n.path(), "built": True, "cooked": False,
            "note": "model resolves on downstream cook; pass a hash-pinned .onnx"}


# ── ML Regression (train-inline + infer; NO model file at all -- the safest ML tool; cooked) ───────
_REGRESSION_TYPE = {"linear": "ml_regressionlinear", "kernel": "ml_regressionkernel",
                    "proximity": "ml_regressionproximity"}


@endpoint("ml_regression")
def ml_regression(params):
    """Train-inline + infer an attribute regression from a Labeled-Examples input. NO model file, NO
    acquisition surface -- the safest ML tool. Wiring (verified): Labeled Examples -> input 0,
    Input Component -> input 1."""
    method = str(params.get("method", "linear"))
    ntype = _REGRESSION_TYPE.get(method)
    if ntype is None:
        raise ValueError("method must be linear|kernel|proximity")
    governor_gate("ml_regression")
    n = child_after(params["input"], ntype, params.get("name"))   # child_after wires data -> input 0
    data_in = n.input(0)
    ex = resolve_node(params["examples"])
    ex_in = bridge_into(ex, n.parent(), xformtype=0, name_hint=ex.name())  # foreign examples -> local
    n.setInput(0, ex_in)        # Labeled Examples -> input 0
    n.setInput(1, data_in)      # Input Component  -> input 1
    if method == "kernel":
        if params.get("kernel"):
            _menu_set(n, "kerneltype", str(params["kernel"]))
        if "width" in params:
            _try_set(n, "width", clamp(float(params["width"]), 1e-4, 1e6))
    if "weight_decay" in params and method != "proximity":
        _try_set(n, "weightdecay", clamp(float(params["weight_decay"]), 0.0, 1e6))
    if params.get("input_attribute"):
        _try_set(n, "inputpointattribute1", str(params["input_attribute"]))
    if params.get("output_attribute"):
        _try_set(n, "outputpointattribute1", str(params["output_attribute"]))
    result = _cook_report(n)
    result["method"] = method
    return advise(result, n)


# ── PCA (dimensionality reduction / projection / reconstruct; no file; cooked) ─────────────────────
@endpoint("pca")
def pca(params):
    """Principal Component Analysis over point/volume attributes -- feature compression, shape-space
    analysis, and the preprocessing front end to ml_regression. No model file. mode: analyse (compute
    components), project (data -> component space), reconstruct. `basis` wires the analysis result to
    input 1 for project/reconstruct."""
    governor_gate("pca")
    n = child_after(params["input"], "pca", params.get("name"))
    if params.get("basis"):
        b = resolve_node(params["basis"])
        n.setInput(1, bridge_into(b, n.parent(), xformtype=0, name_hint=b.name()))
    if params.get("datatype"):
        _menu_set(n, "datatype", str(params["datatype"]))
    if params.get("mode"):
        _menu_set(n, "mode", str(params["mode"]))
    if params.get("attribs"):
        _try_set(n, "attribs", str(params["attribs"]))
    if "components" in params:
        _try_set(n, "comp", int(clamp(int(params["components"]), 1, 4096)))
    return advise(_cook_report(n), n)
