"""Populate the node reference with a synthetic "Labs" category in ONE pass -- live-probed
params/types/menu-tokens (hython) enriched with descriptions from the offline SideFX Labs help
(help/nodes/<ctx>/labs--<name>-<ver>.txt), mirroring how the Cop lane was added.

RUN UNDER HYTHON (needs hou):
  "<HFS>\\bin\\hython.exe" scripts/import_labs_docs.py            # dry-run: report only
  "<HFS>\\bin\\hython.exe" scripts/import_labs_docs.py --write     # merge into houdini_nodes.json

Only a synthetic `Labs` category is added/updated (categories.Labs + node_types.Labs +
params[<full versioned type>]); existing categories are untouched. Labs types are namespaced
(labs::...) so collisions are unlikely, but the same collision-safe guard as the Cop lane is kept.
"""
import os, sys, re, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODES_JSON = os.path.join(REPO, "reference", "houdini_nodes.json")
HELP_ROOT = r"C:\Program Files\Side Effects Software\sidefx_packages\SideFXLabs21.0\help\nodes"

import hou  # noqa: E402

# hou category name -> help ctx dir (primary); 'other'/'shop' + all dirs are fallbacks.
CAT_CTX = {
    "Sop": "sop", "Object": "obj", "Dop": "dop", "Cop2": "cop2", "Lop": "lop",
    "Top": "top", "Vop": "vop", "Rop": "out", "Chop": "chop",
}

CATS = {
    "Sop": hou.sopNodeTypeCategory(), "Object": hou.objNodeTypeCategory(),
    "Dop": hou.dopNodeTypeCategory(), "Cop2": hou.cop2NodeTypeCategory(),
    "Lop": hou.lopNodeTypeCategory(), "Top": hou.topNodeTypeCategory(),
    "Rop": hou.ropNodeTypeCategory(), "Vop": hou.vopNodeTypeCategory(),
    "Chop": hou.chopNodeTypeCategory(),
}

_PT = {
    hou.parmTemplateType.Float: "float", hou.parmTemplateType.Int: "int",
    hou.parmTemplateType.String: "string", hou.parmTemplateType.Toggle: "toggle",
    hou.parmTemplateType.Menu: "menu", hou.parmTemplateType.Ramp: "ramp",
    hou.parmTemplateType.Button: "button", hou.parmTemplateType.Separator: "sep",
    hou.parmTemplateType.FolderSet: "folderset", hou.parmTemplateType.Folder: "folder",
}


# ---- 1. parse Labs help: help/nodes/<ctx>/labs--*.txt --------------------------------------------
# Two @parameters styles occur: '#id:'-keyed (e.g. cylinder_generator) and label-only (e.g. cop2
# normal_map). Capture BOTH so descriptions can be matched by parm id OR by parm label.
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
        # a plain descriptive line: attach to whatever id/label is currently open
        if s.startswith("#"):
            continue
        if cur_id is not None and not by_id.get(cur_id):
            by_id[cur_id] = s[:200]
        if cur_label is not None and not by_label.get(cur_label.lower()):
            by_label[cur_label.lower()] = s[:200]
    return {"summary": summary, "by_id": by_id, "by_label": by_label}


def parse_help():
    """Return docs[ctx][stem] = parsed doc, plus the list of ctx dirs present."""
    docs, ctxs = {}, []
    if not os.path.isdir(HELP_ROOT):
        sys.exit("Labs help dir not found: %s" % HELP_ROOT)
    for ctx in sorted(os.listdir(HELP_ROOT)):
        cdir = os.path.join(HELP_ROOT, ctx)
        if not os.path.isdir(cdir):
            continue
        ctxs.append(ctx)
        for fn in os.listdir(cdir):
            if not (fn.startswith("labs--") and fn.endswith(".txt")):
                continue
            stem = fn[:-4]
            txt = open(os.path.join(cdir, fn), encoding="utf-8", errors="replace").read().splitlines()
            docs.setdefault(ctx, {})[stem] = _parse_file(txt)
    return docs, ctxs


def lookup_doc(docs, ctxs, cat, name, ver):
    """Find the best help doc for a type, preferring the category's ctx, then any ctx."""
    stems = []
    if ver:
        stems.append("labs--%s-%s" % (name, ver))
    stems.append("labs--%s" % name)
    primary = CAT_CTX.get(cat)
    order = ([primary] if primary else []) + ["other", "shop"] + ctxs
    seen = set()
    for ctx in order:
        if ctx in seen or ctx not in docs:
            continue
        seen.add(ctx)
        for stem in stems:
            if stem in docs[ctx]:
                return docs[ctx][stem]
    return None


# ---- 2. container per category (Cop2 fix: cop2net under /obj; gaea fix: load_contents fallback) --
def make_container(cat_name):
    obj = hou.node("/obj")
    try:
        if cat_name == "Sop":
            return obj.createNode("geo", "_labs_sop")
        if cat_name == "Object":
            return obj
        if cat_name == "Dop":
            return obj.createNode("dopnet", "_labs_dop")
        if cat_name == "Cop2":
            return obj.createNode("cop2net", "_labs_cop2")   # cop2net (NOT copnet), under /obj
        if cat_name == "Lop":
            return obj.createNode("lopnet", "_labs_lop")
        if cat_name == "Top":
            return obj.createNode("topnet", "_labs_top")
        if cat_name == "Rop":
            return obj.createNode("ropnet", "_labs_rop")
        if cat_name == "Vop":
            return obj.createNode("matnet", "_labs_vop")
        if cat_name == "Chop":
            return obj.createNode("chopnet", "_labs_chop")
    except Exception as e:  # noqa: BLE001
        print("  container FAIL %s: %s" % (cat_name, str(e)[:80]))
    return None


def _create(cont, tname):
    """Create a node, retrying with load_contents=False for defs whose subnet fails to match."""
    try:
        return cont.createNode(tname, "_p")
    except hou.Error:
        return cont.createNode(tname, "_p", load_contents=False)


# ---- 3. probe every Labs type across categories, enrich with help ------------------------------
def probe(docs, ctxs):
    names, params, errors, cat_counts = [], {}, {}, {}
    n_desc = n_menu = 0
    no_help = []
    for cat_name, cat in CATS.items():
        labs = [t for t in sorted(cat.nodeTypes().keys())
                if t.lower().startswith("labs::") or t.lower().startswith("labs_")]
        if not labs:
            continue
        cat_counts[cat_name] = len(labs)
        cont = make_container(cat_name)
        if cont is None:
            for t in labs:
                errors[t] = "no container for category %s" % cat_name
            continue
        for tname in labs:
            try:
                n = _create(cont, tname)
            except Exception as e:  # noqa: BLE001
                errors[tname] = str(e).splitlines()[0][:140]
                continue
            comps = n.type().nameComponents()   # (scope, namespace, name, version)
            nm, ver = comps[2], comps[3]
            doc = lookup_doc(docs, ctxs, cat_name, nm, ver)
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
            names.append(tname)
            try:
                n.destroy()
            except Exception:
                pass
    names.sort()
    return names, params, errors, cat_counts, n_desc, n_menu, no_help


def main():
    write = "--write" in sys.argv
    docs, ctxs = parse_help()
    n_help = sum(len(v) for v in docs.values())
    names, params, errors, cat_counts, n_desc, n_menu, no_help = probe(docs, ctxs)

    print("Labs help files parsed :", n_help, "across ctx:", ctxs)
    print("Labs types by category :", cat_counts, "= %d total" % sum(cat_counts.values()))
    print("Labs types probed OK   :", len(names))
    print("Labs types errored     :", len(errors))
    for t, e in sorted(errors.items()):
        print("   ERR %s :: %s" % (t, e))
    print("param sets built       :", len(params))
    print("params with help desc  :", n_desc)
    print("params with menu tokens:", n_menu)
    print("types with NO help file:", len(no_help))
    if no_help:
        print("   ", ", ".join(sorted(no_help)))

    data = json.load(open(NODES_JSON, encoding="utf-8"))
    before_types = len(data["node_types"])
    before_params = len(data["params"])
    before_size = os.path.getsize(NODES_JSON) / 1048576

    if not write:
        print("\nDRY-RUN (no file written). Re-run with --write to merge.")
        print("would set categories.Labs =", len(names))
        print("would add node_types.Labs (list of %d) + %d param sets" % (len(names), len(params)))
        print("sample:", names[:6])
        return

    data["categories"]["Labs"] = len(names)
    data["node_types"]["Labs"] = names

    # Labs keys are fully namespaced (labs::name::ver) -> the key ALWAYS denotes the same node
    # regardless of which category also lists it. Any existing param set under that exact key is a
    # thinner (name+type only) version of the SAME node from an earlier generic probe, so the
    # enriched Labs entry (adds desc + menu tokens) should WIN the canonical key. We overwrite
    # unconditionally, but guard the pathological case of a NON-namespaced key (should never occur
    # here) by refusing to touch any key that doesn't start with the labs namespace.
    existing = data["params"]
    enriched, added, skipped = 0, 0, []
    for name, plist in params.items():
        if not name.lower().startswith("labs::"):
            skipped.append(name)          # non-namespaced -> would be unsafe to clobber; skip
            continue
        if name in existing:
            enriched += 1
        else:
            added += 1
        existing[name] = plist
    print("merge: %d canonical labs keys enriched (overwrote thinner prior entry), %d new" %
          (enriched, added))
    if skipped:
        print("SKIPPED non-namespaced keys (left untouched): %s" % ", ".join(sorted(skipped)))

    data["note"] = data.get("note", "") + " | Labs lane added from live probe + Labs help."
    bak = NODES_JSON + ".bak_prelabs"
    if not os.path.exists(bak):
        json.dump(json.load(open(NODES_JSON, encoding="utf-8")),
                  open(bak, "w", encoding="utf-8"))
    json.dump(data, open(NODES_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    after_size = os.path.getsize(NODES_JSON) / 1048576
    print("\nWROTE %s" % NODES_JSON)
    print("  node_types: %d -> %d ; params: %d -> %d ; size: %.2f -> %.2f MB" % (
        before_types, len(data["node_types"]), before_params, len(data["params"]),
        before_size, after_size))


if __name__ == "__main__":
    main()
