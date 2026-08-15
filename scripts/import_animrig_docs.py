"""Populate the node reference for the animation+rigging finish-out lanes — Crowd + Muscle (new
synthetic categories) and the new KineFX types (classic bone rigs, auto/mocap/deform rigs, KineFX
rig-constraint SOPs, channel-anim CHOPs) — plus the otheranim_1 DOP dynamics-constraint nodes (added
under their native `Dop` category). Live-probed params/types/menu-tokens (hython) enriched with
descriptions from the offline built-in Houdini help (help/nodes.zip -> {obj,sop,dop,chop,vop,out}/
<stem>.txt), mirroring import_kinefx_docs.py / the Cop / Labs lanes.

Unlike the KineFX importer (SOP-container only), these lanes span multiple Houdini contexts, so each
type is created in the correct container (Object -> /obj, Sop -> a geo, Dop -> a dopnet, Chop -> a
chopnet, Vop -> an attribvop inside a geo, Driver -> /out), with a fallback that tries the other
containers if the hint is wrong. Help is looked up in the matching subdir.

RUN UNDER HYTHON (needs hou):
  "<HFS>\\bin\\hython.exe" scripts/import_animrig_docs.py            # dry-run: report only
  "<HFS>\\bin\\hython.exe" scripts/import_animrig_docs.py --write     # merge into houdini_nodes.json

LAST integration step and intentionally NON-FATAL: types that cannot be instantiated headlessly, or
whose help file is absent, are logged and skipped; nothing here blocks the rest of the integration.
The pre-existing houdini_nodes.json is backed up to .bak_preanimrig before the first write.
"""
import os
import sys
import re
import json
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODES_JSON = os.path.join(REPO, "reference", "houdini_nodes.json")
TOOL_NODES = os.path.join(REPO, "reference", "tool_nodes.json")
CATALOG = os.path.join(REPO, "reference", "catalog.json")
HELP_ZIP = r"C:\Program Files\Side Effects Software\Houdini21.0.671\houdini\help\nodes.zip"

import hou  # noqa: E402

# display-category -> synthetic node_types bucket (Solvers dynamics land in native Dop).
NEW_HANDLERS = ["classic_1", "classic_2", "classic_3", "classic_4",
                "crowd_1", "crowd_2", "crowd_3", "crowd_4", "crowd_5", "crowd_6",
                "muscle_1", "muscle_2", "otheranim_1",
                "otheranim_ar1", "otheranim_ar2", "otheranim_ar3",
                "chop_anim_1", "chop_anim_2"]

_PT = {
    hou.parmTemplateType.Float: "float", hou.parmTemplateType.Int: "int",
    hou.parmTemplateType.String: "string", hou.parmTemplateType.Toggle: "toggle",
    hou.parmTemplateType.Menu: "menu", hou.parmTemplateType.Ramp: "ramp",
    hou.parmTemplateType.Button: "button", hou.parmTemplateType.Separator: "sep",
    hou.parmTemplateType.FolderSet: "folderset", hou.parmTemplateType.Folder: "folder",
}

_LABEL_RE = re.compile(r"^\s+([^#=\s].*?):\s*$")
_ID_RE = re.compile(r"#id:\s*(\S+)")


def _parse_file(lines):
    summary, by_id, by_label = "", {}, {}
    sec = None
    cur_label = cur_id = None
    for l in lines:
        s = l.strip()
        m = re.match(r'\s*"""(.*)"""', l)
        if m and not summary:
            summary = m.group(1).strip()
        if s.startswith("@parameters"):
            sec = "p"; cur_label = cur_id = None; continue
        if s.startswith("@"):
            sec = None; cur_label = cur_id = None; continue
        if sec != "p":
            continue
        if s.startswith("==") or not s:
            continue
        mid = _ID_RE.search(l)
        if mid:
            cur_id = mid.group(1)
            by_id.setdefault(cur_id, "")
            continue
        ml = _LABEL_RE.match(l)
        if ml and not l.lstrip().startswith("#"):
            cur_label = ml.group(1).strip()
            cur_id = None
            by_label.setdefault(cur_label.lower(), "")
            continue
        if s.startswith("#"):
            continue
        if cur_id is not None and not by_id.get(cur_id):
            by_id[cur_id] = s[:200]
        if cur_label is not None and not by_label.get(cur_label.lower()):
            by_label[cur_label.lower()] = s[:200]
    return {"summary": summary, "by_id": by_id, "by_label": by_label}


HELP_SUBDIRS = ("obj", "sop", "dop", "chop", "vop", "out", "lop")


def parse_help():
    if not os.path.isfile(HELP_ZIP):
        return {}, False
    docs = {sd: {} for sd in HELP_SUBDIRS}
    with zipfile.ZipFile(HELP_ZIP) as z:
        for entry in z.namelist():
            sd = entry.split("/")[0]
            if sd not in docs or not entry.endswith(".txt"):
                continue
            stem = entry[len(sd) + 1:-4]
            try:
                txt = z.read(entry).decode("utf-8", "replace").splitlines()
            except Exception:  # noqa: BLE001
                continue
            docs[sd][stem] = _parse_file(txt)
    return docs, True


def stems_for(namespace, name, version):
    out = []
    ns = (namespace + "--") if namespace else ""
    if version:
        out.append("%s%s-%s" % (ns, name, version))
    out.append("%s%s" % (ns, name))
    return out


def lookup_doc(docs_sd, namespace, name, version):
    for stem in stems_for(namespace, name, version):
        if stem in docs_sd:
            return docs_sd[stem]
    return None


# ---- type -> (target group, hou category hint) ------------------------------------------------
def build_type_index():
    """type -> {"group": KineFX|Crowd|Muscle|Dop, "hint": Object|Sop|Dop|Chop|Vop|Driver}."""
    tn = json.load(open(TOOL_NODES, encoding="utf-8"))["tools"]
    cat = json.load(open(CATALOG, encoding="utf-8"))["tools"]
    disp = {t["name"]: t["category"] for t in cat}
    side = {}
    # side table (per-type hou hint), optional — looked up next to $TEMP if present.
    p = os.path.join(os.environ.get("TEMP", ""), "type_houcat.json")
    if os.path.isfile(p):
        side = json.load(open(p, encoding="utf-8"))
    # which tools are ours
    import ast
    ours = set()
    for h in NEW_HANDLERS:
        src = open(os.path.join(REPO, "houdini_executor", "handlers", h + ".py"), encoding="utf-8").read()
        for m in re.findall(r'@endpoint\("([^"]+)"', src):
            ours.add(m)
    GROUP = {"KineFX": "KineFX", "Crowd": "Crowd", "Muscle": "Muscle",
             "Solvers & simulation": "Dop"}
    idx = {}
    for tool in ours:
        grp = GROUP.get(disp.get(tool))
        if grp is None:
            continue
        for nt in tn.get(tool, {}).get("nodes", []):
            idx.setdefault(nt, {"group": grp, "hint": side.get(nt)})
    return idx


# ---- containers -------------------------------------------------------------------------------
def make_containers():
    obj = hou.node("/obj")
    geo = obj.createNode("geo", "_ar_geo")
    dopnet = obj.createNode("dopnet", "_ar_dop")
    chopnet = obj.createNode("chopnet", "_ar_chop")
    out = hou.node("/out")
    try:
        avop = geo.createNode("attribvop", "_ar_vop")
    except Exception:  # noqa: BLE001
        avop = None
    try:
        lopnet = obj.createNode("lopnet", "_ar_lop")
    except Exception:  # noqa: BLE001
        lopnet = hou.node("/stage")
    return {"Object": obj, "Sop": geo, "Dop": dopnet, "Chop": chopnet, "Driver": out,
            "Vop": avop, "Lop": lopnet}


HINT_ORDER = ["Object", "Sop", "Dop", "Chop", "Vop", "Driver", "Lop"]
CAT_TO_HELP = {"Object": "obj", "Sop": "sop", "Dop": "dop", "Chop": "chop", "Vop": "vop",
               "Driver": "out", "Lop": "lop"}


def try_create(conts, tname, hint):
    order = ([hint] if hint in conts else []) + [c for c in HINT_ORDER if c != hint]
    last = None
    for cat in order:
        cont = conts.get(cat)
        if cont is None:
            continue
        try:
            n = cont.createNode(tname, "_p")
            return n, cat
        except hou.Error as e:
            last = str(e).splitlines()[0][:140]
            try:
                n = cont.createNode(tname, "_p", load_contents=False)
                return n, cat
            except Exception as e2:  # noqa: BLE001
                last = str(e2).splitlines()[0][:140]
    return None, last


def probe(docs, idx):
    conts = make_containers()
    params, errors, worked_cat = {}, {}, {}
    n_desc = n_menu = 0
    no_help = []
    for tname in sorted(idx):
        n, cat_or_err = try_create(conts, tname, idx[tname]["hint"])
        if n is None:
            errors[tname] = cat_or_err or "createNode failed"
            continue
        worked_cat[tname] = cat_or_err
        comps = n.type().nameComponents()
        namespace, nm, ver = comps[1], comps[2], comps[3]
        docs_sd = docs.get(CAT_TO_HELP.get(cat_or_err, "sop"), {}) if docs else {}
        doc = lookup_doc(docs_sd, namespace, nm, ver) if docs else None
        if doc is None:
            no_help.append(tname)
        by_id = doc["by_id"] if doc else {}
        by_label = doc["by_label"] if doc else {}
        plist, seen = [], set()
        for p in n.parms():
            pt = p.parmTemplate()
            base = p.name()
            tup = p.tuple()
            key = tup.name() if tup is not None and len(tup) > 1 else base
            if key in seen:
                continue
            seen.add(key)
            typ = _PT.get(pt.type(), str(pt.type()).split(".")[-1].lower())
            entry = {"name": key, "type": typ}
            if pt.type() == hou.parmTemplateType.Menu:
                try:
                    mi = list(pt.menuItems())[:32]
                    if mi:
                        entry["menu"] = mi
                        n_menu += 1
                except Exception:
                    pass
            lbl = ""
            try:
                lbl = pt.label() or ""
            except Exception:
                pass
            desc = by_id.get(key) or by_id.get(base) or by_label.get(lbl.strip().lower())
            if desc:
                entry["desc"] = desc
                n_desc += 1
            plist.append(entry)
        params[tname] = plist
        try:
            n.destroy()
        except Exception:
            pass
    return params, errors, worked_cat, n_desc, n_menu, no_help


def main():
    write = "--write" in sys.argv
    idx = build_type_index()
    docs, help_found = parse_help()
    if not help_found:
        print("NOTE: built-in help zip not found at %s — probing params/menus WITHOUT help "
              "descriptions (non-fatal)." % HELP_ZIP)
    params, errors, worked_cat, n_desc, n_menu, no_help = probe(docs, idx)

    print("types to import (KineFX/Crowd/Muscle/Dop):", len(idx))
    print("probed OK        :", len(params))
    print("errored (skipped):", len(errors))
    for t, e in sorted(errors.items()):
        print("   ERR %s :: %s" % (t, e))
    print("params w/ help desc:", n_desc, " params w/ menu:", n_menu)
    print("types with NO help file:", len(no_help))

    # group the successfully probed types
    by_group = {"KineFX": [], "Crowd": [], "Muscle": [], "Dop": []}
    for t in params:
        by_group[idx[t]["group"]].append(t)
    for g in by_group:
        by_group[g].sort()
    print("by group:", {g: len(v) for g, v in by_group.items()})

    if not write:
        print("\nDRY-RUN (no file written). Re-run with --write to merge.")
        return

    data = json.load(open(NODES_JSON, encoding="utf-8"))
    bak = NODES_JSON + ".bak_preanimrig"
    if not os.path.exists(bak):
        json.dump(json.load(open(NODES_JSON, encoding="utf-8")), open(bak, "w", encoding="utf-8"))
        print("backed up ->", bak)

    before_types = len(data["node_types"])
    before_params = len(data["params"])

    def merge_category(catname, types):
        cur = set(data["node_types"].get(catname, []))
        cur.update(types)
        data["node_types"][catname] = sorted(cur)
        data["categories"][catname] = len(cur)

    merge_category("KineFX", by_group["KineFX"])
    merge_category("Crowd", by_group["Crowd"])
    merge_category("Muscle", by_group["Muscle"])
    merge_category("Dop", by_group["Dop"])  # native category, extended

    existing = data["params"]
    enriched = added = kept_bare = 0
    for name, plist in params.items():
        namespaced = "::" in name or name.lower().startswith(("kinefx::", "labs::"))
        if namespaced:
            if name in existing:
                enriched += 1
            else:
                added += 1
            existing[name] = plist
        else:
            if name in existing:
                kept_bare += 1
            else:
                existing[name] = plist
                added += 1
    print("merge: %d namespaced (re)written, %d new keys, %d bare kept" % (enriched, added, kept_bare))

    data["note"] = data.get("note", "") + " | Crowd/Muscle/anim-rig lanes added from live probe + built-in help."
    json.dump(data, open(NODES_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("\nWROTE %s" % NODES_JSON)
    print("  node_types: %d -> %d ; params: %d -> %d" % (
        before_types, len(data["node_types"]), before_params, len(data["params"])))


if __name__ == "__main__":
    main()
