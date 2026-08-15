"""Tag every tool in reference/tool_nodes.json that is backed by a SideFX Labs node
(primary nodetype starts with `labs::` or `labs_`) with `"category": "Labs"` — the
provenance classification parallel to the existing `"category": "Cop"` tag. This makes
Labs-derived tools machine-distinguishable (COP-parity) even though their tool names are
bare descriptive (house convention). Idempotent. Never clobbers an existing "Cop" tag.

  python scripts/tag_labs_category.py            # dry-run: report what would change
  python scripts/tag_labs_category.py --write     # write the tags
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL_NODES = REPO / "reference" / "tool_nodes.json"


def is_labs(nodes):
    # Case-insensitive: a few Labs HDAs register with a capital `Labs::` type name
    # (e.g. Labs::polyscalpel::1.0), which is the exact string the handler creates.
    return any(str(n).lower().startswith("labs::") or str(n).lower().startswith("labs_")
               for n in nodes)


def main():
    write = "--write" in sys.argv
    data = json.loads(TOOL_NODES.read_text(encoding="utf-8"))
    tools = data["tools"]
    to_tag = []
    for name, entry in tools.items():
        if not isinstance(entry, dict):
            continue
        nodes = entry.get("nodes", [])
        if is_labs(nodes) and entry.get("category") not in ("Labs", "Cop", "KineFX"):
            to_tag.append(name)
    print("labs-backed tools needing a Labs tag:", len(to_tag))
    print("  ", sorted(to_tag))
    already = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "Labs")
    print("already tagged Labs:", already)
    if not write:
        print("\nDRY-RUN. Re-run with --write to apply.")
        return
    for name in to_tag:
        tools[name]["category"] = "Labs"
    TOOL_NODES.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "Labs")
    print("\nWROTE %s  (+%d tagged; total Labs=%d)" % (TOOL_NODES, len(to_tag), total))


if __name__ == "__main__":
    main()
