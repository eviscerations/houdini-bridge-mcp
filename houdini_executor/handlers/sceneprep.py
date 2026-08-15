"""Scene ASSEMBLE / ORGANIZE / PLACE / STAGE / USD-HANDOFF / PACKAGE handlers.

The scene-prep lane: compose many produced geometry results into one navigable, staged,
render-ready, hand-off-able scene through TYPED assembly / metadata nodes only. Data-only,
probe-verified against live H21.0.671 nodes:

  T1  object_merge     -- reference external SOP/OBJ streams into a network (the large-scene primitive)
  T3  subnet_organize  -- graph organization (collapse into subnet / create subnet / tag nodes)
  T5  matchsize        -- fit & align to a reference bbox (drop an asset into place)
  T9  usd_layer        -- multi-branch USD stage assembly (merge / sublayer / graft LOPs)
  T10 usd_configure    -- turn imported geo into a real USD asset (kind/purpose/drawmode/... + variant)
  T12 export_package   -- staged, confined USD handoff write (WIRE-ONLY: caller fires the write)
  T13 scene_assemble   -- one-call staged multi-piece assembly macro (venue-portfolio primitive)

Security posture (identical to the rest of this executor):
  * NO exec / VEX / wrangle / expression authoring / generic set-any-parm. Every parm is a named,
    typed, clamped literal. Menu tokens are the verbatim probed tokens (set by index for index-menus,
    by token string for string-menus -- both are literals, never caller-authored expressions).
  * Confined writes only: export_package resolves its output through confined_path (FsPath write),
    and -- like setup_karma / bake_texture / karma_render_settings -- is WIRE-ONLY: the node is BUILT
    and configured but NOT cooked/rendered on the executor thread (no heavy export cook here; the
    caller/human fires it). Networks are built (single cook where needed), never auto-rendered.

Menu tokens/indices below were live-probed against H21.0.671.
"""

import json
import hou
from houdini_executor.server import (
    endpoint, resolve_node, clamp, confined_path, child_after, stage_context, out_context, bridge_input,
)
from houdini_executor.handlers._parmutil import _try_set


# ── local probe-safe helpers (never invents a parm; mirrors look.py/usd.py/deliver.py _try_set) ──


def _try_set_tuple(node, parm, values):
    """Set a parmTuple iff it exists. Returns True if applied."""
    pt = node.parmTuple(parm)
    if pt is None:
        return False
    try:
        pt.set(tuple(values))
        return True
    except Exception:
        return False


def _coerce_list(val):
    """Accept a JSON array or comma-separated string (the catalog has no list Kind), same coercion
    as the `merge` handler. Returns a list of stripped strings."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    s = str(val).strip()
    if not s:
        return []
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
        return [str(parsed).strip()]
    except Exception:
        return [p.strip() for p in s.split(",") if p.strip()]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T1  object_merge  -- reference external SOP/OBJ streams into a network without copying geometry.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# probe: SOP `object_merge`. multiparm folder `numobj` (count) -> per-instance `objpath#`, `group#`,
# `enable#`. `xformtype` Menu idx {0:none, 1:local(Into This Object), 2:object(Into Specified Object)}
# default 2. `xformpath` String. `pack` Toggle. `viewportlod` Menu {0:full,1:points,2:box,3:centroid,
# 4:hidden}. Spec's `packbyname`/`transfer_attributes` DO NOT EXIST on object_merge (they live on the
# `pack` SOP) -- omitted.
_OBJMERGE_XFORM = {"none": 0, "local": 1, "object": 2}
_VIEWPORT_LOD = {"full": 0, "points": 1, "box": 2, "centroid": 3, "hidden": 4}


def _build_object_merge(parent, sources, name=None, xformtype="none", xformpath=None,
                        pack=False, group=None, viewportlod=None):
    """Create an `object_merge` SOP inside `parent` (a SOP network) referencing `sources` (a list of
    resolved SOP/OBJ paths) by path. Returns the created node. No cook."""
    resolved = [resolve_node(p).path() for p in sources]
    if not resolved:
        raise ValueError("object_merge needs a non-empty 'sources' list of node paths")
    n = parent.createNode("object_merge", name) if name else parent.createNode("object_merge")
    n.parm("numobj").set(len(resolved))
    for i, path in enumerate(resolved, start=1):
        _try_set(n, "objpath%d" % i, path)
        _try_set(n, "enable%d" % i, 1)
        if group:
            _try_set(n, "group%d" % i, str(group))
    xt = _OBJMERGE_XFORM.get(str(xformtype), 0)
    _try_set(n, "xformtype", xt)
    if xt == 2 and xformpath:
        _try_set(n, "xformpath", resolve_node(xformpath).path())
    if pack:
        _try_set(n, "pack", 1)
    if viewportlod is not None and str(viewportlod) in _VIEWPORT_LOD:
        _try_set(n, "viewportlod", _VIEWPORT_LOD[str(viewportlod)])
    n.moveToGoodPosition()
    return n, resolved


@endpoint("object_merge")
def object_merge(params):
    """Reference one or many external SOP/OBJ streams into a SOP network WITHOUT copying geometry --
    the missing large-scene / venue assembly primitive (pulls by path, so it survives huge multi-OBJ
    scenes). `sources` = JSON array or comma list of source node paths. `dest` (opt) = an existing SOP
    network / geo OBJ to build inside; otherwise a fresh /obj geo named `name` is created (FAILS on
    name collision). xformtype: none|local|object (how to transform the merged geo; local=into this
    object, object=into `xformpath`). pack=true packs each source (flat-memory assembly). group
    restricts to a source group. viewportlod: full|points|box|centroid|hidden (display economy)."""
    sources = _coerce_list(params.get("sources") or params.get("objpath"))
    if not sources:
        raise ValueError("object_merge needs a non-empty 'sources' list of node paths")

    dest = params.get("dest")
    made_geo = None
    if dest:
        parent = resolve_node(dest)
        if not hasattr(parent, "createNode"):
            raise ValueError("dest %s cannot contain a SOP" % parent.path())
    else:
        obj = hou.node("/obj")
        geo_name = params.get("name") or "assembly"
        if obj.node(geo_name) is not None:
            raise ValueError("object already exists: %s (use a different name/dest)" % geo_name)
        parent = obj.createNode("geo", geo_name)
        made_geo = parent.path()

    node_name = None if (made_geo and not dest) else params.get("name")
    n, resolved = _build_object_merge(
        parent, sources,
        name=node_name,
        xformtype=params.get("xformtype", "none"),
        xformpath=params.get("xformpath"),
        pack=bool(params.get("pack", False)),
        group=params.get("group"),
        viewportlod=params.get("viewportlod"),
    )
    try:
        n.setDisplayFlag(True)
        n.setRenderFlag(True)
        if made_geo:  # [D2] show the freshly-created object, not just its tail SOP
            parent.setDisplayFlag(True)
    except Exception:
        pass
    return {"node": n.path(), "sources": resolved, "geo": made_geo,
            "xformtype": str(params.get("xformtype", "none")),
            "packed": bool(params.get("pack", False))}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T3  subnet_organize  -- pure graph organization (never touches geometry values).
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# HOM probe: hou.Node.collapseIntoSubnet(child_nodes, subnet_name=None), setColor(hou.Color),
# setComment(str), setGenericFlag(hou.nodeFlag.DisplayComment, True) all present on H21.
@endpoint("subnet_organize")
def subnet_organize(params):
    """Organize the node graph (data-only -- no cook, no VEX, no parm-expression). op:
      collapse -> box a set of sibling node paths into a subnet (`nodes` = JSON array/comma list;
                  `name` opt). All nodes must share one parent.
      create   -> an empty `subnet` container inside `parent` (`name` opt).
      tag      -> set organization metadata on `node`: `color` [r,g,b] (network-editor node color),
                  `comment` (shown when set), `user_key`+`user_value` (a data string).
    The network-editor equivalent of set_color (which colors GEOMETRY); this colors/labels the NODES
    so an assembled graph is navigable."""
    op = str(params.get("op", "tag"))

    if op == "collapse":
        paths = _coerce_list(params.get("nodes"))
        if len(paths) < 1:
            raise ValueError("collapse needs a 'nodes' list of sibling node paths")
        nodes = [resolve_node(p) for p in paths]
        parent = nodes[0].parent()
        for nd in nodes:
            if nd.parent() != parent:
                raise ValueError("all nodes must share one parent for collapse (%s is elsewhere)"
                                 % nd.path())
        # Capture names BEFORE collapse -- collapseIntoSubnet re-parents the nodes and the original
        # hou.Node handles are invalidated (ObjectWasDeleted) once they move into the new subnet.
        collapsed_names = [n.name() for n in nodes]
        sub = parent.collapseIntoSubnet(tuple(nodes), params.get("name"))
        try:
            sub.moveToGoodPosition()
        except Exception:
            pass
        return {"op": op, "subnet": sub.path(), "collapsed": collapsed_names}

    if op == "create":
        parent = resolve_node(params["parent"])
        if not hasattr(parent, "createNode"):
            raise ValueError("parent %s cannot contain a subnet" % parent.path())
        name = params.get("name")
        sub = parent.createNode("subnet", name) if name else parent.createNode("subnet")
        sub.moveToGoodPosition()
        return {"op": op, "subnet": sub.path()}

    if op == "tag":
        node = resolve_node(params["node"])
        applied = {}
        c = params.get("color")
        if c and len(c) == 3:
            try:
                node.setColor(hou.Color(tuple(clamp(float(v), 0.0, 1.0) for v in c)))
                applied["color"] = [clamp(float(v), 0.0, 1.0) for v in c]
            except Exception:
                pass
        if "comment" in params:
            try:
                node.setComment(str(params["comment"]))
                node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
                applied["comment"] = str(params["comment"])
            except Exception:
                pass
        if params.get("user_key"):
            try:
                node.setUserData(str(params["user_key"]), str(params.get("user_value", "")))
                applied["user_key"] = str(params["user_key"])
            except Exception:
                pass
        return {"op": op, "node": node.path(), "applied": applied}

    raise ValueError("op must be collapse|create|tag")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T5  matchsize  -- fit and/or align the input to a reference bbox (place an asset at the right size).
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# probe: SOP `matchsize`. `justifytarget` Menu {0:origin, 1:input(2nd input bbox), 2:explicit(size),
# 3:auto(input-if-wired)} default 3. `justify_x/y/z` Menu {0:none,1:min,2:center,3:max} default 2.
# `sizex`/`sizey`/`sizez` (individual; parmTuple `size` too). `dotranslate`/`doscale` Toggle,
# `uniformscale` Toggle default 1. `group`/`grouptype` for restriction. Spec's `dofit`/`singlebbox`/
# `justifytoinput`/`srcgroup` DO NOT EXIST -- the real knob is `justifytarget`.
_MATCH_TARGET = {"origin": 0, "input": 1, "explicit": 2, "auto": 3}
_MATCH_JUSTIFY = {"none": 0, "min": 1, "center": 2, "max": 3}


def _build_matchsize(input_node_path, reference=None, size=None, justify="center",
                     doscale=True, uniformscale=True, dotranslate=True, target=None, name=None,
                     group=None):
    """Create a `matchsize` SOP after `input_node_path`. If `reference` is given it is wired as the
    second input and justifytarget=input; if `size` [x,y,z] is given, justifytarget=explicit. `group`
    (optional) restricts which part of the input geometry defines the source bbox. Returns the created
    node. No cook."""
    n = child_after(input_node_path, "matchsize", name)
    tgt = target
    if tgt is None:
        if reference is not None:
            tgt = "input"
        elif size is not None:
            tgt = "explicit"
        else:
            tgt = "auto"
    if reference is not None:
        ref = resolve_node(reference)
        # matchsize's second input takes the geometry whose bbox to match. If the reference lives in
        # the SAME SOP network, wire it directly; otherwise (a different OBJ/geo) bridge it in with an
        # object_merge so cross-network references work (SOPs can't be wired across networks).
        same_net = (isinstance(ref, hou.SopNode) and ref.parent() == n.parent())
        if same_net:
            n.setInput(1, ref)
        else:
            bridge, _ = _build_object_merge(n.parent(), [ref.path()],
                                            name=(n.name() + "_ref"), pack=False)
            n.setInput(1, bridge)
    _try_set(n, "justifytarget", _MATCH_TARGET.get(str(tgt), 3))
    if size is not None and len(size) == 3:
        if not _try_set_tuple(n, "size", [float(v) for v in size]):
            for pn, v in zip(("sizex", "sizey", "sizez"), size):
                _try_set(n, pn, float(v))
    ji = _MATCH_JUSTIFY.get(str(justify), 2)
    for ax in ("justify_x", "justify_y", "justify_z"):
        _try_set(n, ax, ji)
    _try_set(n, "dotranslate", 1 if dotranslate else 0)
    _try_set(n, "doscale", 1 if doscale else 0)
    _try_set(n, "uniformscale", 1 if uniformscale else 0)
    if group is not None:
        _try_set(n, "group", str(group))
    return n


@endpoint("matchsize")
def matchsize(params):
    """Fit/resize/reposition/align `input` to a reference bounding box or explicit size -- the typed
    'drop this asset into the scene at the right size/position' node. Provide either `reference` (a node
    whose bbox to match -- wired as the 2nd input) OR `size` [x,y,z] (an explicit target size). justify:
    none|min|center|max (applied to all three axes). doscale (default true), uniformscale (default true:
    fit uniformly vs stretch), dotranslate (default true). `group` (optional) restricts which part of
    the input defines the source bbox."""
    n = _build_matchsize(
        params["input"],
        reference=params.get("reference"),
        size=params.get("size"),
        justify=params.get("justify", "center"),
        doscale=bool(params.get("doscale", True)),
        uniformscale=bool(params.get("uniformscale", True)),
        dotranslate=bool(params.get("dotranslate", True)),
        target=params.get("target"),
        name=params.get("name"),
        group=params.get("group"),
    )
    n.geometry()  # single cook to realize
    return {"node": n.path()}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T9  usd_layer  -- multi-branch USD stage assembly (beyond single-file usd_import).
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# probe (LOP): `merge` mergestyle STRING-menu tokens {separate, separateweakfiles,
# separateweakfilesandsops, flattened, flattenintoinputlayer, flatteninputs, flattenloplayers};
# inputs wired input0..N (no count parm). `sublayer` multiparm `num_files` -> `filepath#`/`enable#`;
# `sublayertype` {filesandinputs,files,inputs}. `graftbranches` `primpath` (dest root) + multiparm
# `primcount` -> `srcprimpath#`/`dstprimpath#`/`enable#`; inputs: 0=Input Stage, 1=Source for Grafting.
# Spec's `mergestyle`=separate/flatten-input-layers, `sublayermode`/`stronger`, `destpath`/
# `graftlocation`/`graftprimpath` were WRONG -- real names above.
_MERGESTYLE = ("separate", "separateweakfiles", "separateweakfilesandsops", "flattened",
               "flattenintoinputlayer", "flatteninputs", "flattenloplayers")


def _lop_after(ntype, name=None, after=None):
    if after:
        src = resolve_node(after)
        parent = src.parent()
        n = parent.createNode(ntype, name) if name else parent.createNode(ntype)
        n.setInput(0, src)
    else:
        stage = stage_context()
        n = stage.createNode(ntype, name) if name else stage.createNode(ntype)
    n.moveToGoodPosition()
    return n


@endpoint("usd_layer")
def usd_layer(params):
    """Multi-branch USD stage assembly. op:
      merge    -> `merge` LOP combining several LOP branches into one stage. `inputs` = JSON array/
                  comma list of LOP paths (wired input0..N). mergestyle: one of the probed tokens
                  (default flattenloplayers = Simple Merge).
      sublayer -> `sublayer` LOP composing `.usd` files as sublayers. `files` = JSON array/comma list
                  of USD files (read-confined). `input` (opt) = a LOP to layer onto (input0).
      graft    -> `graftbranches` LOP slotting a source subtree under a destination prim. `input` =
                  Input Stage LOP (input0); `source` = the LOP to graft (input1); `primpath` = dest
                  parent prim; `src_prims` / `dst_prims` = JSON array/comma lists of source and (opt)
                  destination prim paths."""
    op = str(params.get("op", "merge"))

    if op == "merge":
        inputs = _coerce_list(params.get("inputs"))
        if not inputs:
            raise ValueError("usd_layer merge needs a non-empty 'inputs' list of LOP paths")
        nodes = [resolve_node(p) for p in inputs]
        parent = nodes[0].parent()
        n = parent.createNode("merge", params.get("name")) if params.get("name") \
            else parent.createNode("merge")
        for i, nd in enumerate(nodes):
            n.setInput(i, nd)
        style = str(params.get("mergestyle", "flattenloplayers"))
        if style in _MERGESTYLE:
            _try_set(n, "mergestyle", style)
        n.moveToGoodPosition()
        n.cook(force=True)
        return {"op": op, "node": n.path(), "merged": len(nodes), "mergestyle": style}

    if op == "sublayer":
        files = _coerce_list(params.get("files"))
        if not files:
            raise ValueError("usd_layer sublayer needs a non-empty 'files' list of USD files")
        confined = [confined_path(f) for f in files]
        n = _lop_after("sublayer", params.get("name"), params.get("input"))
        n.parm("num_files").set(len(confined))
        for i, path in enumerate(confined, start=1):
            _try_set(n, "filepath%d" % i, path)
            _try_set(n, "enable%d" % i, 1)
        n.cook(force=True)
        return {"op": op, "node": n.path(), "files": confined}

    if op == "graft":
        n = _lop_after("graftbranches", params.get("name"), params.get("input"))
        if params.get("source"):
            bridge_input(n, params["source"], index=1, name_hint="source")
        if params.get("primpath"):
            _try_set(n, "primpath", str(params["primpath"]))
        src_prims = _coerce_list(params.get("src_prims"))
        dst_prims = _coerce_list(params.get("dst_prims"))
        if src_prims:
            n.parm("primcount").set(len(src_prims))
            for i, sp in enumerate(src_prims, start=1):
                _try_set(n, "srcprimpath%d" % i, str(sp))
                _try_set(n, "enable%d" % i, 1)
                if i - 1 < len(dst_prims):
                    _try_set(n, "dstprimpath%d" % i, str(dst_prims[i - 1]))
        n.cook(force=True)
        return {"op": op, "node": n.path(), "src_prims": src_prims, "dst_prims": dst_prims}

    raise ValueError("op must be merge|sublayer|graft")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T10  usd_configure  -- turn imported geo into a real, LOD-carrying USD asset (pure metadata).
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# probe (LOP `configureprimitive`): `primpattern`. Each attr gated by its set* toggle. String-menus:
#   kind        {'':None, assembly, group, component, subcomponent}
#   purpose     {default, proxy, render, guide}
#   drawmode    {default, origin, bounds, cards}   (needs applydrawmode=on to take effect)
#   specifier   {def, over, class}
#   instanceable{notinstanceable, instanceable}
#   visibility  {inherit, invisible, visible}
# toggles: setkind/setpurpose/setdrawmode/setapplydrawmode/applydrawmode/setspecifier/
#   setinstanceable/setvisibility. Spec's `setvis`/`vis` -> real `setvisibility`/`visibility`; spec's
#   `setactive`/`active` DO NOT EXIST -- omitted.
# probe (LOP `setvariant`): multiparm `num_variants` -> `primpattern#`/`variantset#`/`variantname#`.
_KIND = ("assembly", "group", "component", "subcomponent")
_PURPOSE = ("default", "proxy", "render", "guide")
_DRAWMODE = ("default", "origin", "bounds", "cards")
_SPECIFIER = ("def", "over", "class")
_VISIBILITY = ("inherit", "invisible", "visible")


def _build_configure(primpattern, after=None, name=None, kind=None, purpose=None, drawmode=None,
                     instanceable=None, visibility=None, specifier=None):
    n = _lop_after("configureprimitive", name, after)
    _try_set(n, "primpattern", str(primpattern))
    if kind and str(kind) in _KIND:
        _try_set(n, "setkind", 1)
        _try_set(n, "kind", str(kind))
    if purpose and str(purpose) in _PURPOSE:
        _try_set(n, "setpurpose", 1)
        _try_set(n, "purpose", str(purpose))
    if drawmode and str(drawmode) in _DRAWMODE:
        _try_set(n, "setdrawmode", 1)
        _try_set(n, "drawmode", str(drawmode))
        # drawmode only renders as a proxy when applydrawmode is on -- enable it for non-default.
        if str(drawmode) != "default":
            _try_set(n, "setapplydrawmode", 1)
            _try_set(n, "applydrawmode", 1)
    if instanceable is not None:
        _try_set(n, "setinstanceable", 1)
        _try_set(n, "instanceable", "instanceable" if bool(instanceable) else "notinstanceable")
    if visibility and str(visibility) in _VISIBILITY:
        _try_set(n, "setvisibility", 1)
        _try_set(n, "visibility", str(visibility))
    if specifier and str(specifier) in _SPECIFIER:
        _try_set(n, "setspecifier", 1)
        _try_set(n, "specifier", str(specifier))
    return n


@endpoint("usd_configure")
def usd_configure(params):
    """Author USD asset metadata (the native proxy-LOD + hierarchy a downstream studio needs) -- pure
    metadata, no shader/VEX. op:
      configure (default) -> `configureprimitive` LOP on `primpattern`:
          kind: assembly|group|component|subcomponent   (asset hierarchy)
          purpose: default|proxy|render|guide
          drawmode: default|origin|bounds|cards          (USD-native proxy LOD -- heavy assets draw as
                     bounds/cards in the assembly stage, full geo at render)
          instanceable (bool), visibility: inherit|invisible|visible, specifier: def|over|class
      variant -> `setvariant` LOP: `primpattern`, `variantset`, `variantname` (LOD/look selection).
    `input` (opt) = a LOP to layer onto."""
    op = str(params.get("op", "configure"))

    if op == "variant":
        n = _lop_after("setvariant", params.get("name"), params.get("input"))
        n.parm("num_variants").set(1)
        _try_set(n, "primpattern1", str(params.get("primpattern", "")))
        if params.get("variantset"):
            _try_set(n, "variantset1", str(params["variantset"]))
        if params.get("variantname"):
            _try_set(n, "variantname1", str(params["variantname"]))
        _try_set(n, "enable1", 1)
        n.cook(force=True)
        return {"op": op, "node": n.path(),
                "variantset": params.get("variantset"), "variantname": params.get("variantname")}

    if op == "configure":
        if not params.get("primpattern"):
            raise ValueError("usd_configure needs a 'primpattern' (target prims)")
        n = _build_configure(
            params["primpattern"], after=params.get("input"), name=params.get("name"),
            kind=params.get("kind"), purpose=params.get("purpose"), drawmode=params.get("drawmode"),
            instanceable=params.get("instanceable"), visibility=params.get("visibility"),
            specifier=params.get("specifier"),
        )
        n.cook(force=True)
        return {"op": op, "node": n.path(), "primpattern": str(params["primpattern"])}

    raise ValueError("op must be configure|variant")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T12  export_package  -- staged, confined USD handoff write. WIRE-ONLY (caller fires the write).
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# probe (`usd` ROP, category Driver): `loppath`, `lopoutput`, `savestyle` STRING-menu
# {flattenimplicitlayers, flattenalllayers, separate, flattenstage}, `trange` Menu {0:off,1:normal,
# 2:on,3:stage}, `f1`/`f2` (frame range). NO `mkpath`/`flattenstage`/`flattenimplicit` toggles --
# packaging is the single `savestyle` menu; we mkpath the confined parent ourselves.
_SAVESTYLE = ("flattenimplicitlayers", "flattenalllayers", "separate", "flattenstage")


@endpoint("export_package")
def export_package(params):
    """WIRE-ONLY staged USD handoff: build + fully configure a `usd` ROP for a confined package write,
    but do NOT execute (same posture as setup_karma / bake_texture -- a whole-stage flatten is a
    potentially heavy write, so the caller/human fires it). `loppath` = the assembled LOP stage.
    `output` = a confined .usd/.usda/.usdc/.usdz path under the working directory (its parent dir is
    created). savestyle: flattenimplicitlayers (default) | flattenalllayers | separate | flattenstage.
    `frames` [start,end] = an animated handoff (else current frame). Returns the ROP path; rendered=
    False."""
    import os
    out_path = confined_path(params["output"])
    if not out_path.lower().endswith((".usd", ".usda", ".usdc", ".usdz")):
        raise ValueError("output must end in .usd / .usda / .usdc / .usdz")
    if not params.get("loppath"):
        raise ValueError("export_package needs a 'loppath' (the assembled LOP stage)")
    lop = resolve_node(params["loppath"])

    n = out_context().createNode("usd", params.get("name"))
    _try_set(n, "loppath", lop.path())
    n.parm("lopoutput").set(out_path)
    style = str(params.get("savestyle", "flattenimplicitlayers"))
    if style in _SAVESTYLE:
        _try_set(n, "savestyle", style)
    frames = params.get("frames")
    if frames and len(frames) == 2:
        _try_set(n, "trange", 1)  # 1 = Render Specific Frame Range
        f1 = int(clamp(int(frames[0]), -100000, 100000))
        f2 = int(clamp(int(frames[1]), f1, 100000))
        # The usd ROP's f1/f2 ship with default $FSTART/$FEND expression keyframes; a plain .set() is
        # masked by the expression, so clear the keyframes first, then set the literal frame.
        for pn, v in (("f1", f1), ("f2", f2)):
            p = n.parm(pn)
            if p is not None:
                try:
                    p.deleteAllKeyframes()
                    p.set(v)
                except Exception:
                    pass
    # No mkpath parm on the usd ROP -> create the confined parent dir so the wired ROP is fireable.
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    except Exception:
        pass
    n.moveToGoodPosition()
    return {"node": n.path(), "output": out_path, "savestyle": style, "rendered": False,
            "note": "USD package ROP wired + confined; start the write yourself"}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# T13  scene_assemble  -- the venue-portfolio macro: one call builds a staged multi-piece scene.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _build_piece_material(sop_node, basecolor):
    """Assign a typed principledshader::2.0 (basecolor only) to `sop_node` via a Material SOP, wired
    downstream. Data-only literal params -- no VOP graph. Returns the material SOP."""
    parent = sop_node.parent()
    mat = parent.createNode("material")
    mat.setInput(0, sop_node)
    matnet = hou.node("/mat") or hou.node("/").createNode("mat")
    sh = matnet.createNode("principledshader::2.0")
    if basecolor and len(basecolor) == 3:
        _try_set(sh, "basecolorr", clamp(float(basecolor[0]), 0.0, 1.0))
        _try_set(sh, "basecolorg", clamp(float(basecolor[1]), 0.0, 1.0))
        _try_set(sh, "basecolorb", clamp(float(basecolor[2]), 0.0, 1.0))
    _try_set(mat, "shop_materialpath1", sh.path())
    mat.moveToGoodPosition()
    return mat


@endpoint("scene_assemble")
def scene_assemble(params):
    """One-call staged multi-piece assembly (the venue-portfolio primitive). Builds, in a single fresh
    /obj geo (`name`, FAILS on collision), a navigable assembled scene:
      1. object_merge each source (pack=true for flat memory);
      2. per-piece xform (t/r/s literals) and/or matchsize (fit to a reference node's bbox);
      3. per-piece network-node color tag + node name (navigable graph);
      4. optional per-piece basecolor material (typed principledshader, basecolor only);
      5. merge all pieces -> one assembled stream;
      6. optional sop_import -> a USD stage prim + configureprimitive kind=component (handoff-ready).
    `pieces` = a JSON string (the catalog has no object-array Kind): a list of objects, each:
      {path (req), t?[3], r?[3], s?[3]|scalar, match? (a node path to fit to), color?[3],
       material?[3] (basecolor)}.
    `to_usd` (bool) stages the merged result to USD; `usd_path` (opt) = the stage prim prefix.
    BUILT, never rendered -- the caller/human fires any render/export."""
    name = params.get("name")
    if not name:
        raise ValueError("scene_assemble needs a 'name' for the new /obj geometry")
    obj = hou.node("/obj")
    if obj.node(name) is not None:
        raise ValueError("object already exists: %s (use a different name)" % name)

    raw = params.get("pieces")
    if isinstance(raw, str):
        try:
            pieces = json.loads(raw)
        except Exception as exc:
            raise ValueError("pieces must be a JSON array of piece objects: %s" % exc)
    else:
        pieces = raw
    if not isinstance(pieces, list) or not pieces:
        raise ValueError("scene_assemble needs a non-empty 'pieces' JSON array")

    geo = obj.createNode("geo", name)
    built = []
    tails = []  # the last SOP of each piece chain, to be merged

    # a small deterministic palette so each piece node is visually distinct in the network editor
    palette = [(0.9, 0.4, 0.4), (0.4, 0.7, 0.9), (0.5, 0.9, 0.5), (0.9, 0.8, 0.4),
               (0.8, 0.5, 0.9), (0.5, 0.9, 0.85), (0.9, 0.6, 0.4), (0.7, 0.7, 0.7)]

    for idx, piece in enumerate(pieces):
        if not isinstance(piece, dict) or not piece.get("path"):
            raise ValueError("piece %d must be an object with a 'path'" % idx)
        pname = piece.get("name") or ("piece%d" % (idx + 1))
        om, _ = _build_object_merge(geo, [piece["path"]], name=pname, pack=True)
        tail = om

        # matchsize (fit to a reference node's bbox) takes precedence as the placement primitive.
        if piece.get("match"):
            tail = _build_matchsize(tail.path(), reference=piece["match"],
                                    justify=piece.get("justify", "center"),
                                    name=pname + "_match")

        # explicit per-piece transform (literal t/r/s) via a plain xform SOP.
        t, r, s = piece.get("t"), piece.get("r"), piece.get("s")
        if any(v is not None for v in (t, r, s)):
            x = geo.createNode("xform", pname + "_xform")
            x.setInput(0, tail)
            if t and len(t) == 3:
                _try_set_tuple(x, "t", [float(v) for v in t])
            if r and len(r) == 3:
                _try_set_tuple(x, "r", [float(v) for v in r])
            if s is not None:
                if isinstance(s, (list, tuple)) and len(s) == 3:
                    _try_set_tuple(x, "s", [float(v) for v in s])
                else:
                    _try_set(x, "scale", float(s))
            x.moveToGoodPosition()
            tail = x

        if piece.get("material"):
            tail = _build_piece_material(tail, piece["material"])

        # navigable-graph tag: color the piece's head node.
        col = piece.get("color") or palette[idx % len(palette)]
        try:
            om.setColor(hou.Color(tuple(clamp(float(v), 0.0, 1.0) for v in col)))
            om.setComment(pname)
            om.setGenericFlag(hou.nodeFlag.DisplayComment, True)
        except Exception:
            pass

        tails.append(tail)
        built.append({"piece": pname, "object_merge": om.path(), "tail": tail.path()})

    # merge all piece tails into one assembled stream.
    if len(tails) == 1:
        merged = tails[0]
    else:
        merged = geo.createNode("merge", "assembled")
        for i, nd in enumerate(tails):
            merged.setInput(i, nd)
        merged.moveToGoodPosition()
    try:
        merged.setDisplayFlag(True)
        merged.setRenderFlag(True)
        geo.setDisplayFlag(True)  # [D2] show the containing object, not just its tail SOP
    except Exception:
        pass

    geo.layoutChildren()
    out = {"geo": geo.path(), "pieces": built, "assembled": merged.path()}

    # optional USD handoff: SOP -> stage, then configure the root prim as a component.
    if params.get("to_usd"):
        si = stage_context().createNode("sopimport")
        _try_set(si, "soppath", merged.path())
        prefix = params.get("usd_path") or ("/" + name)
        _try_set(si, "enable_pathprefix", 1)
        _try_set(si, "pathprefix", str(prefix))
        si.moveToGoodPosition()
        cfg = _build_configure(prefix, after=si.path(), kind="component")
        cfg.cook(force=True)
        out["usd_stage"] = si.path()
        out["usd_configure"] = cfg.path()
        out["usd_prim"] = prefix

    return out
