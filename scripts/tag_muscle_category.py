"""Tag every tool in reference/tool_nodes.json that is backed by a Muscle / tissue-sim node with
`"category": "Muscle"` — the provenance classification parallel to the existing `"category":
"KineFX"` / `"Crowd"` / `"Cop"` / `"Labs"` tags. Mirrors scripts/tag_kinefx_category.py.

The Muscle lane (muscle_1..muscle_2) is all SOP-context muscle/tissue authoring, simulation-prep,
and OTIS/FEM/Vellum muscle-constraint-property nodes. The match is an EXPLICIT ALLOWLIST of the
exact versioned type strings the two Muscle handlers create (the union of every wave's
INTEGRATION §c list). The allowlist is disjoint from the KineFX and Crowd allowlists (verified),
so no non-Muscle tool is mis-tagged.

Idempotent. Never clobbers an existing "KineFX" / "Crowd" / "Cop" / "Labs" tag.

  python scripts/tag_muscle_category.py            # dry-run: report what would change
  python scripts/tag_muscle_category.py --write     # write the tags
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL_NODES = REPO / "reference" / "tool_nodes.json"

# Union of every Muscle wave's INTEGRATION §c exact versioned node-type list (muscle_1..muscle_2 = 27).
ALLOWLIST = {
    "frankenmuscle", "frankenmusclepaint", "muscleadjustvolume", "muscleautotensionlines",
    "muscleconstraintpropertiesfem", "muscleconstraintpropertiesotis",
    "muscleconstraintpropertiesvellum", "muscledeform::2.0", "muscledeintersect",
    "muscleflex::2.0", "muscleid", "musclemerge", "musclemirror", "musclepaint",
    "musclepreroll", "muscleproperties", "musclepropertiesotis", "muscleslideconstraint",
    "musclesolidify", "muscletensionlines", "muscletensionlinesactivate", "muscletpose",
    "otisconfiguremuscleandtissue", "tissueproperties", "tissuepropertiesotis",
    "tissuesolidify::2.0", "tissuesolidifyotis",
}


def is_muscle(nodes):
    return any(str(n) in ALLOWLIST for n in nodes)


def main():
    write = "--write" in sys.argv
    data = json.loads(TOOL_NODES.read_text(encoding="utf-8"))
    tools = data["tools"]
    to_tag = []
    for name, entry in tools.items():
        if not isinstance(entry, dict):
            continue
        nodes = entry.get("nodes", [])
        cat = entry.get("category")
        if is_muscle(nodes) and cat not in ("Muscle", "KineFX", "Crowd", "Labs", "Cop"):
            to_tag.append(name)
    print("muscle-backed tools needing a Muscle tag:", len(to_tag))
    print("  ", sorted(to_tag))
    already = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "Muscle")
    print("already tagged Muscle:", already)
    if len(ALLOWLIST) != 27:
        print("WARNING: allowlist has %d types (expected 27)" % len(ALLOWLIST))
    if not write:
        print("\nDRY-RUN. Re-run with --write to apply.")
        return
    for name in to_tag:
        tools[name]["category"] = "Muscle"
    TOOL_NODES.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "Muscle")
    print("\nWROTE %s  (+%d tagged; total Muscle=%d)" % (TOOL_NODES, len(to_tag), total))


if __name__ == "__main__":
    main()
