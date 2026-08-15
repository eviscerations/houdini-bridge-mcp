"""Populate the node reference with the Copernicus (Cop) lane in ONE pass — live-probed params/types
(hython) enriched with descriptions from the offline SideFX help (nodes.zip -> cop/<node>.txt).

RUN UNDER HYTHON (needs hou):
  "<HFS>\\bin\\hython.exe" scripts/import_cop_docs.py            # dry-run: report only
  "<HFS>\\bin\\hython.exe" scripts/import_cop_docs.py --write     # merge into houdini_nodes.json

Only the `Cop` category is added/updated; existing categories are untouched. Reusable: the same
pattern (probe a category + enrich from nodes.zip) can refresh any lane later.
"""
import os, sys, re, json, zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODES_JSON = os.path.join(REPO, "reference", "houdini_nodes.json")
HFS = r"C:\Program Files\Side Effects Software\Houdini21.0.671"
NODES_ZIP = os.path.join(HFS, "houdini", "help", "nodes.zip")

import hou  # noqa: E402


# ---- 1. parse help: cop/<node>.txt -> {summary, {parm_id: desc}} ------------------------------
def parse_help():
    zf = zipfile.ZipFile(NODES_ZIP)
    docs = {}
    for entry in zf.namelist():
        if not (entry.startswith("cop/") and entry.endswith(".txt")):
            continue
        name = entry[len("cop/"):-4]
        txt = zf.read(entry).decode("utf-8", "replace").splitlines()
        summary, params, sec, pending_id = "", {}, None, None
        for l in txt:
            s = l.strip()
            m = re.match(r'\s*"""(.*)"""', l)
            if m and not summary:
                summary = m.group(1).strip()
            if s.startswith("@parameters"):
                sec = "p"; continue
            if s.startswith("@"):
                sec = None; pending_id = None; continue
            if sec != "p":
                continue
            mid = re.search(r"#id:\s*(\S+)", l)
            if mid:
                pending_id = mid.group(1)
                params.setdefault(pending_id, "")
            elif pending_id and s and not s.startswith("#") and not params[pending_id]:
                params[pending_id] = s[:200]   # first descriptive line
        docs[name] = {"summary": summary, "params": params}
    return docs


# ---- 2. live-probe each Cop node type: real param names + types (+ menu tokens) ----------------
_PT = {
    hou.parmTemplateType.Float: "float", hou.parmTemplateType.Int: "int",
    hou.parmTemplateType.String: "string", hou.parmTemplateType.Toggle: "toggle",
    hou.parmTemplateType.Menu: "menu", hou.parmTemplateType.Ramp: "ramp",
    hou.parmTemplateType.Button: "button", hou.parmTemplateType.Separator: "sep",
    hou.parmTemplateType.FolderSet: "folderset", hou.parmTemplateType.Folder: "folder",
}


def probe_cop_types(help_docs):
    cat = hou.nodeTypeCategories().get("Cop")
    if cat is None:
        sys.exit("Cop category not present on this build")
    net = hou.node("/obj").createNode("copnet", "ref_probe")
    names, params = [], {}
    for tname in sorted(cat.nodeTypes().keys()):
        try:
            n = net.createNode(tname)
        except Exception:
            continue
        names.append(tname)
        hd = help_docs.get(tname, {}).get("params", {})
        plist = []
        seen = set()
        for p in n.parms():
            pt = p.parmTemplate()
            base = p.name()
            # collapse tuple components (tx/ty/tz -> t) to the tuple name when present
            tup = p.tuple()
            key = tup.name() if tup is not None and len(tup) > 1 else base
            if key in seen:
                continue
            seen.add(key)
            typ = _PT.get(pt.type(), str(pt.type()).split(".")[-1].lower())
            entry = {"name": key, "type": typ}
            if pt.type() == hou.parmTemplateType.Menu:
                try:
                    entry["menu"] = list(pt.menuItems())[:32]
                except Exception:
                    pass
            desc = hd.get(key) or hd.get(base)
            if desc:
                entry["desc"] = desc
            plist.append(entry)
        params[tname] = plist
        try:
            n.destroy()
        except Exception:
            pass
    net.destroy()
    return names, params


def main():
    write = "--write" in sys.argv
    help_docs = parse_help()
    names, params = probe_cop_types(help_docs)
    print("cop help files parsed :", len(help_docs))
    print("cop node types probed :", len(names))
    print("param sets built      :", len(params))
    with_desc = sum(1 for plist in params.values() for e in plist if e.get("desc"))
    print("params with help desc :", with_desc)

    data = json.load(open(NODES_JSON, encoding="utf-8"))
    before_types = len(data["node_types"])
    before_params = len(data["params"])
    if not write:
        print("\nDRY-RUN (no file written). Re-run with --write to merge.")
        print("would set categories.Cop =", len(names))
        print("would add node_types.Cop (list of %d) + %d param sets" % (len(names), len(params)))
        print("sample:", names[:8])
        return
    data["categories"]["Cop"] = len(names)
    data["node_types"]["Cop"] = names

    # Collision-safe merge: if a Cop node name is ALSO claimed by a non-Cop category,
    # writing the Cop params under the plain name would clobber the (more complete)
    # non-Cop entry (this is exactly the xform/bend/resample/sopimport regression).
    # For those, write the Cop params under "<name> (Cop)" instead; the plain name
    # stays the non-Cop version. Idempotent: re-running lands the same keys and never
    # double-suffixes (we key off the CURRENT node_types map, not on the prior write).
    noncop_names = set()
    for cat, lst in data["node_types"].items():
        if cat == "Cop":
            continue
        noncop_names.update(lst)
    existing = data["params"]
    collisions = []
    for name, plist in params.items():
        if name in noncop_names and name in existing:
            existing[name + " (Cop)"] = plist   # preserve Cop under suffixed key
            collisions.append(name)
        else:
            existing[name] = plist               # non-colliding: plain name as before
    if collisions:
        print("collision-safe: wrote %d Cop set(s) under '<name> (Cop)': %s" % (
            len(collisions), ", ".join(sorted(collisions))))
    data["note"] = data.get("note", "") + " | Cop lane added from live probe + nodes.zip help."
    bak = NODES_JSON + ".bak_precop"
    if not os.path.exists(bak):
        json.dump(json.load(open(NODES_JSON, encoding="utf-8")), open(bak, "w", encoding="utf-8"))
    json.dump(data, open(NODES_JSON, "w", encoding="utf-8"), indent=1)
    print("\nWROTE %s" % NODES_JSON)
    print("  node_types: %d -> %d ; params: %d -> %d" % (
        before_types, len(data["node_types"]), before_params, len(data["params"])))


if __name__ == "__main__":
    main()
