"""houdini_executor / governor.py — advisory memory governor v1 (ADVISORY-first, telemetry not gate).

Heavy handlers SURFACE a live resource envelope (projected headroom) in their result so the watching
AI/human governs; ONLY a genuinely catastrophic band hard-refuses, to honor "never OOM/BSOD". On this
rig the tight resource is VRAM (12 GB AMD RX 6700 XT / gfx1031), not the 64 GB system RAM, so the
bands are tuned to the GPU ceiling with margin.

Design rules (audited):
  * `classify_band` is PURE — numbers in, band out, NO import of scene (avoids a circular import).
  * `envelope_status` does a DEFERRED import of `_vram_report` from handlers.scene INSIDE the function
    body, never at module top.
  * FAIL-SOFT everywhere. This is telemetry, NOT a security boundary. Any failure reading the envelope
    => the advisory is omitted/marked unavailable and the handler proceeds. The ONE intentional refuse
    is the catastrophic band in `governor_gate`; a band-unknown (telemetry failure) NEVER refuses.

Thresholds live as MODULE-LEVEL CONSTANTS so they're tunable without touching handler code.
"""

# ── band thresholds (GB) ─────────────────────────────────────────────────────
# Tuned to the 12 GB card WITH margin: system-wide VRAM avail fluctuates ~±0.1 GB call-to-call
# (other apps + the desktop compositor), so these are deliberately NOT razor edges.
#
# VRAM (the tight resource on this rig):
#   critical  < 1.0 GB free — a heavy op (VDB voxelization, remesh, scatter-copy) can easily claim
#             ~1 GB+ of GPU memory in one cook; below this margin a cook risks driving the card to
#             0 and hanging/BSODing the display driver. This is the catastrophic band → heavy ops
#             REFUSE here (the single hard-gate).
#   caution   < 3.0 GB free — enough headroom for a modest op but not a big voxelization/boolean;
#             proceed, but flag prominently so the governor can down-scale resolution/counts.
# RAM (secondary; 64 GB box, rarely the wall — kept as a coarse backstop):
#   critical  < 4.0 GB free — the OS itself is under pressure; refuse heavy work.
#   caution   < 8.0 GB free — getting tight for a large point/voxel build; flag.
VRAM_CRITICAL_GB = 1.0
VRAM_CAUTION_GB = 3.0
RAM_CRITICAL_GB = 4.0
RAM_CAUTION_GB = 8.0

_GUIDANCE = {
    "critical": "free VRAM below safe margin — reduce resolution/counts or clear the scene before heavy ops",
    "caution": "headroom is tight — consider lowering resolution/point counts, or clearing unused geo first",
    "ok": "resource headroom ok",
}
_GUIDANCE_RAM_CRITICAL = "free system RAM below safe margin — close other apps or clear the scene before heavy ops"
_GUIDANCE_RAM_CAUTION = "system RAM headroom is tight — consider lowering counts or freeing memory"
_VRAM_UNKNOWN_NOTE = " (VRAM headroom unknown — classified on system RAM only)"

# ── v2 magnitude-advisory thresholds (per-op REQUESTED magnitude, classified PRE-cook) ───────────
# These are ADVISORY FLAGS, not limits. magnitude_advice() reads only the caller's params dict and
# these module constants and returns {level,note}; a "heavy" level NEVER refuses (the ONE hard-refuse
# stays the catastrophic VRAM/RAM band in governor_gate). Tunable here without touching handler code.
#
# Point-count ops (scatter / scatter_copy `count`; pop_scatter_sim `count`/`constantrate` birth-rate):
#   a flat requested point count. ~500k is sizeable for a game/real-time asset but ordinary for a film
#   hero or a scan-density scatter; ~5M in a single scatter is a deliberate choice worth confirming.
MAG_SCATTER_CAUTION = 500_000
MAG_SCATTER_HEAVY = 5_000_000
# Subdivision iterations (facet_smooth_subdiv op=subdivide): Catmull-Clark ~quadruples the polycount
# per iteration, so 3 iters ≈ 64x and 4 iters ≈ 256x the input — small integers compound hard.
MAG_SUBDIV_ITERS_CAUTION = 3
MAG_SUBDIV_ITERS_HEAVY = 4
# Voxel size (vdb_from_polygons / vdb_from_particles `voxelsize`): SMALLER voxels = more voxels, cost
# ~ (bbox / voxelsize)^3. The true cost needs the model's bbox (unknown pre-cook), so these flag only
# ABSOLUTE smallness and the note says so — scale-relative advice, not a limit.
MAG_VOXEL_CAUTION = 0.05
MAG_VOXEL_HEAVY = 0.01
# Remesh target edge length (remesh `targetsize`): SMALLER edge = denser mesh (~(1/len)^2 over the
# surface). Same scale caveat as voxel size — absolute-smallness flag only.
MAG_REMESH_EDGE_CAUTION = 0.05
MAG_REMESH_EDGE_HEAVY = 0.01

# ── polycount-bloat band (POST-cook geo_cost auto-catch — the "2M-poly coffee cup") ──────────────
# When advise() gathers geo_cost, a prim/point count over these absolute bands adds an advisory
# geo_cost_flag. Prims is the primary signal (a mesh asset); points is a looser backstop (a scan /
# point cloud can legitimately be large, so its band is higher). Advisory only — never refuses.
GEO_BLOAT_PRIMS = 1_000_000
GEO_BLOAT_POINTS = 2_000_000

_MAG_OK = "ok"
_MAG_CAUTION = "caution"
_MAG_HEAVY = "heavy"


def classify_band(vram_avail_gb, ram_avail_gb, vram_known=True):
    """PURE band classifier. Numbers in → (band, guidance) out. No imports, never raises on normal
    numeric input.

    band ∈ {"critical","caution","ok"}:
      critical  vram_known and vram_avail_gb < VRAM_CRITICAL_GB, OR ram_avail_gb < RAM_CRITICAL_GB
                → the catastrophic band; heavy ops refuse.
      caution   vram_known and vram_avail_gb < VRAM_CAUTION_GB, OR ram_avail_gb < RAM_CAUTION_GB
                → proceed but flag prominently.
      ok        otherwise.
    If `not vram_known`, VRAM is ignored and the classification is RAM-only, with a note in guidance.
    """
    try:
        ram = float(ram_avail_gb)
    except (TypeError, ValueError):
        ram = None
    vram = None
    if vram_known:
        try:
            vram = float(vram_avail_gb)
        except (TypeError, ValueError):
            vram = None
            vram_known = False

    # critical
    vram_crit = vram_known and vram is not None and vram < VRAM_CRITICAL_GB
    ram_crit = ram is not None and ram < RAM_CRITICAL_GB
    if vram_crit or ram_crit:
        g = _GUIDANCE_RAM_CRITICAL if (ram_crit and not vram_crit) else _GUIDANCE["critical"]
        if not vram_known:
            g += _VRAM_UNKNOWN_NOTE
        return "critical", g

    # caution
    vram_caut = vram_known and vram is not None and vram < VRAM_CAUTION_GB
    ram_caut = ram is not None and ram < RAM_CAUTION_GB
    if vram_caut or ram_caut:
        g = _GUIDANCE_RAM_CAUTION if (ram_caut and not vram_caut) else _GUIDANCE["caution"]
        if not vram_known:
            g += _VRAM_UNKNOWN_NOTE
        return "caution", g

    g = _GUIDANCE["ok"]
    if not vram_known:
        g += _VRAM_UNKNOWN_NOTE
    return "ok", g


def _read_ram_gb():
    """System RAM (avail_gb, total_gb) via a small GlobalMemoryStatusEx ctypes call — mirrors the one
    in scene.mem(). Returns (None, None) on any failure (fail-soft). No `hou` needed."""
    import ctypes
    from ctypes import wintypes
    gb = 1024.0 ** 3

    class MSX(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    msx = MSX()
    msx.dwLength = ctypes.sizeof(MSX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(msx)):
        return None, None
    return round(msx.ullAvailPhys / gb, 1), round(msx.ullTotalPhys / gb, 1)


def envelope_status():
    """Gather the live resource envelope and classify it. NEVER raises.

    Returns a dict with (best-effort) keys:
        ram_avail_gb, ram_total_gb,
        vram_avail_gb?, vram_total_gb?, vram_used_gb?, gpu_name?,   (present iff VRAM readable; the
                                                                    GOVERN-TARGET card)
        govern_target_basis?, gpus?,   (multi-GPU honesty: which card is governed + ALL discrete cards)
        band, guidance
    On total failure returns {"band":"unknown","guidance":"envelope unavailable"}.
    """
    try:
        status = {}

        # System RAM (small ctypes call; fail-soft).
        try:
            ram_avail, ram_total = _read_ram_gb()
        except Exception:  # noqa: BLE001
            ram_avail, ram_total = None, None
        if ram_avail is not None:
            status["ram_avail_gb"] = ram_avail
        if ram_total is not None:
            status["ram_total_gb"] = ram_total

        # VRAM — DEFERRED import (avoid a circular import at module load; scene imports server, not us,
        # but keep the deferred contract regardless). _vram_report() never raises.
        vram_known = False
        vram_avail = None
        try:
            from houdini_executor.handlers.scene import _vram_report
            vr = _vram_report().get("vram")
            if isinstance(vr, dict):
                if "vram_total_gb" in vr:
                    status["vram_total_gb"] = vr["vram_total_gb"]
                if "gpu_name" in vr:
                    status["gpu_name"] = vr["gpu_name"]
                if "vram_used_gb" in vr:
                    status["vram_used_gb"] = vr["vram_used_gb"]
                # vram_avail_gb is present only when the PDH per-adapter usage query succeeded.
                if "vram_avail_gb" in vr:
                    status["vram_avail_gb"] = vr["vram_avail_gb"]
                    vram_avail = vr["vram_avail_gb"]
                    vram_known = True
                # Multi-GPU honesty pass-through (telemetry only; does NOT affect band math below).
                # `band`/`guidance` still classify on the GOVERN-TARGET card's vram_avail_gb, exactly
                # as before -- these two keys just surface which card that is and the full GPU list.
                if "govern_target_basis" in vr:
                    status["govern_target_basis"] = vr["govern_target_basis"]
                if "gpus" in vr:
                    status["gpus"] = vr["gpus"]
        except Exception:  # noqa: BLE001 — VRAM telemetry failure must never break the envelope
            vram_known = False

        band, guidance = classify_band(vram_avail, status.get("ram_avail_gb"), vram_known=vram_known)
        status["band"] = band
        status["guidance"] = guidance
        return status
    except Exception as exc:  # noqa: BLE001 — absolute backstop; never raise out of envelope_status
        return {"band": "unknown", "guidance": "envelope unavailable", "envelope_err": str(exc)[:80]}


def governor_gate(op_label):
    """Advisory gate for a heavy op. Calls envelope_status(); if band == "critical", RAISE ValueError
    (the ONE intentional hard-refuse, honoring "never OOM/BSOD"). Otherwise return the status dict.

    FAIL-SOFT: a band of "unknown" (telemetry couldn't be read) does NOT refuse — never block real
    work on a telemetry failure. Only an explicit "critical" band refuses.
    """
    status = envelope_status()
    if status.get("band") == "critical":
        vram = status.get("vram_avail_gb")
        ram = status.get("ram_avail_gb")
        vram_s = ("%.2fGB" % vram) if isinstance(vram, (int, float)) else "unknown"
        ram_s = ("%.1fGB" % ram) if isinstance(ram, (int, float)) else "unknown"
        raise ValueError(
            "refused: %s — %s (free VRAM %s / RAM %s)"
            % (op_label, status.get("guidance", "resource envelope critical"), vram_s, ram_s)
        )
    return status


def advise(result, node=None):
    """Enrich a handler's result dict IN PLACE (and return it): attach the live envelope, and — if
    `node` is given and a cooked geometry is cheaply available — a best-effort geo_cost.

    NEVER raises. If `result` isn't a dict it's returned untouched. geo_cost uses the geometry that is
    ALREADY cooked by the handler (every wired handler calls node.geometry()/len(...) before returning,
    so reading counts here forces no extra cook). If no cheap cooked geo is available, geo_cost is
    simply omitted — we never force-cook just to measure.
    """
    try:
        if not isinstance(result, dict):
            return result
        result["envelope"] = envelope_status()
        if node is not None:
            try:
                # geometry() on a SOP returns the last cooked geo; the handler already cooked it, so
                # this is cheap. intrinsicValue avoids materializing point/prim tuples.
                geo = node.geometry()
                if geo is not None:
                    gc = {
                        "points": int(geo.intrinsicValue("pointcount")),
                        "prims": int(geo.intrinsicValue("primitivecount")),
                    }
                    result["geo_cost"] = gc
                    # v2: auto-catch the 2M-poly-coffee-cup — a cooked count over the high band gets an
                    # ADVISORY flag so the watching crew builds to a budget. Never refuses.
                    flag = _geo_cost_flag(gc)
                    if flag:
                        result["geo_cost_flag"] = flag
            except Exception:  # noqa: BLE001 — geo_cost is best-effort; skip on any failure
                pass
        return result
    except Exception:  # noqa: BLE001 — advise must never break a handler
        return result


# ── v2 magnitude advisory ────────────────────────────────────────────────────────────────────────
def _fmt(n):
    """Human-readable count (5.0M / 500k / 42). Never raises."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1e6:
        return "%.1fM" % (n / 1e6)
    if n >= 1e3:
        return "%.0fk" % (n / 1e3)
    return "%d" % int(n)


def _mag(level, note):
    return {"level": level, "note": note}


def _num(params, *keys):
    """First present key in `params` coerced to float; None on missing/garbage. Never raises."""
    if not isinstance(params, dict):
        return None
    for k in keys:
        if k in params:
            try:
                return float(params[k])
            except (TypeError, ValueError):
                return None
    return None


def _geo_cost_flag(geo_cost):
    """Advisory bloat note if a cooked geo's prim/point count exceeds the high band, else None. This is
    the auto-catch for the 2M-poly-coffee-cup case. Advisory only — NEVER raises, never refuses."""
    try:
        if not isinstance(geo_cost, dict):
            return None
        prims = geo_cost.get("prims")
        points = geo_cost.get("points")
        if isinstance(prims, (int, float)) and not isinstance(prims, bool) and prims > GEO_BLOAT_PRIMS:
            return ("high: %s prims — confirm this density is intended for your target "
                    "(game asset ~1k-tens-of-k, film hero more, scan/cloud can be more still)" % _fmt(prims))
        if isinstance(points, (int, float)) and not isinstance(points, bool) and points > GEO_BLOAT_POINTS:
            return ("high: %s points — confirm this density is intended for your target "
                    "(fine for a scan/point cloud, heavy for a mesh asset)" % _fmt(points))
        return None
    except Exception:  # noqa: BLE001
        return None


def magnitude_advice(op_label, params):
    """Advisory classification of an op's REQUESTED magnitude BEFORE it cooks, from the params the caller
    passed. Returns {"level": "ok"|"caution"|"heavy", "note": str}.

    PURE-ish: reads ONLY `params` + the module-constant thresholds; imports nothing; NEVER raises; NEVER
    a hard-refuse (a "heavy" level is a FLAG for the watching crew to down-scale, not a block). Ops whose
    output size is only knowable post-cook (copy_to_points, boolean) say so honestly and defer to
    geo_cost/geo_cost_flag.
    """
    try:
        op = str(op_label)
        p = params if isinstance(params, dict) else {}

        # ── point-count ops ─────────────────────────────────────────────────────────────────────
        if op in ("scatter", "scatter_copy", "pop_scatter_sim"):
            cnt = _num(p, "count", "constantrate")
            if cnt is None or cnt < 0:
                return _mag(_MAG_OK, "no explicit count — the scatter node's own default applies")
            rate = " points/sec (birth rate)" if op == "pop_scatter_sim" else " points"
            if cnt >= MAG_SCATTER_HEAVY:
                return _mag(_MAG_HEAVY, "requested %s%s — heavy; confirm the target needs this density "
                            "(real-time asset far less, film hero mid-range, scan/cloud can justify it)"
                            % (_fmt(cnt), rate))
            if cnt >= MAG_SCATTER_CAUTION:
                return _mag(_MAG_CAUTION, "requested %s%s — sizeable; down-scale unless this is a hero / "
                            "scan-density target" % (_fmt(cnt), rate))
            return _mag(_MAG_OK, "requested %s%s" % (_fmt(cnt), rate))

        # ── subdivision iterations (compounding polycount) ───────────────────────────────────────
        if op == "facet_smooth_subdiv":
            if str(p.get("op", "smooth")) != "subdivide":
                return _mag(_MAG_OK, "op is not 'subdivide' — no polycount multiplication")
            iters = _num(p, "iterations")
            if iters is None:
                return _mag(_MAG_OK, "no explicit iterations — node default")
            it = int(iters)
            if it < 0:
                return _mag(_MAG_OK, "iterations %d" % it)
            mult = 4 ** it if it <= 20 else None  # avoid a silly huge int in the note
            mult_s = ("≈ %sx the input polycount" % _fmt(mult)) if mult is not None else "an enormous multiple of the input"
            if iters >= MAG_SUBDIV_ITERS_HEAVY:
                return _mag(_MAG_HEAVY, "%d subdivision iterations %s — heavy; 1-2 iters is usually enough" % (it, mult_s))
            if iters >= MAG_SUBDIV_ITERS_CAUTION:
                return _mag(_MAG_CAUTION, "%d subdivision iterations %s" % (it, mult_s))
            return _mag(_MAG_OK, "%d subdivision iterations %s" % (it, mult_s))

        # ── voxel-size ops (SMALLER = heavier) ───────────────────────────────────────────────────
        if op in ("vdb_from_polygons", "vdb_from_particles"):
            vs = _num(p, "voxelsize")
            if vs is None or vs <= 0:
                return _mag(_MAG_OK, "no explicit voxelsize — node default")
            base = ("voxelsize %g — cost scales ~(bbox/voxelsize)^3, so this is RELATIVE to your model's "
                    "extent; " % vs)
            if vs <= MAG_VOXEL_HEAVY:
                return _mag(_MAG_HEAVY, base + "very small voxels — likely a dense/large grid, confirm against the model scale")
            if vs <= MAG_VOXEL_CAUTION:
                return _mag(_MAG_CAUTION, base + "small voxels — check the grid isn't finer than the target needs")
            return _mag(_MAG_OK, base + "reasonable for a unit-to-tens-of-units model")

        # ── remesh target edge length (SMALLER = denser) ─────────────────────────────────────────
        if op == "remesh":
            ts = _num(p, "targetsize")
            if ts is None or ts <= 0:
                return _mag(_MAG_OK, "no explicit targetsize — node default")
            base = ("targetsize %g — smaller edge = denser mesh (~(1/len)^2 over the surface), RELATIVE "
                    "to model scale; " % ts)
            if ts <= MAG_REMESH_EDGE_HEAVY:
                return _mag(_MAG_HEAVY, base + "very fine edge — likely a high-poly result, confirm the polycount budget")
            if ts <= MAG_REMESH_EDGE_CAUTION:
                return _mag(_MAG_CAUTION, base + "fine edge — check against your polycount budget")
            return _mag(_MAG_OK, base + "reasonable")

        # ── ops with NO pre-cook magnitude signal ────────────────────────────────────────────────
        if op in ("copy_to_points", "boolean"):
            return _mag(_MAG_OK, "magnitude not knowable pre-cook (copy_to_points = target point count; "
                        "boolean = intersection of both meshes) — see geo_cost/geo_cost_flag after the cook")

        return _mag(_MAG_OK, "no magnitude heuristic for this op")
    except Exception:  # noqa: BLE001 — advisory must NEVER raise out of a handler
        return {"level": _MAG_OK, "note": "magnitude advisory unavailable"}


# ── self-test (run: `hython governor.py`, or plain python for classify_band) ─────────────────────
def _selftest():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # classify_band across every band -------------------------------------------------------------
    b, _ = classify_band(0.5, 32.0)                       # VRAM critical
    check(b == "critical", "VRAM<1.0 should be critical, got %s" % b)
    b, _ = classify_band(8.0, 2.0)                        # RAM critical
    check(b == "critical", "RAM<4.0 should be critical, got %s" % b)
    b, _ = classify_band(2.0, 32.0)                       # VRAM caution
    check(b == "caution", "VRAM<3.0 should be caution, got %s" % b)
    b, _ = classify_band(8.0, 6.0)                        # RAM caution
    check(b == "caution", "RAM<8.0 should be caution, got %s" % b)
    b, _ = classify_band(8.0, 32.0)                       # ok
    check(b == "ok", "8GB VRAM / 32GB RAM should be ok, got %s" % b)
    # not vram_known → RAM-only classification, note appended
    b, g = classify_band(0.1, 32.0, vram_known=False)     # VRAM ignored, RAM fine → ok
    check(b == "ok", "vram_known=False with fine RAM should be ok, got %s" % b)
    check("unknown" in g.lower(), "unknown-VRAM note missing from guidance: %r" % g)
    b, _ = classify_band(0.1, 3.0, vram_known=False)      # RAM-only critical
    check(b == "critical", "vram_known=False with RAM<4.0 should be critical, got %s" % b)
    # edge: exactly at threshold is NOT below it (margin semantics)
    b, _ = classify_band(1.0, 32.0)
    check(b != "critical", "VRAM==1.0 should NOT be critical (strict <), got %s" % b)
    # garbage input must not raise
    b, _ = classify_band(None, None, vram_known=True)
    check(b in ("ok", "caution", "critical", "unknown"), "garbage input band invalid: %s" % b)

    # envelope_status / advise never raise --------------------------------------------------------
    try:
        env = envelope_status()
        check(isinstance(env, dict) and "band" in env, "envelope_status must return a dict with band")
    except Exception as e:  # noqa: BLE001
        fails.append("envelope_status raised: %s" % e)
    try:
        r = advise({"node": "/obj/x"}, node=None)
        check("envelope" in r, "advise must attach envelope")
    except Exception as e:  # noqa: BLE001
        fails.append("advise raised: %s" % e)
    try:
        # governor_gate must NOT refuse on a non-critical/unknown band (fail-soft).
        s = governor_gate("selftest")
        check(isinstance(s, dict), "governor_gate should return status dict when not critical")
    except ValueError as ve:
        # Acceptable only if the live band is genuinely critical right now.
        check("refused" in str(ve), "unexpected ValueError from gate: %s" % ve)
    except Exception as e:  # noqa: BLE001
        fails.append("governor_gate raised non-ValueError: %s" % e)

    # v2 magnitude_advice across bands -------------------------------------------------------------
    def lvl(op, params):
        return magnitude_advice(op, params).get("level")
    check(lvl("scatter", {"count": 1000}) == "ok", "small scatter should be ok")
    check(lvl("scatter", {"count": 600_000}) == "caution", "600k scatter should be caution")
    check(lvl("scatter", {"count": 6_000_000}) == "heavy", "6M scatter should be heavy")
    check(lvl("scatter", {}) == "ok", "scatter with no count should be ok")
    check(lvl("pop_scatter_sim", {"constantrate": 6_000_000}) == "heavy", "6M birth-rate should be heavy")
    check(lvl("facet_smooth_subdiv", {"op": "subdivide", "iterations": 2}) == "ok", "2 subdiv iters ok")
    check(lvl("facet_smooth_subdiv", {"op": "subdivide", "iterations": 3}) == "caution", "3 subdiv iters caution")
    check(lvl("facet_smooth_subdiv", {"op": "subdivide", "iterations": 4}) == "heavy", "4 subdiv iters heavy")
    check(lvl("facet_smooth_subdiv", {"op": "smooth", "iterations": 4}) == "ok", "non-subdivide op ok")
    check(lvl("vdb_from_polygons", {"voxelsize": 0.5}) == "ok", "0.5 voxel ok")
    check(lvl("vdb_from_polygons", {"voxelsize": 0.03}) == "caution", "0.03 voxel caution")
    check(lvl("vdb_from_polygons", {"voxelsize": 0.005}) == "heavy", "tiny voxel heavy")
    check(lvl("remesh", {"targetsize": 1.0}) == "ok", "1.0 edge ok")
    check(lvl("remesh", {"targetsize": 0.03}) == "caution", "0.03 edge caution")
    check(lvl("remesh", {"targetsize": 0.005}) == "heavy", "tiny edge heavy")
    check(lvl("copy_to_points", {}) == "ok", "copy_to_points defers to post-cook, ok")
    check(lvl("boolean", {}) == "ok", "boolean defers to post-cook, ok")
    # magnitude_advice must NEVER raise on garbage/missing params
    for bad in (None, {}, {"count": "abc"}, {"count": None}, {"voxelsize": "x"}, {"iterations": []},
                {"targetsize": float("nan")}):
        try:
            r = magnitude_advice("scatter", bad)
            check(isinstance(r, dict) and r.get("level") in ("ok", "caution", "heavy"),
                  "magnitude_advice bad-input result invalid: %r" % r)
        except Exception as e:  # noqa: BLE001
            fails.append("magnitude_advice raised on %r: %s" % (bad, e))
    check(magnitude_advice(None, None).get("level") in ("ok", "caution", "heavy"),
          "magnitude_advice(None,None) should still return a valid level")

    # v2 geo_cost_flag bloat band ------------------------------------------------------------------
    check(_geo_cost_flag({"prims": 10, "points": 20}) is None, "small geo should not flag")
    check(_geo_cost_flag({"prims": 2_000_000, "points": 1_500_000}) is not None, "2M prims should flag")
    check("prims" in (_geo_cost_flag({"prims": 2_000_000, "points": 10}) or ""), "prim bloat note wrong")
    check(_geo_cost_flag({"prims": 10, "points": 3_000_000}) is not None, "3M points should flag")
    check(_geo_cost_flag("garbage") is None, "garbage geo_cost should not raise/flag")
    check(_geo_cost_flag({"prims": True}) is None, "bool prims must not be treated as a count")

    if fails:
        print("SELFTEST FAIL:")
        for f in fails:
            print("  -", f)
        return False
    print("SELFTEST OK")
    print("live envelope:", envelope_status())
    return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if _selftest() else 1)
