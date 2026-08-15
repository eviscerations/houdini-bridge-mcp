"""Analysis / point-cloud handlers.

The four wrangle endpoints are SERVER-AUTHORED templates: the caller supplies only clamped
numbers, never a code snippet — the VEX is fixed here (this replaces any raw `pcopen` lane). The
neighbourhood point cap (`maxpts`) is enforced so a query can't blow up on a multi-GB cloud.
`read_geo_stats` reads via intrinsics (never a python point loop). `level` and `isolate` are
ported from proven scripts.
"""

import hou
from houdini_executor.server import endpoint, child_after, clamp, resolve_node, confined_path


def _attr_list(fn):
    out = []
    try:
        for a in fn():
            out.append({"name": a.name(), "type": str(a.dataType()), "size": a.size()})
    except Exception:
        pass
    return out


@endpoint("point_normals")
def point_normals(params):
    """Estimate a per-point normal by plane-fitting the neighbourhood (covariance -> smallest
    eigenvector via power iteration). radius_m clamped; maxpts CAPPED. Writes v@N and f@planar."""
    radius = clamp(float(params.get("radius_m", 1.0)), 1e-4, 1e6)
    maxpts = int(clamp(int(params.get("maxpts", 32)), 3, 256))
    n = child_after(params["input"], "attribwrangle", params.get("name"))
    n.parm("class").set(2)  # Points
    n.parm("snippet").set(
        'float rad = %g; int maxpts = %d;\n'
        'int h = pcopen(0, "P", @P, rad, maxpts);\n'
        'vector pos[] = {};\n'
        'vector mean = 0;\n'
        'while (pciterate(h)) { vector p; pcimport(h, "P", p); push(pos, p); mean += p; }\n'
        'int np = len(pos);\n'
        'if (np >= 3) {\n'
        '  mean /= float(np);\n'
        '  matrix3 C = 0;\n'
        '  foreach (vector p; pos) {\n'
        '    vector d = p - mean;\n'
        '    C.xx += d.x*d.x; C.xy += d.x*d.y; C.xz += d.x*d.z;\n'
        '    C.yy += d.y*d.y; C.yz += d.y*d.z; C.zz += d.z*d.z;\n'
        '  }\n'
        '  C.yx = C.xy; C.zx = C.xz; C.zy = C.yz;\n'
        '  float tr = C.xx + C.yy + C.zz;\n'
        '  matrix3 A = 0; A.xx = tr; A.yy = tr; A.zz = tr; A = A - C;\n'
        '  vector v = {1,1,1};\n'
        '  for (int i = 0; i < 20; i++) { v = normalize(v * A); }\n'
        '  if (v.y < 0) v = -v;\n'
        '  v@N = v;\n'
        '  float sse = 0;\n'
        '  foreach (vector p; pos) { float e = dot(p - mean, v); sse += e*e; }\n'
        '  f@planar = 1.0 - clamp(sse / (tr + 1e-9), 0.0, 1.0);\n'
        '}\n' % (radius, maxpts))
    g = n.geometry()
    return {"node": n.path(), "radius_m": radius, "maxpts": maxpts,
            "points": g.intrinsicValue("pointcount")}


@endpoint("segment_planar")
def segment_planar(params):
    """Classify points as wall vs horizontal from v@N (requires point_normals first). kwall and
    coshoriz are the |N.y| thresholds. Writes i@wall and i@horiz."""
    kwall = clamp(float(params.get("kwall", 0.3)), 0.0, 1.0)
    coshoriz = clamp(float(params.get("coshoriz", 0.85)), 0.0, 1.0)
    n = child_after(params["input"], "attribwrangle", params.get("name"))
    n.parm("class").set(2)
    n.parm("snippet").set(
        'float d = abs(dot(normalize(v@N), {0,1,0}));\n'
        'i@horiz = (d > %g) ? 1 : 0;\n'
        'i@wall = (d < %g) ? 1 : 0;\n' % (coshoriz, kwall))
    g = n.geometry()
    return {"node": n.path(), "kwall": kwall, "coshoriz": coshoriz,
            "points": g.intrinsicValue("pointcount")}


@endpoint("despeckle")
def despeckle(params):
    """Remove isolated points with fewer than min_nbrs neighbours inside radius. radius clamped;
    the neighbour query is capped."""
    radius = clamp(float(params.get("radius", 1.0)), 1e-4, 1e6)
    min_nbrs = int(clamp(int(params.get("min_nbrs", 4)), 1, 256))
    n = child_after(params["input"], "attribwrangle", params.get("name"))
    n.parm("class").set(2)
    n.parm("snippet").set(
        'int h = pcopen(0, "P", @P, %g, 64);\n'
        'if (pcnumfound(h) < %d) removepoint(0, @ptnum);\n' % (radius, min_nbrs))
    g = n.geometry()
    return {"node": n.path(), "radius": radius, "min_nbrs": min_nbrs,
            "points": g.intrinsicValue("pointcount")}


@endpoint("tag_radial")
def tag_radial(params):
    """Tag points inside a sphere (center + radius) with i@tag = 1. center = [x,y,z]."""
    c = params.get("center") or [0.0, 0.0, 0.0]
    if len(c) != 3:
        raise ValueError("center must be [x, y, z]")
    radius = clamp(float(params.get("radius", 1.0)), 1e-6, 1e9)
    n = child_after(params["input"], "attribwrangle", params.get("name"))
    n.parm("class").set(2)
    n.parm("snippet").set(
        'vector c = set(%g, %g, %g);\n'
        'i@tag = (distance(@P, c) < %g) ? 1 : 0;\n'
        % (float(c[0]), float(c[1]), float(c[2]), radius))
    g = n.geometry()
    return {"node": n.path(), "center": [float(x) for x in c], "radius": radius,
            "points": g.intrinsicValue("pointcount")}


@endpoint("read_geo_stats")
def read_geo_stats(params):
    """Structured readback via intrinsics (safe on multi-GB clouds). Accepts a SOP or an OBJ with a
    display SOP. Per-prim-type histogram is opt-in and capped at 500k prims."""
    node = resolve_node(params["node"])
    target = node
    if getattr(node, "geometry", None) is None:
        disp = getattr(node, "displayNode", None)
        target = disp() if disp else None
        if target is None:
            rnd = getattr(node, "renderNode", None)
            target = rnd() if rnd else None
    if target is None or getattr(target, "geometry", None) is None:
        raise ValueError(f"no geometry (need a SOP or an OBJ with a display SOP): {params['node']}")
    g = target.geometry()
    if g is None:
        raise ValueError("node produced no geometry")
    bb = g.boundingBox()
    res = {"node": target.path(),
           "pointcount": g.intrinsicValue("pointcount"),
           "primitivecount": g.intrinsicValue("primitivecount"),
           "vertexcount": g.intrinsicValue("vertexcount"),
           "bbox": {"min": list(bb.minvec()), "max": list(bb.maxvec()),
                    "size": list(bb.sizevec()), "center": list(bb.center())},
           "point_attribs": _attr_list(g.pointAttribs),
           "prim_attribs": _attr_list(g.primAttribs),
           "vertex_attribs": _attr_list(g.vertexAttribs),
           "detail_attribs": _attr_list(g.globalAttribs)}
    if params.get("include_prim_types"):
        cap = 500000
        if res["primitivecount"] <= cap:
            hist = {}
            for p in g.prims():
                t = p.type().name()
                hist[t] = hist.get(t, 0) + 1
            res["prim_types"] = hist
        else:
            res["prim_types"] = {"skipped": f"primitivecount > cap {cap}"}
    return res


@endpoint("level")
def level(params):
    """Gravity-align a cloud: RANSAC the ground plane in the current frame, PCA-refine the inlier
    normal, and rotate it to +Y via a `level` xform after the input SOP. `input` = cloud SOP path.
    """
    try:
        import numpy as np
    except Exception:
        raise ValueError("numpy is not available in this Houdini python")
    src = resolve_node(params["input"])
    th = clamp(float(params.get("threshold", 0.1)), 1e-4, 1e6)
    if getattr(src, "geometry", None) is None:
        raise ValueError(f"input must be a SOP with geometry: {params['input']}")
    P = np.array(src.geometry().pointFloatAttribValues("P"), dtype=np.float64).reshape(-1, 3)
    if len(P) < 3:
        raise ValueError(f"too few points to fit a plane ({len(P)})")
    rng = np.random.default_rng(0)
    best_in, best = -1, None
    for _ in range(300):
        s = P[rng.choice(len(P), 3, replace=False)]
        nrm = np.cross(s[1] - s[0], s[2] - s[0])
        ln = np.linalg.norm(nrm)
        if ln < 1e-9:
            continue
        nrm = nrm / ln
        d = -nrm @ s[0]
        inl = int((np.abs(P @ nrm + d) < th).sum())
        if inl > best_in:
            best_in, best = inl, (nrm, d)
    if best is None:
        raise ValueError("RANSAC found no plane")
    nrm, d = best
    m = np.abs(P @ nrm + d) < th
    Q = P[m]
    c = Q.mean(0)
    _, evec = np.linalg.eigh((Q - c).T @ (Q - c) / len(Q))
    nrm = evec[:, 0]
    if nrm[1] < 0:
        nrm = -nrm
    gn = hou.Vector3(float(nrm[0]), float(nrm[1]), float(nrm[2])).normalized()
    rot = tuple(gn.matrixToRotateTo(hou.Vector3(0.0, 1.0, 0.0)).extractRotates())
    parent = src.parent()
    lvl = parent.node("level") or parent.createNode("xform", "level")
    lvl.setInput(0, src)
    lvl.parmTuple("r").set(rot)
    lvl.setDisplayFlag(True)
    lvl.setRenderFlag(True)
    parent.layoutChildren()
    return {"node": lvl.path(), "normal": [float(x) for x in nrm], "inliers": int(m.sum()),
            "total": int(len(P)), "inlier_frac": float(m.sum()) / len(P),
            "rot": [float(x) for x in rot]}


@endpoint("isolate")
def isolate(params):
    """Keep only cloud points inside an oriented box object (box's own world transform -> box-local;
    VEX point-delete). `input` = cloud SOP, `box` = a box OBJ. Optional confined `.bgeo`/`.ply` out."""
    src = resolve_node(params["input"])
    box = resolve_node(params["box"])
    src_obj = src.parent()
    bdisp = box.displayNode() if getattr(box, "displayNode", None) else None
    if bdisp is None:
        raise ValueError("box must be an OBJ with a display SOP")
    xf = src_obj.worldTransform() * box.worldTransform().inverted()
    mm = xf.asTuple()
    bb = bdisp.geometry().boundingBox()
    lo, hi = bb.minvec(), bb.maxvec()
    vex = (
        "matrix xf = set(%s);\n"
        "vector lp = @P * xf;\n"
        "vector lo = set(%.9g,%.9g,%.9g);\n"
        "vector hi = set(%.9g,%.9g,%.9g);\n"
        "if (lp.x<lo.x || lp.y<lo.y || lp.z<lo.z || lp.x>hi.x || lp.y>hi.y || lp.z>hi.z)"
        " removepoint(0, @ptnum);\n"
    ) % (",".join("%.9g" % v for v in mm), lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])
    old = src_obj.node("isolate_box")
    if old:
        old.destroy()
    wr = src_obj.createNode("attribwrangle", "isolate_box")
    wr.setFirstInput(src)
    wr.parm("class").set(2)
    wr.parm("snippet").set(vex)
    wr.setDisplayFlag(True)
    wr.setRenderFlag(True)
    src_obj.layoutChildren()
    kept = wr.geometry().intrinsicValue("pointcount")
    saved = None
    if params.get("out"):
        out_path = confined_path(params["out"])
        wr.geometry().saveToFile(out_path)
        saved = out_path
    return {"node": wr.path(), "box": box.path(), "kept": kept, "out": saved}
