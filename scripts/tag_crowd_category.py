"""Tag every tool in reference/tool_nodes.json that is backed by a Crowd (agent / crowd-sim /
motion-path) node with `"category": "Crowd"` — the provenance classification parallel to the
existing `"category": "KineFX"` / `"Cop"` / `"Labs"` tags. Mirrors scripts/tag_kinefx_category.py.

The Crowd lane (crowd_1..crowd_6) mixes Houdini contexts — SOP (`agent`, `agentunpack`,
`crowdmotionpath*`, `sopcrowdimport`, …), CHOP (`agent`, `crowdstate::3.0`, `crowdtrigger::2.0`,
…), DOP (`crowdobject`, `agentterrainadaptation::3.0`, …), Object (`agentcam`) and VOP (crowd_6's
12 agent-data VOP building blocks). The tagger matches by tool->nodetype from tool_nodes.json, so
context is irrelevant to tagging. The match is an EXPLICIT ALLOWLIST of the exact versioned type
strings the six Crowd handlers create (the union of every wave's INTEGRATION §c list).

NOTE on the shared base name `agent`: it is a SOP tool (`agent_source`, crowd_1) AND a CHOP tool
(crowd_2) — both are Crowd, so tagging both is correct. The allowlist is disjoint from the KineFX
and Muscle allowlists (verified), so no non-Crowd tool is mis-tagged.

Idempotent. Never clobbers an existing "KineFX" / "Muscle" / "Cop" / "Labs" tag.

  python scripts/tag_crowd_category.py            # dry-run: report what would change
  python scripts/tag_crowd_category.py --write     # write the tags
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL_NODES = REPO / "reference" / "tool_nodes.json"

# Union of every Crowd wave's INTEGRATION §c exact versioned node-type list (crowd_1..crowd_6 = 64).
ALLOWLIST = {
    "agent", "agentarcingcliplayer", "agentcam", "agentclip::2.0", "agentcliplayer",
    "agentclipproperties", "agentcliptransitiongraph", "agentclipweights",
    "agentcollisionlayer", "agentconfigurejoints", "agentconstraintnetwork",
    "agentconverttransforms", "agentdefinitioncache", "agentedit", "agentlayer::2.0",
    "agentlayerbindings", "agentlayername", "agentlayers", "agentlayershapes",
    "agentlookat::3.0", "agentlookatapply::3.0", "agentmetadata", "agentprep::3.0",
    "agentproxy", "agentrelationship", "agentrigchildren", "agentrigfind", "agentrigparent",
    "agentterrainadaptation::3.0", "agentterrainprojection", "agenttransformcount",
    "agenttransformgroup", "agenttransformnames", "agenttransforms", "agentunpack",
    "agentvellumunpack", "bakeskinning", "crowdassignlayers", "crowdfuzzylogic",
    "crowdmotionpath", "crowdmotionpathapplyrel", "crowdmotionpatharcinglayer",
    "crowdmotionpathavoid", "crowdmotionpathedit", "crowdmotionpatheditcore",
    "crowdmotionpathevaluate", "crowdmotionpathevaluatecore", "crowdmotionpathfollow",
    "crowdmotionpathlayer", "crowdmotionpathretime", "crowdmotionpathtransition",
    "crowdmotionpathtrigger", "crowdobject", "crowdsource::3.0", "crowdstate::3.0",
    "crowdtransition::3.0", "crowdtrigger::2.0", "crowdtriggerlogic::2.0",
    "houdinicrowdprocedural", "kinefx::agentanimationunpack", "kinefx::agentcharacterunpack",
    "kinefx::agentfromrig", "kinefx::agentposefromrig", "sopcrowdimport",
}


def is_crowd(nodes):
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
        if is_crowd(nodes) and cat not in ("Crowd", "KineFX", "Muscle", "Labs", "Cop"):
            to_tag.append(name)
    print("crowd-backed tools needing a Crowd tag:", len(to_tag))
    print("  ", sorted(to_tag))
    already = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "Crowd")
    print("already tagged Crowd:", already)
    if len(ALLOWLIST) != 64:
        print("WARNING: allowlist has %d types (expected 64)" % len(ALLOWLIST))
    if not write:
        print("\nDRY-RUN. Re-run with --write to apply.")
        return
    for name in to_tag:
        tools[name]["category"] = "Crowd"
    TOOL_NODES.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(1 for e in tools.values() if isinstance(e, dict) and e.get("category") == "Crowd")
    print("\nWROTE %s  (+%d tagged; total Crowd=%d)" % (TOOL_NODES, len(to_tag), total))


if __name__ == "__main__":
    main()
