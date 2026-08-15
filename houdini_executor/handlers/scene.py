"""Scene / utility handlers."""

import hou
from houdini_executor.server import endpoint, confined_path, resolve_node


@endpoint("set_frame")
def set_frame(params):
    hou.setFrame(int(params["frame"]))
    return {"frame": hou.frame()}


@endpoint("set_display")
def set_display(params):
    """Show/hide a node in the viewport (and optionally in render).

    OBJECT nodes (e.g. /obj/terrain, a geo OBJ) are shown/hidden via their `display` PARM (the
    "Display" checkbox) -- the SOP display FLAG does nothing to an object's viewport visibility.
    SOP nodes use the display flag (setting a SOP's display flag auto-clears sibling display flags
    in that network -- Houdini behavior). `display` defaults to True; `render` is only touched when
    explicitly provided. The `via` field reports how visibility was applied ("object-parm" vs
    "sop-flag") so the caller can tell."""
    node = resolve_node(params["node"])
    display = bool(params.get("display", True))
    want_render = "render" in params
    render = bool(params["render"]) if want_render else None

    def _is_object(n):
        if isinstance(getattr(hou, "ObjNode", ()), type) and isinstance(n, hou.ObjNode):
            return True
        try:
            return n.type().category().name() == "Object"
        except Exception:
            return False

    def _try_set_parm(n, name, val):
        """Set an integer parm iff it exists; return True if applied, False if the parm is absent.
        Any failure to actually set an existing parm is surfaced as a clear ValueError."""
        try:
            p = n.parm(name)
        except Exception:
            p = None
        if p is None:
            return False
        try:
            p.set(1 if val else 0)
            return True
        except Exception as exc:
            raise ValueError("node %s parm '%s' could not be set: %s" % (n.path(), name, exc))

    if _is_object(node):
        # OBJECT: viewport visibility is the `display` PARM, not the display flag.
        if not _try_set_parm(node, "display", display):
            raise ValueError("object %s has no 'display' parm to control visibility" % node.path())
        out = {"node": node.path(), "display": display, "render": "unchanged", "via": "object-parm"}
        if want_render:
            # Objects don't carry a simple render-visibility toggle like SOPs do; set one only if a
            # known render parm actually exists. Do NOT invent a parm -- report "unchanged" if none.
            applied = False
            for cand in ("viewportvis", "render"):
                if _try_set_parm(node, cand, render):
                    applied = True
                    out["render"] = render
                    out["render_parm"] = cand
                    break
            if not applied:
                out["render"] = "unchanged"
                out["render_note"] = "no render-visibility parm on this object; left unchanged"
        return out

    # SOP (or anything else that carries a display flag): keep flag-based behavior.
    if not hasattr(node, "setDisplayFlag"):
        raise ValueError("node %s cannot carry a display flag" % node.path())
    try:
        node.setDisplayFlag(display)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("node %s cannot carry a display flag: %s" % (node.path(), exc))
    out = {"node": node.path(), "display": display, "render": "unchanged", "via": "sop-flag"}
    if want_render:
        if not hasattr(node, "setRenderFlag"):
            raise ValueError("node %s cannot carry a render flag" % node.path())
        try:
            node.setRenderFlag(render)
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("node %s cannot carry a render flag: %s" % (node.path(), exc))
        out["render"] = render
    return out


@endpoint("delete_node")
def delete_node(params):
    """Delete a node (SOP or OBJ) from the scene. If `reconnect` is true and the node has an
    input, its first input is bridged to each of its output connections before destroying so the
    downstream chain stays connected (Houdini does NOT auto-bridge on destroy()); with no input,
    downstream inputs are simply disconnected. Returns the deleted path, whether a reconnect was
    actually performed, and the parent path."""
    node = resolve_node(params["node"])
    path = node.path()
    parent = node.parent()
    parent_path = parent.path() if parent is not None else None
    reconnect = bool(params.get("reconnect", False))
    reconnected = False
    if reconnect and len(node.inputs()) >= 1:
        src = node.inputs()[0]  # may be None
        for conn in node.outputConnections():
            try:
                conn.outputNode().setInput(conn.inputIndex(), src)
                reconnected = True
            except Exception:
                pass
    try:
        node.destroy()
    except Exception as exc:
        raise ValueError("cannot delete node %s (locked or inside a locked asset?): %s"
                         % (path, exc))
    return {"deleted": path, "reconnected": reconnected, "parent": parent_path}


@endpoint("save_scene")
def save_scene(params):
    """Save the .hip to a confined path under the working directory."""
    path = confined_path(params["path"])
    if not path.lower().endswith((".hip", ".hipnc", ".hiplc")):
        raise ValueError("save path must end in .hip / .hipnc / .hiplc")
    hou.hipFile.save(path)
    return {"saved": path}


@endpoint("list_node_types")
def list_node_types(params):
    """Enumerate the node-type palette. Default: per-category counts + names for one category
    (`category`, default Sop). `contains` filters names; `full` returns every name in every
    category."""
    catmap = {}
    for cname, getter in (("Sop", "sopNodeTypeCategory"), ("Object", "objNodeTypeCategory"),
                          ("Driver", "ropNodeTypeCategory"), ("Dop", "dopNodeTypeCategory"),
                          ("Cop2", "cop2NodeTypeCategory"), ("Vop", "vopNodeTypeCategory"),
                          ("Lop", "lopNodeTypeCategory"), ("Chop", "chopNodeTypeCategory"),
                          ("Top", "topNodeTypeCategory"), ("Shop", "shopNodeTypeCategory")):
        fn = getattr(hou, getter, None)
        if fn is not None:
            try:
                catmap[cname] = fn()
            except Exception:
                pass
    counts = {}
    allnames = {}
    for cname, cat in catmap.items():
        try:
            names = sorted(cat.nodeTypes().keys())
        except Exception:
            names = []
        counts[cname] = len(names)
        allnames[cname] = names
    con = str(params.get("contains", "") or "").lower()
    out = {"counts": counts, "categories": sorted(catmap.keys())}
    if params.get("full") or con:
        filt = {}
        for cname, names in allnames.items():
            sel = [n for n in names if con in n.lower()] if con else names
            if sel:
                filt[cname] = sel
        out["node_types"] = filt
    else:
        want = params.get("category") if params.get("category") in allnames else "Sop"
        out["category"] = want
        out["node_types"] = {want: allnames.get(want, [])}
    return out


@endpoint("reload_node")
def reload_node(params):
    """Re-read a File SOP after its file was rewritten on disk. Presses `reload` if present, else
    forces a recook."""
    node = resolve_node(params["node"])
    p = node.parm("reload")
    if p is not None:
        p.pressButton()
    else:
        node.cook(force=True)
    out = {"node": node.path(), "reloaded": True}
    try:
        g = node.geometry()
        out["pointcount"] = g.intrinsicValue("pointcount")
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# VRAM telemetry for the memory governor (additive to mem()).
# On this rig the tight resource is the 12GB GPU, not the 64GB system RAM, so the
# governor needs the GPU ceiling too. Two in-process ctypes paths (NO subprocess):
#   DXGI  -> gpu_name, total dedicated VRAM, per-process OS budget, adapter LUID
#   PDH   -> system-wide dedicated usage of THAT adapter (the true freeze-ceiling signal)
# Everything below is FAIL-SOFT: any failure yields "vram":"unavailable" (or omitted
# per-field), and never affects the RAM report. mem() must never throw.
# ---------------------------------------------------------------------------
def _vram_vcall(this, index, restype, argtypes, *args):
    """Call vtable[index] on a COM interface pointer `this` (HRESULT-style methods)."""
    import ctypes
    from ctypes import POINTER, c_void_p
    vtbl = ctypes.cast(this, POINTER(c_void_p))[0]
    fnptr = ctypes.cast(vtbl, POINTER(c_void_p))[index]
    fn = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(fnptr)
    return fn(this, *args)


def _vram_all_adapters():
    """DXGI (ctypes-COM): enumerate EVERY non-software adapter with dedicated VRAM > 0.
    Returns a LIST of {gpu_name, _total(bytes), _budget(bytes|None), _luid_low, _luid_high}, in DXGI
    enumeration order. Raises on failure (caught by the caller). No `hou` needed; pure Windows API.
    Multi-GPU aware: the rig has two discrete cards (12GB 6700 XT + 8GB Vega 56); both are returned so
    the governor can report all of them and pick a govern target, instead of silently assuming one."""
    import ctypes
    from ctypes import (POINTER, byref, c_void_p, c_uint, c_ulonglong, Structure)
    ole32 = ctypes.windll.ole32
    dxgi = ctypes.windll.dxgi

    class GUID(Structure):
        _fields_ = [("Data1", c_uint), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    def _guid(s):
        g = GUID(); ole32.CLSIDFromString(ctypes.c_wchar_p(s), byref(g)); return g

    IID_IDXGIFactory1 = _guid("{770aae78-f26f-4dba-a829-253c83d1b387}")
    IID_IDXGIAdapter3 = _guid("{645967A4-1392-4310-A798-8053CE3E93FD}")

    class DESC1(Structure):
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", c_uint),
                    ("DeviceId", c_uint), ("SubSysId", c_uint), ("Revision", c_uint),
                    ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                    ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", ctypes.c_longlong),
                    ("Flags", c_uint)]

    class VMI(Structure):
        _fields_ = [("Budget", c_ulonglong), ("CurrentUsage", c_ulonglong),
                    ("AvailableForReservation", c_ulonglong), ("CurrentReservation", c_ulonglong)]

    # vtable indices: IUnknown 0..2, IDXGIObject 3..6, then per-interface methods.
    IDX_RELEASE, IDX_QI, IDX_ENUM1, IDX_GETDESC1, IDX_QVMI = 2, 0, 12, 10, 14

    factory = c_void_p()
    hr = dxgi.CreateDXGIFactory1(byref(IID_IDXGIFactory1), byref(factory))
    if hr != 0 or not factory.value:
        raise OSError("CreateDXGIFactory1 hr=0x%08x" % (hr & 0xffffffff))

    adapters = []
    try:
        i = 0
        while True:
            adapter = c_void_p()
            # restype c_long (NOT ctypes.HRESULT): EnumAdapters1 returns DXGI_ERROR_NOT_FOUND to
            # end enumeration -- must be inspected, not auto-raised by ctypes.
            hr = _vram_vcall(factory, IDX_ENUM1, ctypes.c_long,
                             [c_uint, POINTER(c_void_p)], i, byref(adapter))
            if hr != 0 or not adapter.value:
                break
            try:
                d = DESC1()
                _vram_vcall(adapter, IDX_GETDESC1, ctypes.c_long, [POINTER(DESC1)], byref(d))
                is_sw = bool(d.Flags & 0x2)  # DXGI_ADAPTER_FLAG_SOFTWARE
                if not is_sw and d.DedicatedVideoMemory > 0:
                    budget = None
                    a3 = c_void_p()
                    hr3 = _vram_vcall(adapter, IDX_QI, ctypes.c_long,
                                      [POINTER(GUID), POINTER(c_void_p)],
                                      byref(IID_IDXGIAdapter3), byref(a3))
                    if hr3 == 0 and a3.value:
                        try:
                            vmi = VMI()
                            if _vram_vcall(a3, IDX_QVMI, ctypes.c_long,
                                           [c_uint, c_uint, POINTER(VMI)], 0, 0, byref(vmi)) == 0:
                                budget = vmi.Budget
                        finally:
                            _vram_vcall(a3, IDX_RELEASE, ctypes.c_ulong, [])
                    luid = d.AdapterLuid & 0xFFFFFFFFFFFFFFFF
                    adapters.append({"gpu_name": d.Description, "_total": d.DedicatedVideoMemory,
                                     "_budget": budget, "_luid_low": luid & 0xFFFFFFFF,
                                     "_luid_high": (luid >> 32) & 0xFFFFFFFF})
            finally:
                _vram_vcall(adapter, IDX_RELEASE, ctypes.c_ulong, [])
            i += 1
    finally:
        _vram_vcall(factory, IDX_RELEASE, ctypes.c_ulong, [])

    if not adapters:
        raise OSError("no hardware DXGI adapter found")
    return adapters


def _vram_dxgi_query():
    """Back-compat single-adapter accessor: the discrete adapter with the most dedicated VRAM (the
    12GB card on this rig). Returns {gpu_name, _total, _budget, _luid_low, _luid_high}. Raises on
    failure (caught by the caller). Kept so the legacy single-card fail-soft path in _vram_report()
    still has a one-adapter source."""
    return max(_vram_all_adapters(), key=lambda a: a["_total"])


def _houdini_gl_renderer():
    """Best-effort in-process GL_RENDERER string for Houdini's viewport GPU. Returns a string or None;
    NEVER raises. HONEST STATUS on this rig: no in-process path yields it reliably from a handler's
    Python context -- hython is headless (no GL context), the `glinfo`/`gpumem`/`glcache` hscript
    commands print nothing without a live GL context, `hou.ui` is absent headless, and even in the GUI
    the viewport's GL context is current only on the render thread during a draw, so
    wglGetCurrentContext is typically NULL when a handler runs. We STILL try the wgl path so that,
    wherever a GL context IS current, the true renderer is captured (=> basis 'probed-gl-renderer');
    otherwise the caller falls back to the max-VRAM assumption (=> basis 'assumed-max-vram')."""
    try:
        import ctypes
        opengl32 = ctypes.windll.opengl32
        opengl32.wglGetCurrentContext.restype = ctypes.c_void_p
        if not opengl32.wglGetCurrentContext():
            return None
        opengl32.glGetString.restype = ctypes.c_char_p
        GL_RENDERER = 0x1F01
        r = opengl32.glGetString(GL_RENDERER)
        if not r:
            return None
        s = r.decode("ascii", "replace").strip()
        return s or None
    except Exception:
        return None


def _vram_pdh_used_by_luid(luid_low, luid_high):
    """PDH: system-wide dedicated GPU usage (bytes) for the adapter matching this LUID, summed across
    its instances. Returns int bytes, or None if unavailable. In-process; no subprocess."""
    import ctypes
    from ctypes import wintypes, byref, c_void_p, Structure

    class CV(Structure):
        _fields_ = [("CStatus", wintypes.DWORD), ("largeValue", ctypes.c_longlong)]

    PDH_FMT_LARGE = 0x00000400
    pdh = ctypes.windll.pdh
    query = c_void_p()
    if pdh.PdhOpenQueryW(None, 0, byref(query)) != 0:
        return None
    try:
        path = "\\GPU Adapter Memory(*)\\Dedicated Usage"
        size = wintypes.DWORD(0)
        pdh.PdhExpandWildCardPathW(None, ctypes.c_wchar_p(path), None, byref(size), 0)
        buf = ctypes.create_unicode_buffer(size.value)
        if pdh.PdhExpandWildCardPathW(None, ctypes.c_wchar_p(path), buf, byref(size), 0) != 0:
            return None
        instances = [s for s in buf[:size.value].split("\x00") if s]
        want = ("0x%08x_0x%08x" % (luid_high, luid_low)).lower()  # e.g. luid_0x00000000_0x00036065
        handles = []
        for p in instances:
            if want in p.lower():
                h = c_void_p()
                if pdh.PdhAddEnglishCounterW(query, ctypes.c_wchar_p(p), 0, byref(h)) == 0:
                    handles.append(h)
        if not handles:
            return None
        pdh.PdhCollectQueryData(query)
        total, got = 0, False
        for h in handles:
            v = CV()
            if pdh.PdhGetFormattedCounterValue(h, PDH_FMT_LARGE, None, byref(v)) == 0:
                total += v.largeValue
                got = True
        return total if got else None
    finally:
        pdh.PdhCloseQuery(query)


def _vram_report():
    """Build the additive VRAM fields for mem(). NEVER raises -- returns {"vram":"unavailable"} on any
    failure. `vram_used_gb`/`vram_avail_gb` are SYSTEM-WIDE (whole-card occupancy, the freeze ceiling),
    not per-process; `vram_budget_gb` is the OS-provided budget for this process.

    MULTI-GPU AWARE + HONEST ABOUT WHICH CARD IT GOVERNS. Shape (additive -- every existing top-level
    `vram_*` key describes the GOVERN-TARGET card, so the governor's band math is UNCHANGED):
        {gpu_name, vram_total_gb, vram_budget_gb?, vram_used_gb?, vram_avail_gb?, vram_used_scope?,
         govern_target_basis: "probed-gl-renderer"|"assumed-max-vram",
         gl_renderer?,                                   # only when a GL renderer was actually probed
         gpus: [ {gpu_name, vram_total_gb, vram_used_gb?, vram_avail_gb?}, ... ]}  # ALL discrete cards
    The govern target is PROBED (matched to Houdini's GL_RENDERER) when determinable, else it falls
    back to the max-VRAM discrete card (the documented assumption) -- basis stamped either way.
    Single-GPU rig => `gpus` has one entry == the govern target. Fail-soft: if the multi-adapter
    enumeration fails, drop to the legacy single-card path; if that fails too, {"vram":"unavailable"}."""
    gb = 1024.0 ** 3

    def _card(a, full):
        """Render one enumerated adapter into report fields. full=True adds budget + used_scope (the
        govern-target card); full=False is the compact per-GPU list entry."""
        c = {"gpu_name": a["gpu_name"], "vram_total_gb": round(a["_total"] / gb, 2)}
        if full and a.get("_budget") is not None:
            c["vram_budget_gb"] = round(a["_budget"] / gb, 2)
        if a.get("_used") is not None:
            c["vram_used_gb"] = round(a["_used"] / gb, 2)
            c["vram_avail_gb"] = round((a["_total"] - a["_used"]) / gb, 2)
            if full:
                c["vram_used_scope"] = "system-wide"
        return c

    # ── primary path: enumerate ALL discrete adapters ────────────────────────────────────────────
    try:
        adapters = _vram_all_adapters()
    except Exception:
        adapters = None

    if adapters:
        try:
            # per-card system-wide dedicated usage (PDH, LUID-matched); None per card if unavailable.
            for a in adapters:
                try:
                    a["_used"] = _vram_pdh_used_by_luid(a["_luid_low"], a["_luid_high"])
                except Exception:
                    a["_used"] = None

            # Determine the GOVERN-TARGET card: PROBE Houdini's GL renderer first, else assume max-VRAM.
            target, basis, renderer = None, "assumed-max-vram", _houdini_gl_renderer()
            if renderer:
                rl = renderer.lower()
                for a in adapters:
                    nl = (a["gpu_name"] or "").lower()
                    if nl and (nl in rl or rl in nl):
                        target, basis = a, "probed-gl-renderer"
                        break
            if target is None:
                target = max(adapters, key=lambda a: a["_total"])
                basis = "assumed-max-vram"

            vram = _card(target, full=True)
            vram["govern_target_basis"] = basis
            if renderer:  # honest: surface what the probe actually saw, when it saw anything
                vram["gl_renderer"] = renderer
            vram["gpus"] = [_card(a, full=False) for a in adapters]
            return {"vram": vram}
        except Exception:
            pass  # fall through to the legacy single-card path below

    # ── fail-soft legacy single-card path (prior behavior, now stamped + wrapped in a 1-item list) ─
    try:
        dx = _vram_dxgi_query()
        vram = {"gpu_name": dx["gpu_name"],
                "vram_total_gb": round(dx["_total"] / gb, 2)}
        if dx["_budget"] is not None:
            vram["vram_budget_gb"] = round(dx["_budget"] / gb, 2)
        try:
            used = _vram_pdh_used_by_luid(dx["_luid_low"], dx["_luid_high"])
        except Exception:
            used = None
        if used is not None:
            vram["vram_used_gb"] = round(used / gb, 2)
            vram["vram_avail_gb"] = round((dx["_total"] - used) / gb, 2)
            vram["vram_used_scope"] = "system-wide"
        vram["govern_target_basis"] = "assumed-max-vram"
        gpu = {"gpu_name": vram["gpu_name"], "vram_total_gb": vram["vram_total_gb"]}
        if "vram_used_gb" in vram:
            gpu["vram_used_gb"] = vram["vram_used_gb"]
            gpu["vram_avail_gb"] = vram["vram_avail_gb"]
        vram["gpus"] = [gpu]
        return {"vram": vram}
    except Exception as e:
        return {"vram": "unavailable", "vram_err": str(e)[:80]}


@endpoint("mem")
def mem(params):
    """Report process working set + system RAM + Houdini memory/glcache + GPU VRAM (self-monitoring)."""
    import ctypes
    from ctypes import wintypes
    gb = 1024.0 ** 3
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    try:
        gpmi = ctypes.windll.psapi.GetProcessMemoryInfo
    except AttributeError:
        gpmi = k32.K32GetProcessMemoryInfo
    gpmi.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    gpmi.restype = wintypes.BOOL
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    gpmi(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)

    class MSX(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    msx = MSX()
    msx.dwLength = ctypes.sizeof(MSX)
    k32.GlobalMemoryStatusEx(ctypes.byref(msx))
    obj = hou.node("/obj")
    geos = [c for c in obj.children() if c.type().name() == "geo"] if obj else []
    try:
        hmem = hou.hscript("memory")[0].strip()
    except Exception as e:
        hmem = "err:" + str(e)[:60]
    result = {"working_set_gb": round(pmc.WorkingSetSize / gb, 3),
              "peak_working_set_gb": round(pmc.PeakWorkingSetSize / gb, 3),
              "sys_total_gb": round(msx.ullTotalPhys / gb, 1),
              "sys_avail_gb": round(msx.ullAvailPhys / gb, 1), "sys_load_pct": msx.dwMemoryLoad,
              "geo_count": len(geos),
              "displayed": [g.name() for g in geos if g.isDisplayFlagSet()][:30],
              "hscript_memory": hmem}
    # Additive GPU VRAM telemetry (fail-soft; never affects the RAM report above).
    result.update(_vram_report())
    return result


@endpoint("find_error_nodes")
def find_error_nodes(params):
    """Read-only diagnostic: scan a subtree for nodes in an error (and optionally warning) state and
    report them so an AI agent can self-correct. `root` (default /obj) scopes the scan; the root node
    plus every descendant (allSubChildren) is inspected. `include_warnings` also reports warning-only
    nodes. For each bad node a guarded cook (force=False) is attempted -- a cook FAILURE is captured
    and reported (not raised), which is exactly how a broken node (e.g. a File SOP pointing at a
    missing path) surfaces. Pure introspection: no node is created, deleted, or mutated. Returns
    {root, scanned, count, nodes:[{path,type,severity,cook_failed,errors,warnings}]}."""
    root = resolve_node(params.get("root", "/obj"))
    include_warnings = bool(params.get("include_warnings", False))

    # root itself + every descendant. allSubChildren is recursive; guard in case a node kind lacks it.
    nodes = [root]
    try:
        nodes.extend(root.allSubChildren())
    except Exception:
        pass

    bad = []
    scanned = 0
    for node in nodes:
        scanned += 1
        cook_failed = False
        # A dirty/uncooked node only cooks now (force=False); an already-cooked scene stays cheap.
        # A cook that FAILS raises hou.OperationFailed -- that is the error signal we want, captured
        # not raised, so a downstream bad node is reported rather than aborting the whole scan.
        try:
            node.cook(force=False)
        except hou.OperationFailed:
            cook_failed = True
        except Exception:
            cook_failed = True
        errs = []
        warns = []
        try:
            errs = [str(e) for e in node.errors()]
        except Exception:
            errs = []
        if include_warnings:
            try:
                warns = [str(w) for w in node.warnings()]
            except Exception:
                warns = []
        has_err = bool(errs) or cook_failed
        if not (has_err or (include_warnings and warns)):
            continue
        if cook_failed and not errs:
            # Cook raised but errors() gave no text -- still report a clear signal.
            errs = ["cook failed (no error text available)"]
        try:
            ntype = node.type().name()
        except Exception:
            ntype = "?"
        bad.append({"path": node.path(), "type": ntype,
                    "severity": "error" if (errs or cook_failed) else "warning",
                    "cook_failed": cook_failed, "errors": errs, "warnings": warns})
    return {"root": root.path(), "scanned": scanned, "count": len(bad), "nodes": bad}


@endpoint("select_node")
def select_node(params):
    """Select a node (clearing any prior selection) and make it the current node. If `dive` is true
    and a Network Editor pane is open, set that pane's pwd to this node so its child graph is shown
    (a no-op when the node has no browsable interior). Returns the selected path and whether a dive
    was actually performed."""
    node = resolve_node(params["node"])
    node.setSelected(True, clear_all_selected=True)
    # Make it the current node too (drives parm/relationship context). Guard: some node kinds/builds
    # may not honor setCurrent -- selection above is the load-bearing part.
    try:
        node.setCurrent(True, clear_all_selected=False)
    except (hou.OperationFailed, AttributeError, TypeError):
        pass

    dived = False
    if bool(params.get("dive", False)):
        try:
            net = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        except (hou.OperationFailed, AttributeError, TypeError):
            net = None
        if net is not None:
            try:
                net.setCurrentNode(node)
                net.setPwd(node)  # dive: show this node's internal graph (fails if it has none)
                dived = True
            except (hou.OperationFailed, AttributeError, TypeError):
                dived = False
    return {"selected": node.path(), "dived": dived}


def _node_bbox(node):
    """Best-effort hou.BoundingBox for a node so the viewport can frame it precisely. Order: direct
    SOP geometry bounds; else an OBJ's display-SOP geometry bounds transformed into world; else a
    degenerate box at the OBJ's world translation. Returns None if nothing resolves (all guarded --
    never raises)."""
    # Direct SOP geometry (node itself is a SOP).
    try:
        geo = node.geometry()
        if geo is not None:
            return geo.boundingBox()
    except (hou.OperationFailed, AttributeError, TypeError):
        pass
    # OBJ: bounds of its display SOP, moved into world space by the OBJ transform.
    try:
        disp = node.displayNode()
    except (hou.OperationFailed, AttributeError, TypeError):
        disp = None
    if disp is not None:
        try:
            geo = disp.geometry()
            if geo is not None:
                bbox = geo.boundingBox()
                try:
                    bbox.transform(node.worldTransform())
                except (hou.OperationFailed, AttributeError, TypeError):
                    pass
                return bbox
        except (hou.OperationFailed, AttributeError, TypeError):
            pass
    # Last resort: a point box at the OBJ's world translation.
    try:
        t = node.parmTransform().extractTranslates()
        bbox = hou.BoundingBox()
        bbox.enlargeToContain(hou.Vector3(t[0], t[1], t[2]))
        return bbox
    except (hou.OperationFailed, AttributeError, TypeError, IndexError):
        pass
    return None


@endpoint("frame_selected")
def frame_selected(params):
    """Frame the Scene Viewer on a node (the Shift+H "home selected" equivalent) -- precise framing
    for mixed-scale scenes where frame-all is useless. With `node`, select it first then frame it;
    without, frame the current selection. Tries the viewport's frameSelected(), and for an explicit
    node also computes the node's bounds and frameBoundingBox() as a robust fallback."""
    sv = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if sv is None:
        raise ValueError("no scene viewer open")
    vp = sv.curViewport()

    node = None
    target = "selection"
    if params.get("node"):
        node = resolve_node(params["node"])
        node.setSelected(True, clear_all_selected=True)
        target = node.path()

    # Primary: viewport frame-selected (may be absent on some builds -> guarded).
    try:
        vp.frameSelected()
    except (hou.OperationFailed, AttributeError, TypeError):
        pass

    # Robust fallback for an explicit node: frame its computed bounding box.
    if node is not None:
        bbox = _node_bbox(node)
        if bbox is not None:
            try:
                vp.frameBoundingBox(bbox)
            except (hou.OperationFailed, AttributeError, TypeError):
                pass
    return {"framed": target}


@endpoint("layout_nodes")
def layout_nodes(params):
    """Auto-arrange a network's children so freshly added nodes don't stack (the Shift+L equivalent).
    `parent` is the network whose children to lay out (e.g. /obj or /obj/terrain). Returns the parent
    path and its child count."""
    parent = resolve_node(params["parent"])
    if not hasattr(parent, "layoutChildren"):
        raise ValueError("node %s cannot lay out children" % parent.path())
    try:
        parent.layoutChildren()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot lay out children of %s: %s" % (parent.path(), exc))
    try:
        count = len(parent.children())
    except Exception:
        count = 0
    return {"laid_out": parent.path(), "children": count}


@endpoint("viewport_optimize")
def viewport_optimize(params):
    """Apply heavy-scene viewport levers (display-quality only, no data change). mode:
    balanced (default) | aggressive."""
    profile = str(params.get("mode", "balanced"))
    sv = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if sv is None:
        raise ValueError("no scene viewer open")
    s = sv.curViewport().settings()
    log = {}

    def ap(name, *args):
        setter = "set" + name[0].upper() + name[1:]
        for m in (name, setter):
            fn = getattr(s, m, None)
            if fn is None:
                continue
            try:
                fn(*args)
                log[name] = "ok"
                return
            except TypeError:
                continue
            except Exception as e:
                log[name] = "err:" + str(e)[:60]
                return
        log.setdefault(name, "no-callable")

    vq = hou.viewportVolumeQuality.VeryLow if profile == "aggressive" else hou.viewportVolumeQuality.Low
    ap("volumeQuality", vq)
    ap("volumeBSplines", hou.viewportVolumeBSplines.Off)
    ap("scenePolygonLimit", 10)
    ap("distanceBasedPackedCulling", True)
    ap("levelOfDetail", 0.5)
    ap("sceneAntialias", 1)
    try:
        sv.curViewport().draw()
    except Exception:
        pass
    return {"mode": profile, "applied": log}
