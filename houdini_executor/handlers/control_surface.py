"""Control-surface handlers -- viewport interaction & operator feedback.

DATA-ONLY GUI drive: every param is a typed scalar / enum token / bool / node path that maps to a
built-in HOM method taking NO Python callable. Nothing here compiles, loads, or evals a caller
string; there is no callback surface.

These drive the interactive Scene Viewer, which does NOT exist in a headless hython session
(`hou.ui` is absent -> there is no SceneViewer/GeometryViewport). Every actuator resolves the viewer
through `_scene_viewer()` / `_cur_viewport()`, which raise a CLEAR ValueError ("no interactive
viewport available ...") instead of crashing with an AttributeError when run headless. The actuation
path is fully reachable in the live GUI executor; signatures were pinned against the installed build
(Houdini 21.0.671) via the offline help server + hython introspection.

HOM APIs used (all confirmed present on 21.0.671):
  hou.SceneViewer.setSnappingMode / setSnapTo{CurrentGeometry,Templates,OtherObjects,Guides,Drawables}
  hou.SceneViewer.flashMessage / setPromptMessage / snappingMode / constructionPlane / curViewport
  hou.GeometryViewport.home{All,Selected,Grid,NonTemplated} / saveViewToCamera / lockCameraToView
  hou.ConstructionPlane.setIsVisible / setCellSize / setNumberOfCells / setNumberOfCellsPerRulerLine
  enums: hou.snappingMode {Off,Grid,Prim,Point,Multi} · hou.promptMessageType {Error,Message,Prompt,Warning}
"""

import hou
from houdini_executor.server import endpoint, resolve_node, clamp


# ── viewer resolution (fail-clear when there is no GUI) ──────────────────────────────────────────
def _scene_viewer():
    """The current Scene Viewer pane tab. Raises a CLEAR error headless (no `hou.ui`) or when no
    Scene Viewer pane is open -- never an AttributeError."""
    ui = getattr(hou, "ui", None)
    if ui is None:
        raise ValueError("no interactive viewport available (headless session; GUI-only tool)")
    try:
        sv = ui.paneTabOfType(hou.paneTabType.SceneViewer)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the Scene Viewer: %s" % exc)
    if sv is None:
        raise ValueError("no Scene Viewer pane open")
    return sv


def _cur_viewport(sv=None):
    """The active GeometryViewport of the current Scene Viewer. Clear error if unavailable."""
    sv = sv or _scene_viewer()
    try:
        vp = sv.curViewport()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the current viewport: %s" % exc)
    if vp is None:
        raise ValueError("no active viewport in the Scene Viewer")
    return vp


def _clean_text(s, cap=200):
    """Display-only sanitize: coerce to str, strip C0/C1 control chars (keep normal spaces), cap
    length. This text is only ever shown on-screen -- it is never evaluated."""
    s = str(s)
    out = []
    for ch in s:
        o = ord(ch)
        if o == 9 or o == 10 or o == 32:        # tab / newline / space -> normalize to a space
            out.append(" ")
        elif o < 32 or 127 <= o < 160:          # other C0/C1 control chars -> drop
            continue
        else:
            out.append(ch)
    return "".join(out)[:cap]


# ── enum token maps (verbatim from the installed build) ──────────────────────────────────────────
_SNAP_MODES = {"off": "Off", "grid": "Grid", "prim": "Prim", "point": "Point", "multi": "Multi"}
_PROMPT_LEVELS = {"prompt": "Prompt", "message": "Message", "warning": "Warning", "error": "Error"}
_HOME_METHODS = {"all": "homeAll", "selected": "homeSelected",
                 "grid": "homeGrid", "non_templated": "homeNonTemplated"}
# per-target snap toggles: param name -> SceneViewer setter
_SNAP_TOGGLES = {"to_geometry": "setSnapToCurrentGeometry",
                 "to_templates": "setSnapToTemplates",
                 "to_other_objects": "setSnapToOtherObjects",
                 "to_guides": "setSnapToGuides",
                 "to_drawables": "setSnapToDrawables"}


# ── viewport_snap ────────────────────────────────────────────────────────────────────────────────
@endpoint("viewport_snap")
def viewport_snap(params):
    """Set Scene Viewer snapping. `mode` picks the overall snapping mode (setSnappingMode); the
    per-target `to_*` bools toggle what snapping locks onto within the current mode. Only SUPPLIED
    params change (each toggle is applied only when present). Returns what was applied plus the
    resulting snapping-mode token."""
    sv = _scene_viewer()
    applied = {}

    mode = params.get("mode")
    if mode is not None:
        key = str(mode).lower()
        if key not in _SNAP_MODES:
            raise ValueError("mode must be one of %s" % sorted(_SNAP_MODES))
        try:
            sv.setSnappingMode(getattr(hou.snappingMode, _SNAP_MODES[key]))
            applied["mode"] = _SNAP_MODES[key]
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set snapping mode: %s" % exc)

    for pname, setter in _SNAP_TOGGLES.items():
        if pname in params:
            on = bool(params[pname])
            fn = getattr(sv, setter, None)
            if fn is None:
                raise ValueError("this build has no %s" % setter)
            try:
                fn(on)
                applied[pname] = on
            except (hou.OperationFailed, AttributeError, TypeError) as exc:
                raise ValueError("cannot set %s: %s" % (pname, exc))

    if not applied:
        raise ValueError("nothing to do: supply `mode` and/or at least one to_* toggle")

    result = {"applied": applied}
    try:
        result["snapping_mode"] = sv.snappingMode().name()
    except Exception:
        pass
    return result


# ── view_message ─────────────────────────────────────────────────────────────────────────────────
@endpoint("view_message")
def view_message(params):
    """Show an operator-facing message in the Scene Viewer (watched-crew UX). `type=flash` (default)
    shows a transient overlay via flashMessage for `duration` seconds; `type=prompt` sets the
    persistent status-line prompt via setPromptMessage at severity `level`. Text is display-only:
    control chars are stripped and it is capped at 200 chars. Nothing is evaluated."""
    raw = params.get("message")
    if raw is None:
        raise ValueError("message is required")
    msg = _clean_text(raw, cap=200)
    if not msg:
        raise ValueError("message is empty after control-char stripping")

    sv = _scene_viewer()
    kind = str(params.get("type", "flash")).lower()

    if kind == "flash":
        dur = clamp(float(params.get("duration", 1.0)), 0.1, 10.0)
        try:
            # first arg is an optional image-file overlay. It is a std::string in the SWIG binding and
            # REJECTS None ("invalid null reference"); pass "" for a plain text flash (live-verified).
            sv.flashMessage("", msg, dur)
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot flash message: %s" % exc)
        return {"shown": msg, "type": "flash", "duration": dur}

    if kind == "prompt":
        lvl = str(params.get("level", "message")).lower()
        if lvl not in _PROMPT_LEVELS:
            raise ValueError("level must be one of %s" % sorted(_PROMPT_LEVELS))
        try:
            sv.setPromptMessage(msg, getattr(hou.promptMessageType, _PROMPT_LEVELS[lvl]))
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set prompt message: %s" % exc)
        return {"shown": msg, "type": "prompt", "level": _PROMPT_LEVELS[lvl]}

    raise ValueError("type must be 'flash' or 'prompt'")


# ── home_view ────────────────────────────────────────────────────────────────────────────────────
@endpoint("home_view")
def home_view(params):
    """Home/tumble the current viewport to the default view direction for a target (distinct from
    `frame_selected`, which preserves the view direction). `target`: all (default) | selected | grid
    | non_templated."""
    target = str(params.get("target", "all")).lower()
    if target not in _HOME_METHODS:
        raise ValueError("target must be one of %s" % sorted(_HOME_METHODS))
    vp = _cur_viewport()
    fn = getattr(vp, _HOME_METHODS[target], None)
    if fn is None:
        raise ValueError("this build has no %s" % _HOME_METHODS[target])
    try:
        fn()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot home view (%s): %s" % (target, exc))
    return {"homed": target}


# ── save_view_to_camera ──────────────────────────────────────────────────────────────────────────
@endpoint("save_view_to_camera")
def save_view_to_camera(params):
    """Bake the current interactive viewport view into a camera node (its transform + view lens
    settings), the "save view to camera" operation. `camera` is the target camera OBJ node path
    (resolved + must exist). If `lock` is true, also lock the viewport to its camera after saving
    (guarded -- only meaningful when the viewport is looking through a camera)."""
    cam = resolve_node(params["camera"])
    vp = _cur_viewport()
    try:
        vp.saveViewToCamera(cam)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot save view to camera %s: %s" % (cam.path(), exc))
    out = {"saved_to": cam.path(), "locked": False}
    if bool(params.get("lock", False)):
        try:
            vp.lockCameraToView()
            out["locked"] = True
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            out["lock_note"] = "lockCameraToView unavailable/failed: %s" % str(exc)[:80]
    return out


# ── construction_plane ───────────────────────────────────────────────────────────────────────────
@endpoint("construction_plane")
def construction_plane(params):
    """Show/hide and size the Scene Viewer construction-plane grid. Only SUPPLIED params change:
    `visible` (bool) toggles the grid; `cell_size` (float>0) sets the grid cell size; `cells`
    (int>=1) sets the number of cells; `cells_per_ruler` (int>=1) sets cells per ruler line. The
    grid is 2D, so a scalar is applied to both axes."""
    sv = _scene_viewer()
    try:
        cp = sv.constructionPlane()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the construction plane: %s" % exc)
    if cp is None:
        raise ValueError("no construction plane on this Scene Viewer")

    applied = {}
    if "visible" in params:
        try:
            cp.setIsVisible(bool(params["visible"]))
            applied["visible"] = bool(params["visible"])
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set construction-plane visibility: %s" % exc)

    if "cell_size" in params:
        v = float(params["cell_size"])
        if v <= 0:
            raise ValueError("cell_size must be > 0")
        try:
            cp.setCellSize((v, v))          # cellSize() -> tuple of float
            applied["cell_size"] = v
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set cell_size: %s" % exc)

    if "cells" in params:
        n = int(params["cells"])
        if n < 1:
            raise ValueError("cells must be >= 1")
        try:
            cp.setNumberOfCells((n, n))     # numberOfCells() -> tuple of int
            applied["cells"] = n
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set cells: %s" % exc)

    if "cells_per_ruler" in params:
        n = int(params["cells_per_ruler"])
        if n < 1:
            raise ValueError("cells_per_ruler must be >= 1")
        try:
            cp.setNumberOfCellsPerRulerLine((n, n))
            applied["cells_per_ruler"] = n
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set cells_per_ruler: %s" % exc)

    if not applied:
        raise ValueError("nothing to do: supply visible / cell_size / cells / cells_per_ruler")
    return {"applied": applied}


# ── ui_reference (READ-ONLY discoverability; never actuates) ─────────────────────────────────────
_UI_REFERENCE = {
    "control_surface_tools": {
        "viewport_snap": "Set Scene Viewer snapping: mode (Off|Grid|Prim|Point|Multi) + per-target "
                         "to_geometry/to_templates/to_other_objects/to_guides/to_drawables bools.",
        "view_message": "Show an operator message in the viewport: type=flash (transient overlay, "
                        "duration s) or type=prompt (status line, level Prompt|Message|Warning|Error).",
        "home_view": "Home/tumble the viewport: target=all|selected|grid|non_templated.",
        "save_view_to_camera": "Bake the current view into a camera OBJ (camera=path, optional lock).",
        "construction_plane": "Show/hide + size the construction grid: visible / cell_size / cells / "
                              "cells_per_ruler.",
        "ui_reference": "This read-only helper. Returns the control-surface tool list + drivable-UI "
                        "state + confirmed enum tokens. Never actuates.",
    },
    "enum_tokens": {
        "snapping_mode": ["Off", "Grid", "Prim", "Point", "Multi"],
        "prompt_message_type": ["Error", "Message", "Prompt", "Warning"],
        "home_target": ["all", "selected", "grid", "non_templated"],
        "view_message_type": ["flash", "prompt"],
    },
    "notes": "All control-surface tools drive the interactive Scene Viewer, which requires a live "
             "GUI session (absent in headless hython). Data-only: no param accepts code/callables.",
}


@endpoint("ui_reference")
def ui_reference(params):
    """Read-only discoverability helper (mirrors node_reference / vex_reference: serves text, never
    actuates). Returns the control-surface tool catalog + confirmed enum tokens (always, even
    headless), and -- when a live GUI is present -- the CURRENT drivable-UI state (snapping mode,
    construction-plane visibility, viewer state name, desktop names). Reading a registry is not
    registering. `topic` optionally narrows to: tools | enums | live | all (default all)."""
    topic = str(params.get("topic", "all")).lower()
    out = {}

    if topic in ("tools", "all"):
        out["control_surface_tools"] = _UI_REFERENCE["control_surface_tools"]
    if topic in ("enums", "all"):
        out["enum_tokens"] = _UI_REFERENCE["enum_tokens"]
    if topic in ("tools", "enums", "all"):
        out["notes"] = _UI_REFERENCE["notes"]

    if topic in ("live", "all"):
        live = {"gui_available": False}
        ui = getattr(hou, "ui", None)
        if ui is not None:
            live["gui_available"] = True
            # Everything below is fail-soft: a missing pane / state simply omits that field.
            try:
                names = [d.name() for d in ui.desktops()]
                live["desktops"] = names
                cur = ui.curDesktop()
                live["current_desktop"] = cur.name() if cur is not None else None
            except Exception:
                pass
            try:
                sv = ui.paneTabOfType(hou.paneTabType.SceneViewer)
            except Exception:
                sv = None
            if sv is not None:
                try:
                    live["snapping_mode"] = sv.snappingMode().name()
                except Exception:
                    pass
                try:
                    cp = sv.constructionPlane()
                    if cp is not None:
                        live["construction_plane_visible"] = bool(cp.isVisible())
                except Exception:
                    pass
                try:
                    live["current_viewer_state"] = sv.currentState()
                except Exception:
                    pass
            else:
                live["scene_viewer_open"] = False
        out["live"] = live

    if not out:
        raise ValueError("topic must be one of: tools | enums | live | all")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# pane / desktop / parameter navigation + read-only hotkey reference.
#
# Same DATA-ONLY discipline: every param is a typed scalar / enum token / bool / node
# path resolving to a built-in HOM method that takes NO Python callable. Nothing compiles/loads/evals
# a caller string; there is no callback surface anywhere below.
# REFUSED (author a Python Panel interface, author/mutate hotkey config) is NOT built here.
#
# These drive the desktop / pane manager / path-based panes / network editor, all of which live in
# the interactive UI layer. In a headless hython session `hou.ui` and `hou.hotkeys` do not exist, so
# EVERY tool below (incl. hotkey_reference) resolves the UI through a guard that raises a CLEAR
# ValueError instead of an AttributeError. Signatures were pinned against Houdini 21.0.671 via the
# offline help server + hython introspection (dir() on the classes; hou.paneTabType/hou.paneLinkType
# member enumeration).
#
# HOM APIs used (all confirmed present on 21.0.671):
#   hou.ui.desktops / curDesktop / paneTabOfType
#   hou.Desktop.setAsCurrent / panes / paneTabs / name
#   hou.Pane.id / tabs / currentTab / createTab(type, python_panel_interface=None) /
#       splitHorizontally / splitVertically / setIsMaximized / isMaximized
#   hou.PaneTab.setType(type) / type / name / setIsCurrentTab / close / clone / setPin(pin) / isPin /
#       setLinkGroup(group) / linkGroup
#   hou.PathBasedPaneTab.setCurrentNode(node, pick_node=True) / setPwd(node) / currentNode / pwd
#   hou.NetworkEditor.setPwd(node) / setCurrentNode(node, pick_node=True) / frameSelection /
#       homeToSelection / pwd
#   hou.hotkeys.contextsInContext / commandsInContext / commandsInCategory /
#       commandCategoriesInCategory / hotkeyLabel / hotkeyDescription / assignments (READ-ONLY subset)
#   enums: hou.paneTabType {SceneViewer,NetworkEditor,Parm,ParmSpreadsheet,DetailsView,PythonShell,
#          SceneGraphTree,ChannelEditor,MaterialPalette,...}  ·
#          hou.paneLinkType {FollowSelection,Pinned,Group1..Group9}
# ═════════════════════════════════════════════════════════════════════════════════════════════════


# ── UI / desktop / pane resolution (fail-clear when there is no GUI) ──────────────────────────────
def _ui():
    """`hou.ui`, or a CLEAR error headless. Every control-surface UI tool needs the interactive UI layer."""
    ui = getattr(hou, "ui", None)
    if ui is None:
        raise ValueError("no interactive UI available (headless session; GUI-only tool)")
    return ui


def _current_desktop():
    """The current desktop, or a clear error."""
    ui = _ui()
    try:
        d = ui.curDesktop()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the current desktop: %s" % exc)
    if d is None:
        raise ValueError("no current desktop")
    return d


def _pane_tab_type_tokens():
    """Verbatim set of valid hou.paneTabType member tokens on this build (drop the SWIG 'thisown')."""
    tt = getattr(hou, "paneTabType", None)
    if tt is None:
        raise ValueError("this build has no hou.paneTabType")
    return sorted(m for m in dir(tt) if not m.startswith("_") and m != "thisown")


def _resolve_pane_tab_type(token):
    """Map a caller string to an existing hou.paneTabType member (case-insensitive). Data-only: this
    selects a built-in enum value by name; it never constructs or evaluates anything."""
    valid = _pane_tab_type_tokens()
    lut = {t.lower(): t for t in valid}
    key = str(token).lower()
    if key not in lut:
        raise ValueError("type must be one of %s" % valid)
    return getattr(hou.paneTabType, lut[key])


def _pane_link_tokens():
    lt = getattr(hou, "paneLinkType", None)
    if lt is None:
        raise ValueError("this build has no hou.paneLinkType")
    return sorted(m for m in dir(lt) if not m.startswith("_") and m != "thisown")


def _find_pane(pane_id):
    """The Pane with the given integer id in the current desktop, or a clear error. If pane_id is
    None, return the pane hosting the current Network Editor (falling back to the first pane)."""
    d = _current_desktop()
    try:
        panes = list(d.panes())
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot enumerate panes: %s" % exc)
    if not panes:
        raise ValueError("no panes in the current desktop")
    if pane_id is None:
        ui = _ui()
        try:
            ne = ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            if ne is not None and ne.pane() is not None:
                return ne.pane()
        except Exception:
            pass
        return panes[0]
    want = int(pane_id)
    for p in panes:
        try:
            if int(p.id()) == want:
                return p
        except Exception:
            continue
    ids = []
    for p in panes:
        try:
            ids.append(int(p.id()))
        except Exception:
            pass
    raise ValueError("no pane with id %d (available: %s)" % (want, sorted(ids)))


def _pathbased_kind_to_type():
    """pane-kind token -> the hou.paneTabType used to locate that path-based pane."""
    return {"parm": "Parm", "network": "NetworkEditor", "scene": "SceneViewer"}


def _find_pathbased_tab(kind):
    """Locate the visible path-based pane tab of a kind (parm|network|scene) and confirm it supports
    node navigation (has setCurrentNode). Clear error otherwise."""
    kinds = _pathbased_kind_to_type()
    k = str(kind).lower()
    if k not in kinds:
        raise ValueError("pane must be one of %s" % sorted(kinds))
    ui = _ui()
    try:
        tab = ui.paneTabOfType(getattr(hou.paneTabType, kinds[k]))
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the %s pane: %s" % (k, exc))
    if tab is None:
        raise ValueError("no %s pane open" % k)
    if getattr(tab, "setCurrentNode", None) is None:
        raise ValueError("the %s pane does not support node navigation on this build" % k)
    return tab


# ── switch_desktop ────────────────────────────────────────────────────────────────────────────────
@endpoint("switch_desktop")
def switch_desktop(params):
    """Make an existing desktop (saved pane layout) current, by name. Resolves `desktop` against the
    live `hou.ui.desktops()` set (an existing-name allowlist -- no free-form layout is created), then
    calls hou.Desktop.setAsCurrent(). Returns the desktop switched to and the full available list."""
    name = params.get("desktop")
    if name is None or not str(name).strip():
        raise ValueError("desktop (name) is required")
    name = str(name)
    ui = _ui()
    try:
        desktops = list(ui.desktops())
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot enumerate desktops: %s" % exc)
    names = [d.name() for d in desktops]
    match = next((d for d in desktops if d.name() == name), None)
    if match is None:
        raise ValueError("no desktop named %r (available: %s)" % (name, names))
    try:
        match.setAsCurrent()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot switch to desktop %r: %s" % (name, exc))
    return {"current_desktop": name, "available": names}


# ── pane_focus_node ────────────────────────────────────────────────────────────────────────────────
@endpoint("pane_focus_node")
def pane_focus_node(params):
    """Jump a path-based pane to a node (quick-nav). `pane` = parm | network | scene selects which
    path-based pane tab; `node` (resolved node path, must exist) becomes that pane's current node via
    setCurrentNode. For `network` you may also dive the editor into the node's own network by passing
    `dive=true` (setPwd). Only navigates -- authors nothing."""
    node = resolve_node(params["node"])
    kind = params.get("pane", "parm")
    tab = _find_pathbased_tab(kind)
    try:
        tab.setCurrentNode(node)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot focus %s pane on %s: %s" % (kind, node.path(), exc))
    out = {"pane": str(kind).lower(), "current_node": node.path(), "dived": False}
    if bool(params.get("dive", False)) and getattr(tab, "setPwd", None) is not None:
        try:
            tab.setPwd(node)
            out["dived"] = True
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            out["dive_note"] = "setPwd failed: %s" % str(exc)[:80]
    return out


# ── pane_pin ──────────────────────────────────────────────────────────────────────────────────────
@endpoint("pane_pin")
def pane_pin(params):
    """Pin / unpin (or set the link group of) a path-based pane so it stops following selection.
    `pane` = parm | network | scene. Supply EITHER `pin` (bool -> setPin: True pins, False returns to
    Follow-Selection) OR `link_group` (enum token: FollowSelection | Pinned | Group1..Group9 ->
    setLinkGroup). Returns the resulting pin/link state."""
    kind = params.get("pane", "parm")
    tab = _find_pathbased_tab(kind)

    if "link_group" in params:
        valid = _pane_link_tokens()
        lut = {t.lower(): t for t in valid}
        key = str(params["link_group"]).lower()
        if key not in lut:
            raise ValueError("link_group must be one of %s" % valid)
        try:
            tab.setLinkGroup(getattr(hou.paneLinkType, lut[key]))
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set link group: %s" % exc)
        applied = {"link_group": lut[key]}
    elif "pin" in params:
        on = bool(params["pin"])
        try:
            tab.setPin(on)
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set pin: %s" % exc)
        applied = {"pin": on}
    else:
        raise ValueError("supply either `pin` (bool) or `link_group` (enum token)")

    out = {"pane": str(kind).lower(), "applied": applied}
    try:
        out["is_pinned"] = bool(tab.isPin())
    except Exception:
        pass
    try:
        out["link_group_now"] = tab.linkGroup().name()
    except Exception:
        pass
    return out


# ── pane_tab ──────────────────────────────────────────────────────────────────────────────────────
@endpoint("pane_tab")
def pane_tab(params):
    """Manage pane tabs by TYPE (data-only). `op`:
      query    -> list valid paneTabType tokens + the current desktop's tabs (name/type/pane id/current)
      create   -> create a new tab of `type` on the target pane (createTab; NO python_panel_interface
                  -> authoring a Python Panel is REFUSED, only a built-in type is created)
      set_type -> change the target tab's type to `type` (setType)
      current  -> make the target tab the current (front) tab (setIsCurrentTab)
      clone    -> clone the target tab (clone)
      close    -> close the target tab (close; reversible session-UI op)
    Target pane is `pane_id` (int from Pane.id(); default = pane hosting the Network Editor). The
    target TAB for set_type/current/clone/close is that pane's current tab. Run `query` first to
    discover pane ids + types."""
    op = str(params.get("op", "query")).lower()

    if op == "query":
        d = _current_desktop()
        tabs = []
        try:
            for t in d.paneTabs():
                rec = {}
                try:
                    rec["name"] = t.name()
                except Exception:
                    pass
                try:
                    rec["type"] = t.type().name()
                except Exception:
                    pass
                try:
                    rec["pane_id"] = int(t.pane().id()) if t.pane() is not None else None
                except Exception:
                    rec["pane_id"] = None
                try:
                    rec["is_current"] = bool(t.isCurrentTab())
                except Exception:
                    pass
                tabs.append(rec)
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot enumerate pane tabs: %s" % exc)
        return {"pane_tab_types": _pane_tab_type_tokens(), "desktop": d.name(), "tabs": tabs}

    pane = _find_pane(params.get("pane_id"))

    if op == "create":
        if "type" not in params:
            raise ValueError("create requires `type` (a paneTabType token)")
        ttype = _resolve_pane_tab_type(params["type"])
        try:
            new_tab = pane.createTab(ttype)          # NO python_panel_interface -> data-only
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot create tab: %s" % exc)
        res = {"op": "create", "pane_id": int(pane.id())}
        try:
            res["created"] = {"name": new_tab.name(), "type": new_tab.type().name()}
        except Exception:
            pass
        return res

    # set_type / current / clone / close all act on the pane's current tab.
    try:
        tab = pane.currentTab()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the pane's current tab: %s" % exc)
    if tab is None:
        raise ValueError("target pane (id %d) has no current tab" % int(pane.id()))

    if op == "set_type":
        if "type" not in params:
            raise ValueError("set_type requires `type` (a paneTabType token)")
        ttype = _resolve_pane_tab_type(params["type"])
        try:
            tab.setType(ttype)
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set tab type: %s" % exc)
        return {"op": "set_type", "pane_id": int(pane.id()), "type": params_type_name(ttype)}

    if op == "current":
        try:
            tab.setIsCurrentTab()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set current tab: %s" % exc)
        return {"op": "current", "pane_id": int(pane.id()), "tab": _safe_name(tab)}

    if op == "clone":
        try:
            clone = tab.clone()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot clone tab: %s" % exc)
        return {"op": "clone", "pane_id": int(pane.id()), "cloned": _safe_name(clone)}

    if op == "close":
        try:
            tab.close()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot close tab: %s" % exc)
        return {"op": "close", "pane_id": int(pane.id())}

    raise ValueError("op must be one of: query | create | set_type | current | clone | close")


def params_type_name(ttype):
    try:
        return ttype.name()
    except Exception:
        return str(ttype)


def _safe_name(tab):
    try:
        return tab.name()
    except Exception:
        return None


# ── pane_layout ───────────────────────────────────────────────────────────────────────────────────
@endpoint("pane_layout")
def pane_layout(params):
    """Split / maximize / restore the pane layout of the current desktop (reversible session-UI).
    `op`: split_h (splitHorizontally) | split_v (splitVertically) | maximize (setIsMaximized True) |
    restore (setIsMaximized False). Target pane is `pane_id` (int; default = pane hosting the Network
    Editor). Splitting returns the new pane's id."""
    op = str(params.get("op", "")).lower()
    if op not in ("split_h", "split_v", "maximize", "restore"):
        raise ValueError("op must be one of: split_h | split_v | maximize | restore")
    pane = _find_pane(params.get("pane_id"))

    if op in ("split_h", "split_v"):
        setter = "splitHorizontally" if op == "split_h" else "splitVertically"
        fn = getattr(pane, setter, None)
        if fn is None:
            raise ValueError("this build has no %s" % setter)
        try:
            new_pane = fn()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot %s: %s" % (op, exc))
        out = {"op": op, "pane_id": int(pane.id())}
        try:
            out["new_pane_id"] = int(new_pane.id()) if new_pane is not None else None
        except Exception:
            pass
        return out

    on = (op == "maximize")
    try:
        pane.setIsMaximized(on)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot %s pane: %s" % (op, exc))
    out = {"op": op, "pane_id": int(pane.id())}
    try:
        out["is_maximized"] = bool(pane.isMaximized())
    except Exception:
        pass
    return out


# ── network_navigate ──────────────────────────────────────────────────────────────────────────────
@endpoint("network_navigate")
def network_navigate(params):
    """Drive the Network Editor pane through the node graph (navigation only). Supply at least one of:
      `path`         -> dive the editor into this network node (setPwd)
      `current_node` -> select + make this node the editor's current node (setCurrentNode)
      `frame`        -> bool; frame the current selection after navigating (frameSelection)
    All paths are resolved and must exist. Returns the editor's resulting pwd."""
    ui = _ui()
    try:
        ne = ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access the Network Editor: %s" % exc)
    if ne is None:
        raise ValueError("no Network Editor pane open")

    did = {}
    if "path" in params and params["path"] is not None:
        net = resolve_node(params["path"])
        try:
            ne.setPwd(net)
            did["pwd"] = net.path()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot dive into %s: %s" % (net.path(), exc))

    if "current_node" in params and params["current_node"] is not None:
        cn = resolve_node(params["current_node"])
        try:
            ne.setCurrentNode(cn)
            did["current_node"] = cn.path()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set current node %s: %s" % (cn.path(), exc))

    if bool(params.get("frame", False)):
        try:
            ne.frameSelection()
            did["framed"] = True
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            did["frame_note"] = "frameSelection failed: %s" % str(exc)[:80]

    if not did:
        raise ValueError("nothing to do: supply at least one of path / current_node / frame")
    try:
        did["editor_pwd"] = ne.pwd().path()
    except Exception:
        pass
    return did


# ── hotkey_reference (READ-ONLY; never actuates) ─────────────────────────────────────────────────
# hou.hotkeys is a definition/config module: add*/remove*/install*/save*/load* AUTHOR or MUTATE
# persistent hotkey config -> REFUSED (never called here). This helper touches ONLY the read subset:
# contextsInContext / commandsInContext / commandsInCategory / commandCategoriesInCategory /
# hotkeyLabel / hotkeyDescription / assignments. Reading the assignment registry is not registering.
_HOTKEY_READ_FNS = ("contextsInContext", "commandsInContext", "commandsInCategory",
                    "commandCategoriesInCategory", "hotkeyLabel", "hotkeyDescription", "assignments")
_HOTKEY_MAX_DEFAULT = 1500
_HOTKEY_MAX_CAP = 6000


def _hotkeys_module():
    """hou.hotkeys, or a CLEAR error. Absent in a plain headless hython session -- it is part of the
    UI layer -- so this helper (like every control-surface UI tool) needs the live Houdini session."""
    hk = getattr(hou, "hotkeys", None)
    if hk is None:
        raise ValueError("hou.hotkeys unavailable (headless/no-UI session); hotkey reference needs a "
                         "live Houdini session")
    return hk


def _hk_walk(hk, context, out, seen, limit, search, want_unassigned):
    """Depth-first walk of the hotkey context tree, collecting command -> {label, keys}. Read-only."""
    if len(out) >= limit or context in seen:
        return
    seen.add(context)
    # commands directly in this context
    try:
        cmds = hk.commandsInContext(context) or []
    except Exception:
        cmds = []
    for sym in cmds:
        if len(out) >= limit:
            return
        try:
            keys = list(hk.assignments(context, sym) or [])
        except Exception:
            keys = []
        if not keys and not want_unassigned:
            continue
        try:
            label = hk.hotkeyLabel(sym)
        except Exception:
            label = None
        if search:
            hay = " ".join([str(sym), str(label or ""), " ".join(keys)]).lower()
            if search not in hay:
                continue
        out.append({"context": context, "command": sym, "label": label, "keys": keys})
    # recurse into child contexts
    try:
        children = hk.contextsInContext(context) or []
    except Exception:
        children = []
    for child in children:
        if len(out) >= limit:
            return
        _hk_walk(hk, child, out, seen, limit, search, want_unassigned)


@endpoint("hotkey_reference")
def hotkey_reference(params):
    """Read-only hotkey map reader (sibling of ui_reference / vex_reference: serves data, never
    actuates). Walks the default hotkey context tree from `context` (root symbol, default "h") and
    returns, per command, its context, symbol, human label, and assigned key strings. This ONLY calls
    the read subset of hou.hotkeys (contextsInContext / commandsInContext / assignments / hotkeyLabel);
    it NEVER calls any add*/remove*/install*/save*/load* mutator.

    Params (all optional):
      context     : str   -- root context symbol to walk from (default "h" = all of Houdini)
      category    : str   -- instead of a context walk, list commands in this hotkey CATEGORY
                             (commandsInCategory); mutually exclusive with a deep context walk
      search      : str   -- case-insensitive substring filter over symbol/label/keys
      unassigned  : bool  -- include commands with no key assignment (default false: hotkey MAP only)
      max         : int   -- cap on returned entries (default 1500, hard cap 6000)

    Needs a live Houdini session (hou.hotkeys is part of the UI layer; absent in headless hython)."""
    hk = _hotkeys_module()
    search = params.get("search")
    search = str(search).lower() if search else None
    want_unassigned = bool(params.get("unassigned", False))
    try:
        limit = int(params.get("max", _HOTKEY_MAX_DEFAULT))
    except (TypeError, ValueError):
        raise ValueError("max must be an integer")
    limit = int(clamp(limit, 1, _HOTKEY_MAX_CAP))

    # category mode: flat list of commands in one category
    if params.get("category"):
        cat = str(params["category"])
        try:
            cmds = hk.commandsInCategory(cat) or []
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot list commands in category %r: %s" % (cat, exc))
        entries = []
        for sym in cmds:
            if len(entries) >= limit:
                break
            try:
                label = hk.hotkeyLabel(sym)
            except Exception:
                label = None
            # assignments() needs a context; the category commands carry their own symbol context.
            keys = []
            try:
                keys = list(hk.assignments(sym, sym) or [])
            except Exception:
                pass
            if search:
                hay = " ".join([str(sym), str(label or ""), " ".join(keys)]).lower()
                if search not in hay:
                    continue
            entries.append({"category": cat, "command": sym, "label": label, "keys": keys})
        return {"mode": "category", "category": cat, "count": len(entries), "commands": entries}

    root = str(params.get("context", "h"))
    out = []
    _hk_walk(hk, root, out, set(), limit, search, want_unassigned)
    return {"mode": "context", "root": root, "count": len(out),
            "truncated": len(out) >= limit, "commands": out}


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# node flags & organization + viewport appearance / layout.
#
# Same DATA-ONLY discipline as the rest of this module: every param is a typed scalar / enum token / bool / node
# path / numeric vector resolving to a built-in HOM method that takes NO Python callable. Nothing
# compiles/loads/evals a caller string; `comment`/`name` text is DISPLAY-ONLY (sanitized via
# _clean_text, never evaluated). There is no callback surface anywhere below.
#
#
# Split by GUI-dependence:
#   * set_node_flags / node_organize operate on a NODE, which exists WITHOUT a GUI -> fully reachable
#     and actuation-verifiable in headless hython (create node -> set -> read back).
#   * viewport_appearance / viewport_layout drive the live Scene Viewer / GeometryViewport, absent in
#     headless hython -> guarded by _scene_viewer()/_cur_viewport() (CLEAR ValueError, never an
#     AttributeError); actuation lands only in the live GUI executor.
#
# Every enum/flag/shape token below was LIVE-ENUMERATED against the installed build (Houdini
# 21.0.671) via hython dir()/introspection + the offline help server -- not guessed. Tokens are
# resolved live at call time (drift-proof), never hard-baked into the actuation path.
#
# HOM APIs used (all confirmed present on 21.0.671):
#   hou.Node.setGenericFlag(hou.nodeFlag.<X>, bool) / isGenericFlagSet
#   hou.Node.setColor(hou.Color) / color / setComment / comment / setName(name, unique_name=True) /
#       setPosition(hou.Vector2) / setUserData("nodeshape", token)
#   hou.SceneViewer.curViewport().settings() -> hou.GeometryViewportSettings
#   hou.GeometryViewportSettings.setColorScheme / setLighting / setRemoveBackfaces / setDisplayTextures
#       / setAmbientOcclusion / setDisplayOrthoGrid / setHullsOnly / setXrayDrawing / setHeadlightIntensity
#       / displaySet(hou.displaySetType.<X>) -> hou.GeometryViewportDisplaySet
#   hou.GeometryViewportDisplaySet.setShadedMode(hou.glShadingType.<X>) / setBoundaryMode /
#       set{Point,Prim,Vertex}{Marker,Normal,Number}Visibility(hou.markerVisibility.<X>)
#   hou.SceneViewer.setViewportLayout(hou.geometryViewportLayout.<X>, single=-1) / viewportLayout
#   enums (verbatim members below):
#     hou.nodeFlag {Audio,Bypass,ColorDefault,Compress,Current,Debug,Display,DisplayComment,
#         DisplayDescriptiveName,Export,Expose,Footprint,Highlight,InOutDetailHigh/Low/Medium,Lock,
#         Material,Origin,OutputForDisplay,Pick,Render,Selectable,SoftLock,Template,Unload,Visible,XRay}
#     hou.glShadingType {Flat,FlatWire,HiddenLineGhost,HiddenLineInvisible,MatCap,MatCapWire,
#         ShadedBoundingBox,Smooth,SmoothWire,Wire,WireBoundingBox,WireGhost}
#     hou.markerVisibility {Always,AroundPointer,Selected,UnderPointer}  (NO "off" token on this build)
#     hou.boundaryDisplay {Off,On,View3D,ViewUV}
#     hou.displaySetType {CurrentModel,DisplayModel,GhostObject,SceneObject,SelectedObject,TemplateModel}
#     hou.viewportColorScheme {Dark,DarkGrey,Grey,Light}
#     hou.viewportLighting {Headlight,HighQuality,HighQualityWithShadows,Normal,Off}
#     hou.geometryViewportLayout {DoubleSide,DoubleStack,Quad,QuadBottomSplit,QuadLeftSplit,Single,
#         TripleBottomSplit,TripleLeftSplit}
#   node-shape tokens (built-in NodeShapes on this build) listed in _NODE_SHAPES below.
# ═════════════════════════════════════════════════════════════════════════════════════════════════


def _norm_token(s):
    """Normalize a token for matching: lowercase, drop underscores/spaces."""
    return str(s).replace("_", "").replace(" ", "").lower()


def _resolve_enum(enum_name, token, aliases=None):
    """Resolve a caller string to an existing member of hou.<enum_name>, LIVE (drift-proof). Matching
    is case/underscore-insensitive against the build's actual members; `aliases` maps friendly caller
    tokens to real member names (checked first). Data-only: selects a built-in enum value by name --
    it never constructs, imports, or evaluates anything. Raises a CLEAR ValueError listing the real
    members on no match."""
    enum_obj = getattr(hou, enum_name, None)
    if enum_obj is None:
        raise ValueError("this build has no hou.%s" % enum_name)
    members = [m for m in dir(enum_obj) if not m.startswith("_") and m != "thisown"]
    key = str(token).lower()
    if aliases and key in aliases:
        member = aliases[key]
        if not hasattr(enum_obj, member):
            raise ValueError("hou.%s has no member %r (build members: %s)"
                             % (enum_name, member, sorted(members)))
        return getattr(enum_obj, member), member
    norm = {_norm_token(m): m for m in members}
    nk = _norm_token(token)
    if nk not in norm:
        extra = (" or aliases %s" % sorted(aliases)) if aliases else ""
        raise ValueError("must be one of hou.%s members %s%s"
                         % (enum_name, sorted(members), extra))
    return getattr(enum_obj, norm[nk]), norm[nk]


# ── set_node_flags ────────────────────────────────────────────────────────────────────────────────
# param name -> hou.nodeFlag member. Resolved live via setGenericFlag(hou.nodeFlag.<X>, bool) -- the
# uniform, drift-proof path (the per-flag setDisplayFlag/setTemplateFlag/... helpers are NOT on base
# hou.Node in this build; they live on subclasses. setGenericFlag is on hou.Node and covers all).
_NODE_FLAGS = {
    "display": "Display", "render": "Render", "template": "Template",
    "selectable_template": "Selectable", "bypass": "Bypass", "lock": "Lock",
    "soft_lock": "SoftLock", "highlight": "Highlight", "debug": "Debug",
    "visible": "Visible", "xray": "XRay", "display_comment": "DisplayComment",
    "display_descriptive_name": "DisplayDescriptiveName",
}


@endpoint("set_node_flags")
def set_node_flags(params):
    """Set node flags on ONE node via hou.Node.setGenericFlag(hou.nodeFlag.<X>, bool). Only SUPPLIED
    flags change; each is an optional typed bool. Supported flags (param -> hou.nodeFlag member):
      display->Display · render->Render · template->Template · selectable_template->Selectable ·
      bypass->Bypass · lock->Lock · soft_lock->SoftLock · highlight->Highlight · debug->Debug ·
      visible->Visible · xray->XRay · display_comment->DisplayComment ·
      display_descriptive_name->DisplayDescriptiveName.
    Not every flag applies to every node type; an inapplicable flag is reported in `errors` rather than
    failing the whole call. `node` (required) is a resolved node path. Works headless (a node exists
    without a GUI). Returns the applied flags (with read-back where available) + any per-flag errors."""
    node = resolve_node(params["node"])
    applied, errors = {}, {}
    nf = getattr(hou, "nodeFlag", None)
    if nf is None:
        raise ValueError("this build has no hou.nodeFlag")
    for pname, member in _NODE_FLAGS.items():
        if pname not in params:
            continue
        on = bool(params[pname])
        flag = getattr(nf, member, None)
        if flag is None:
            errors[pname] = "hou.nodeFlag has no %s on this build" % member
            continue
        try:
            node.setGenericFlag(flag, on)
            applied[pname] = on
        except (hou.OperationFailed, hou.OperationInterrupted, AttributeError, TypeError) as exc:
            errors[pname] = "cannot set %s flag: %s" % (member, str(exc)[:100])
    if not applied and not errors:
        raise ValueError("nothing to do: supply at least one flag bool (%s)" % sorted(_NODE_FLAGS))
    # fail-soft read-back of what stuck
    readback = {}
    for pname in applied:
        flag = getattr(nf, _NODE_FLAGS[pname], None)
        try:
            readback[pname] = bool(node.isGenericFlagSet(flag))
        except Exception:
            pass
    out = {"node": node.path(), "applied": applied}
    if readback:
        out["readback"] = readback
    if errors:
        out["errors"] = errors
    return out


# ── node_organize ─────────────────────────────────────────────────────────────────────────────────
# Built-in node-shape tokens on this build (verbatim from $HFS/houdini/config/NodeShapes/*.json).
# Data-only allowlist: node_organize sets it as the "nodeshape" user-data string; it is a cosmetic
# label, never code.
_NODE_SHAPES = (
    "bone", "bulge", "bulge_down", "burst", "camera", "chevron_down", "chevron_up", "cigar",
    "circle", "clipped_left", "clipped_right", "cloud", "cop", "cop2", "diamond", "ensign",
    "gurgle", "light", "null", "oval", "peanut", "pointy", "rect", "shop", "slash", "squared",
    "star", "subnet_input", "tabbed_left", "tabbed_right", "task", "tilted", "trapezoid_down",
    "trapezoid_up", "vop", "wave",
)


def _sanitize_node_name(raw):
    """Node-name safe subset: keep [A-Za-z0-9_], turn other chars into '_'. Houdini also enforces this
    (setName raises on illegal chars); we pre-clean so the rename is predictable. Display-only text is
    handled separately by _clean_text -- this is a NAME (identifier), never evaluated."""
    s = str(raw)
    out = []
    for ch in s:
        o = ord(ch)
        if (48 <= o <= 57) or (65 <= o <= 90) or (97 <= o <= 122) or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    name = "".join(out).strip("_")
    return name


@endpoint("node_organize")
def node_organize(params):
    """Cosmetic organization of ONE node (complements set_node_flags). Only SUPPLIED fields change:
      color   : NumVec[3] RGB, each clamped to 0..1 -> hou.Node.setColor(hou.Color((r,g,b)))
      shape   : str, an allowlisted built-in node-shape token -> setUserData("nodeshape", token)
      comment : str, DISPLAY-ONLY text (control chars stripped, capped 200) -> setComment(text);
                pass show_comment=true to also turn on the DisplayComment flag so it renders
      name    : str, rename (sanitized to a node identifier, made unique) -> setName(name, unique_name=True)
      position: NumVec[2] -> setPosition(hou.Vector2(x,y))
    `node` (required) is a resolved node path. Works headless (a node exists without a GUI). Text is
    never evaluated. Returns the applied fields with read-back."""
    node = resolve_node(params["node"])
    applied = {}

    if "color" in params:
        c = params["color"]
        if not isinstance(c, (list, tuple)) or len(c) != 3:
            raise ValueError("color must be an [r, g, b] list of 3 numbers in 0..1")
        try:
            rgb = tuple(clamp(float(x), 0.0, 1.0) for x in c)
        except (TypeError, ValueError):
            raise ValueError("color components must be numbers")
        try:
            node.setColor(hou.Color(rgb))
            applied["color"] = list(node.color().rgb())
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set color: %s" % exc)

    if "shape" in params:
        token = str(params["shape"]).strip().lower()
        if token not in _NODE_SHAPES:
            raise ValueError("shape must be one of %s" % list(_NODE_SHAPES))
        try:
            node.setUserData("nodeshape", token)
            applied["shape"] = node.userData("nodeshape")
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set shape: %s" % exc)

    if "comment" in params:
        text = _clean_text(params["comment"], cap=200)
        try:
            node.setComment(text)
            applied["comment"] = node.comment()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set comment: %s" % exc)
        if bool(params.get("show_comment", False)):
            nf = getattr(hou, "nodeFlag", None)
            flag = getattr(nf, "DisplayComment", None) if nf else None
            if flag is not None:
                try:
                    node.setGenericFlag(flag, True)
                    applied["show_comment"] = True
                except (hou.OperationFailed, AttributeError, TypeError) as exc:
                    applied["show_comment_note"] = "could not show comment: %s" % str(exc)[:80]

    if "name" in params:
        clean = _sanitize_node_name(params["name"])
        if not clean:
            raise ValueError("name is empty after sanitizing to a node identifier")
        try:
            node.setName(clean, unique_name=True)
            applied["name"] = node.name()
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot rename node: %s" % exc)

    if "position" in params:
        p = params["position"]
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("position must be an [x, y] list of 2 numbers")
        try:
            xy = (float(p[0]), float(p[1]))
        except (TypeError, ValueError):
            raise ValueError("position components must be numbers")
        try:
            node.setPosition(hou.Vector2(xy))
            applied["position"] = list(node.position())
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set position: %s" % exc)

    if not applied:
        raise ValueError("nothing to do: supply at least one of color / shape / comment / name / position")
    return {"node": node.path(), "applied": applied}


# ── viewport_appearance (THE INSPECTION-MODE TOOL) ───────────────────────────────────────────────
# GUI-only: drives the live GeometryViewport's settings + a display set so the AI can SEE geometry
# (display mode, point/prim markers-normals-numbers, backface removal) for the visual-acceptance loop.
_DISPLAY_SET_ALIASES = {
    "current_model": "CurrentModel", "display_model": "DisplayModel", "ghost_object": "GhostObject",
    "scene_object": "SceneObject", "selected_object": "SelectedObject", "template_model": "TemplateModel",
}
# friendly display-mode aliases -> real hou.glShadingType members (exact members also accepted live)
_SHADING_ALIASES = {
    "wireframe": "Wire", "wire": "Wire", "wire_ghost": "WireGhost", "wireghost": "WireGhost",
    "hidden_line_invisible": "HiddenLineInvisible", "hidden_line_ghost": "HiddenLineGhost",
    "flat": "Flat", "flat_shaded": "Flat", "flat_wire": "FlatWire", "flatwire": "FlatWire",
    "shaded": "Smooth", "smooth": "Smooth", "smooth_shaded": "Smooth",
    "wire_shaded": "SmoothWire", "smooth_wire": "SmoothWire", "smoothwire": "SmoothWire",
    "matcap": "MatCap", "matcap_wire": "MatCapWire",
    "wire_bounding_box": "WireBoundingBox", "bounding_box": "WireBoundingBox",
    "shaded_bounding_box": "ShadedBoundingBox",
}
# per-display-set marker/normal/number visualizers: param name -> GeometryViewportDisplaySet setter.
# Each takes a hou.markerVisibility member (Always | AroundPointer | Selected | UnderPointer). This
# build's markerVisibility has NO "off" token, so these switch the visualizer among ON modes; `true`
# is accepted as an alias for Always (full display -- the inspection default).
_VIS_SETTERS = {
    "point_markers": "setPointMarkerVisibility", "point_normals": "setPointNormalVisibility",
    "point_numbers": "setPointNumberVisibility", "prim_normals": "setPrimNormalVisibility",
    "prim_numbers": "setPrimNumberVisibility", "vertex_normals": "setVertexNormalVisibility",
    "vertex_numbers": "setVertexNumberVisibility",
}
# GeometryViewportSettings boolean toggles: param -> setter.
_GVS_BOOLS = {
    "textures": "setDisplayTextures", "ambient_occlusion": "setAmbientOcclusion",
    "ortho_grid": "setDisplayOrthoGrid", "hulls_only": "setHullsOnly",
    "xray": "setXrayDrawing", "remove_backfaces": "setRemoveBackfaces",
}


def _resolve_marker_visibility(value):
    """Caller value -> hou.markerVisibility member. `true` -> Always; a token resolves live. `false`
    is rejected with a clear message (this build's markerVisibility has no off state)."""
    if isinstance(value, bool):
        if value:
            return _resolve_enum("markerVisibility", "Always")
        raise ValueError("this build's hou.markerVisibility has no 'off' state; pass a mode token "
                         "(always | around_pointer | selected | under_pointer) or omit the param")
    return _resolve_enum("markerVisibility", value)


@endpoint("viewport_appearance")
def viewport_appearance(params):
    """Set typed GeometryViewport display/inspection settings so geometry is VISIBLE for the visual-
    acceptance loop. Only SUPPLIED params change. GUI-only (needs the live Scene Viewer).

    Display-set visualizers (applied to the display set named by `display_set`, default display_model):
      display_mode : enum -> setShadedMode(hou.glShadingType.<X>). Aliases: wireframe, wire_ghost,
                     hidden_line_invisible, hidden_line_ghost, flat, flat_wire, shaded/smooth,
                     wire_shaded (=SmoothWire), matcap, matcap_wire, wire_bounding_box,
                     shaded_bounding_box (exact glShadingType members also accepted).
      point_markers / point_normals / point_numbers / prim_normals / prim_numbers / vertex_normals /
      vertex_numbers : hou.markerVisibility token (always | around_pointer | selected | under_pointer),
                     or true (= always). No 'off' token exists on this build.
      boundary     : enum -> setBoundaryMode(hou.boundaryDisplay.<X>) (off | on | view3d | viewuv).
    Settings-level toggles (GeometryViewportSettings):
      remove_backfaces / textures / ambient_occlusion / ortho_grid / hulls_only / xray : bool
      color_scheme : enum (dark | dark_grey | grey | light) -> setColorScheme
      lighting     : enum (off | headlight | normal | high_quality | high_quality_with_shadows)
      headlight_intensity : float 0..10 -> setHeadlightIntensity
      display_set  : which display set the visualizers/display_mode target (default display_model).
    Returns the applied settings. No param accepts code/callables."""
    vp = _cur_viewport()
    try:
        st = vp.settings()
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot access viewport settings: %s" % exc)
    if st is None:
        raise ValueError("no viewport settings available")

    applied = {}

    # ---- settings-level boolean toggles ----
    for pname, setter in _GVS_BOOLS.items():
        if pname in params:
            fn = getattr(st, setter, None)
            if fn is None:
                raise ValueError("this build has no GeometryViewportSettings.%s" % setter)
            try:
                fn(bool(params[pname]))
                applied[pname] = bool(params[pname])
            except (hou.OperationFailed, AttributeError, TypeError) as exc:
                raise ValueError("cannot set %s: %s" % (pname, exc))

    # ---- settings-level enums ----
    if "color_scheme" in params:
        val, member = _resolve_enum("viewportColorScheme", params["color_scheme"])
        try:
            st.setColorScheme(val)
            applied["color_scheme"] = member
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set color_scheme: %s" % exc)

    if "lighting" in params:
        val, member = _resolve_enum("viewportLighting", params["lighting"])
        try:
            st.setLighting(val)
            applied["lighting"] = member
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set lighting: %s" % exc)

    if "headlight_intensity" in params:
        try:
            hi = clamp(float(params["headlight_intensity"]), 0.0, 10.0)
        except (TypeError, ValueError):
            raise ValueError("headlight_intensity must be a number")
        try:
            st.setHeadlightIntensity(hi)
            applied["headlight_intensity"] = hi
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot set headlight_intensity: %s" % exc)

    # ---- display-set-level visualizers (display mode + markers/normals/numbers + boundary) ----
    need_dset = ("display_mode" in params or "boundary" in params
                 or any(k in params for k in _VIS_SETTERS))
    if need_dset:
        _, ds_member = _resolve_enum("displaySetType",
                                     params.get("display_set", "display_model"),
                                     aliases=_DISPLAY_SET_ALIASES)
        try:
            dset = st.displaySet(getattr(hou.displaySetType, ds_member))
        except (hou.OperationFailed, AttributeError, TypeError) as exc:
            raise ValueError("cannot access display set %s: %s" % (ds_member, exc))
        if dset is None:
            raise ValueError("no display set %s on this viewport" % ds_member)
        applied["display_set"] = ds_member

        if "display_mode" in params:
            val, member = _resolve_enum("glShadingType", params["display_mode"],
                                        aliases=_SHADING_ALIASES)
            try:
                dset.setShadedMode(val)
                applied["display_mode"] = member
            except (hou.OperationFailed, AttributeError, TypeError) as exc:
                raise ValueError("cannot set display_mode: %s" % exc)

        for pname, setter in _VIS_SETTERS.items():
            if pname in params:
                vis, member = _resolve_marker_visibility(params[pname])
                fn = getattr(dset, setter, None)
                if fn is None:
                    raise ValueError("this build has no GeometryViewportDisplaySet.%s" % setter)
                try:
                    fn(vis)
                    applied[pname] = member
                except (hou.OperationFailed, AttributeError, TypeError) as exc:
                    raise ValueError("cannot set %s: %s" % (pname, exc))

        if "boundary" in params:
            val, member = _resolve_enum("boundaryDisplay", params["boundary"])
            fn = getattr(dset, "setBoundaryMode", None)
            if fn is None:
                raise ValueError("this build has no GeometryViewportDisplaySet.setBoundaryMode")
            try:
                fn(val)
                applied["boundary"] = member
            except (hou.OperationFailed, AttributeError, TypeError) as exc:
                raise ValueError("cannot set boundary: %s" % exc)

    if not applied or (list(applied.keys()) == ["display_set"]):
        raise ValueError("nothing to do: supply at least one display setting "
                         "(display_mode / point_normals / remove_backfaces / color_scheme / ...)")
    return {"applied": applied}


# ── viewport_layout ───────────────────────────────────────────────────────────────────────────────
_LAYOUT_ALIASES = {
    "single": "Single", "quad": "Quad", "double": "DoubleSide", "double_side": "DoubleSide",
    "double_stack": "DoubleStack", "triple": "TripleLeftSplit", "triple_left": "TripleLeftSplit",
    "triple_bottom": "TripleBottomSplit", "quad_left": "QuadLeftSplit", "quad_bottom": "QuadBottomSplit",
}


@endpoint("viewport_layout")
def viewport_layout(params):
    """Set the Scene Viewer's viewport LAYOUT (how the pane splits into viewports). GUI-only.
    `layout` (required) : enum -> hou.geometryViewportLayout. Aliases: single, quad, double
    (=DoubleSide), double_stack, triple (=TripleLeftSplit), triple_bottom, triple_left, quad_left,
    quad_bottom (exact members DoubleSide/DoubleStack/Quad/QuadBottomSplit/QuadLeftSplit/Single/
    TripleBottomSplit/TripleLeftSplit also accepted).
    `single` (optional int -1..3) : which viewport becomes the single/maximized one (-1 = default).
    Distinct from viewport_optimize (that tunes terrain draw). Returns the resulting layout token."""
    if "layout" not in params:
        raise ValueError("layout is required (a hou.geometryViewportLayout token)")
    sv = _scene_viewer()
    val, member = _resolve_enum("geometryViewportLayout", params["layout"], aliases=_LAYOUT_ALIASES)
    single = params.get("single", -1)
    try:
        single = int(single)
    except (TypeError, ValueError):
        raise ValueError("single must be an integer (-1..3)")
    single = int(clamp(single, -1, 3))
    try:
        sv.setViewportLayout(val, single)
    except (hou.OperationFailed, AttributeError, TypeError) as exc:
        raise ValueError("cannot set viewport layout: %s" % exc)
    out = {"layout": member, "single": single}
    try:
        out["layout_now"] = sv.viewportLayout().name()
    except Exception:
        pass
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Gated built-in actuation. Ruling: actuate a SideFX built-in by NAME only.
#
# Of the three scoped actuators, only `enter_state` ships, and it ships in its STRONGEST data-only
# form: an ENUM over the five FIXED built-in tool states, each mapping to a dedicated
# hou.SceneViewer.enter*State() method that takes NO argument. No caller string ever reaches HOM, so
# there is nothing to inject and no origin discriminator is needed -- security by construction, the
# same guarantee as every other typed tool here.
#
# NOT built (deliberately):
#   * run_shelf_tool -- NOT BUILT (decided against, permanently). There is NO typed HOM execute API for
#     a shelf tool; the only actuation path is exec(hou.Tool.script()) of its shipped Python, gated
#     solely by a filesystem-origin check. That reintroduces an exec() of a code string (the exact
#     mechanism the data-only moat forbids), secured by origin-trust rather than by construction -- so
#     it is excluded by decision. The "no arbitrary-code path anywhere" invariant stays absolute.
#   * radial_menu -- DROPPED. hou.RadialMenu has no show/invoke/trigger/popup API in 21.0.671; a radial
#     menu only fires from a live hotkey/gesture. There is no data-only "trigger built-in radial by
#     name" primitive, so it stays reference-only.
#
# HOM APIs used (all confirmed present on hou.SceneViewer, 21.0.671):
#   enterViewState / enterTranslateToolState / enterRotateToolState / enterScaleToolState /
#   enterCurrentNodeState  (each takes no arg)  ·  currentState() (read-back)
# ═════════════════════════════════════════════════════════════════════════════════════════════════

# state token -> the fixed, no-argument hou.SceneViewer method that enters that built-in tool state.
# Deliberately a closed map to dedicated methods: no name string is ever passed to HOM (no
# setCurrentState(name) path here), so a caller cannot name an arbitrary/user-registered state.
_FIXED_VIEWER_STATES = {
    "view": "enterViewState",
    "translate": "enterTranslateToolState",
    "rotate": "enterRotateToolState",
    "scale": "enterScaleToolState",
    "current_node": "enterCurrentNodeState",
}


@endpoint("enter_state")
def enter_state(params):
    """Enter one of the FIVE fixed built-in Scene Viewer tool states (data-only, by construction).
    `state` (required, enum): view (the plain look-around view state) | translate | rotate | scale
    (the three transform-handle tool states) | current_node (the current node's own tool state).
    Each maps to a dedicated no-argument hou.SceneViewer.enter*State() method -- no name string is
    ever passed to HOM, so there is no way to name an arbitrary or user-registered (code-backed) state.
    GUI-only (needs a live Scene Viewer; raises a clear error headless). Returns the state entered and,
    where available, the viewer's current-state name read back."""
    state = str(params.get("state", "")).lower()
    if state not in _FIXED_VIEWER_STATES:
        raise ValueError("state must be one of %s" % sorted(_FIXED_VIEWER_STATES))
    sv = _scene_viewer()
    method = _FIXED_VIEWER_STATES[state]
    fn = getattr(sv, method, None)
    if fn is None:
        raise ValueError("this build has no hou.SceneViewer.%s" % method)
    try:
        fn()
    except (hou.OperationFailed, hou.OperationInterrupted, AttributeError, TypeError) as exc:
        raise ValueError("cannot enter %s state: %s" % (state, exc))
    out = {"entered": state}
    try:
        out["current_state"] = sv.currentState()
    except Exception:
        pass
    return out
