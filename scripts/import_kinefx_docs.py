"""Populate the node reference with a synthetic "KineFX" category in ONE pass -- live-probed
params/types/menu-tokens (hython) enriched with descriptions from the offline built-in Houdini
help (help/nodes.zip -> sop/<stem>.txt), mirroring how the Cop and Labs lanes were added.

RUN UNDER HYTHON (needs hou):
  "<HFS>\\bin\\hython.exe" scripts/import_kinefx_docs.py            # dry-run: report only
  "<HFS>\\bin\\hython.exe" scripts/import_kinefx_docs.py --write     # merge into houdini_nodes.json

Only a synthetic `KineFX` category is added/updated (categories.KineFX + node_types.KineFX +
params[<type>] for the namespaced kinefx::/labs:: keys). The KineFX lane is an EXPLICIT ALLOWLIST of
the exact versioned type strings the six KineFX handlers create (the union of every wave's
INTEGRATION §c list), imported from tag_kinefx_category.ALLOWLIST — a mix of `kinefx::…`, bare SOP
types (`capture`, `deform`, `cregion`, `blendshapes::2.0`, …) and two `labs::` skinning-converters.

KEY-SAFETY (matches the Cop/Labs lanes): `node_reference(node=<type>)` looks a param set up by the
exact type string. Bare KineFX types (`deform`, `capture`, …) ALREADY have a correct generic-SOP
param entry under that same bare key (it is the SAME node), so this script NEVER overwrites a bare
key — it only ADDS a bare key when it is somehow missing, and it (re)writes the namespaced
`kinefx::` / `labs::` keys (safe: a fully-namespaced key denotes exactly one node). The KineFX
category listing (node_types.KineFX) still enumerates ALL probed types so
`node_reference(category="KineFX")` lists the whole lane.

Node-ref is the LAST integration step and is intentionally NON-FATAL: if the built-in help zip
cannot be located the probe still runs (params/menus, just no help descriptions) and the category is
still written; nothing here blocks the rest of the integration.
"""
import os
import sys
import re
import json
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODES_JSON = os.path.join(REPO, "reference", "houdini_nodes.json")
sys.path.insert(0, os.path.join(REPO, "scripts"))
from tag_kinefx_category import ALLOWLIST  # noqa: E402  (single source of truth)

# The built-in node help ships zipped; KineFX/character/capture/deform help lives under sop/.
HELP_ZIP = r"C:\Program Files\Side Effects Software\Houdini21.0.671\houdini\help\nodes.zip"

import hou  # noqa: E402

_PT = {
    hou.parmTemplateType.Float: "float", hou.parmTemplateType.Int: "int",
    hou.parmTemplateType.String: "string", hou.parmTemplateType.Toggle: "toggle",
    hou.parmTemplateType.Menu: "menu", hou.parmTemplateType.Ramp: "ramp",
    hou.parmTemplateType.Button: "button", hou.parmTemplateType.Separator: "sep",
    hou.parmTemplateType.FolderSet: "folderset", hou.parmTemplateType.Folder: "folder",
}

# ---- 1. parse built-in help txt (same @parameters grammar as the Labs/Cop lanes) --------------
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


def parse_help():
    """Return docs[stem] = parsed doc for every sop/<stem>.txt in the built-in nodes help zip.
    Non-fatal: returns ({}, False) if the zip is absent."""
    if not os.path.isfile(HELP_ZIP):
        return {}, False
    docs = {}
    with zipfile.ZipFile(HELP_ZIP) as z:
        for entry in z.namelist():
            if not (entry.startswith("sop/") and entry.endswith(".txt")):
                continue
            stem = entry[len("sop/"):-4]
            try:
                txt = z.read(entry).decode("utf-8", "replace").splitlines()
            except Exception:  # noqa: BLE001
                continue
            docs[stem] = _parse_file(txt)
    return docs, True


def stems_for(namespace, name, version):
    """Help-file stem candidates for a type, most specific first (sop/<stem>.txt)."""
    out = []
    ns = (namespace + "--") if namespace else ""
    if version:
        out.append("%s%s-%s" % (ns, name, version))
    out.append("%s%s" % (ns, name))
    return out


def lookup_doc(docs, namespace, name, version):
    for stem in stems_for(namespace, name, version):
        if stem in docs:
            return docs[stem]
    return None


# ---- 2. probe every allowlisted KineFX type inside one SOP container ---------------------------
def _create(cont, tname):
    try:
        return cont.createNode(tname, "_p")
    except hou.Error:
        return cont.createNode(tname, "_p", load_contents=False)


def probe(docs):
    names, params, errors = [], {}, {}
    n_desc = n_menu = 0
    no_help = []
    cont = hou.node("/obj").createNode("geo", "_kinefx_probe")
    for tname in sorted(ALLOWLIST):
        try:
            n = _create(cont, tname)
        except Exception as e:  # noqa: BLE001
            errors[tname] = str(e).splitlines()[0][:140]
            continue
        comps = n.type().nameComponents()  # (scope, namespace, name, version)
        namespace, nm, ver = comps[1], comps[2], comps[3]
        doc = lookup_doc(docs, namespace, nm, ver)
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
    try:
        cont.destroy()
    except Exception:
        pass
    names.sort()
    return names, params, errors, n_desc, n_menu, no_help


def main():
    write = "--write" in sys.argv
    docs, help_found = parse_help()
    if not help_found:
        print("NOTE: built-in help zip not found at %s -- probing params/menus WITHOUT help "
              "descriptions (non-fatal)." % HELP_ZIP)
    names, params, errors, n_desc, n_menu, no_help = probe(docs)

    print("built-in sop help files parsed :", len(docs))
    print("KineFX allowlist types         :", len(ALLOWLIST))
    print("KineFX types probed OK         :", len(names))
    print("KineFX types errored           :", len(errors))
    for t, e in sorted(errors.items()):
        print("   ERR %s :: %s" % (t, e))
    print("param sets built               :", len(params))
    print("params with help desc          :", n_desc)
    print("params with menu tokens        :", n_menu)
    print("types with NO help file        :", len(no_help))
    if no_help:
        print("   ", ", ".join(sorted(no_help)))

    data = json.load(open(NODES_JSON, encoding="utf-8"))
    before_types = len(data["node_types"])
    before_params = len(data["params"])

    if not write:
        print("\nDRY-RUN (no file written). Re-run with --write to merge.")
        print("would set categories.KineFX =", len(names))
        print("would add node_types.KineFX (list of %d)" % len(names))
        print("sample:", names[:6])
        return

    # Back up BEFORE the first write (idempotent — only the pre-KineFX state is preserved).
    bak = NODES_JSON + ".bak_prekinefx"
    if not os.path.exists(bak):
        json.dump(json.load(open(NODES_JSON, encoding="utf-8")),
                  open(bak, "w", encoding="utf-8"))
        print("backed up ->", bak)

    data["categories"]["KineFX"] = len(names)
    data["node_types"]["KineFX"] = names

    existing = data["params"]
    enriched, added, kept_bare = 0, 0, 0
    for name, plist in params.items():
        namespaced = name.lower().startswith("kinefx::") or name.lower().startswith("labs::")
        if namespaced:
            # fully-namespaced key -> denotes exactly one node; safe to (re)write the enriched set.
            if name in existing:
                enriched += 1
            else:
                added += 1
            existing[name] = plist
        else:
            # bare key -> the SAME node already has a correct generic-SOP entry; never clobber it.
            if name in existing:
                kept_bare += 1
            else:
                existing[name] = plist
                added += 1
    print("merge: %d namespaced keys (re)written, %d new keys, %d bare keys left untouched" %
          (enriched, added, kept_bare))

    data["note"] = data.get("note", "") + " | KineFX lane added from live probe + built-in help."
    json.dump(data, open(NODES_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("\nWROTE %s" % NODES_JSON)
    print("  node_types: %d -> %d ; params: %d -> %d" % (
        before_types, len(data["node_types"]), before_params, len(data["params"])))


if __name__ == "__main__":
    main()
