#!/usr/bin/env python3
"""Recipe-integrity gate for reference/recipes.json.

Recipes are the ROUTING layer that turns tool SURFACE into DRIVABLE capability: an agent calls
`recipe_reference(classify=…)` -> a routing row -> its `entry_recipe` -> the ordered steps. If a step
names a tool that no longer exists (renamed / never shipped), the agent routes into a dead end. This
gate keeps recipes honest against the live catalog:

  1. every recipe step `tool` is a real catalog tool (or a gateway-native tool)
  2. every `tool_manifest` entry is a real tool
  3. every routing `entry_recipe` is a real recipe id
  4. every `domain` used by a recipe is declared in `domains`
  5. (advisory) tools named inside `verify.cheap` / `milestone_check` strings resolve too

Plain python (no hou):  python scripts/validate_recipes.py   (exit 1 on any hard violation)
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECIPES = REPO / "reference" / "recipes.json"
CATALOG = REPO / "reference" / "catalog.json"
# native (non-handler) tools that are legitimately callable but not in the node-handler registry
GATEWAY_NATIVE = {"acquire_terrain", "acquire_model", "node_reference", "vex_reference",
                  "recipe_reference", "capabilities", "batch"}
# gated-capability opportunity-signal family (docs/_OPPORTUNITY_SIGNALS_SCHEMA.md): the recognised
# `<gate>_opportunity` step keys. Each object requires why/propose_via/consent; an optional gated_tool
# must resolve to a live tool.
_OPP_GATES = {"wrangle", "render", "rop", "solver", "vop"}


def main():
    rec = json.loads(RECIPES.read_text(encoding="utf-8"))
    catalog = {t["name"] for t in json.loads(CATALOG.read_text(encoding="utf-8"))["tools"]}
    universe = catalog | GATEWAY_NATIVE
    recipes = rec.get("recipes", [])
    routing = rec.get("routing", [])
    domains = set(rec.get("domains", []))
    ids = {r["id"] for r in recipes}

    hard = []      # (recipe/route, kind, offending)
    advisory = []

    tool_token = re.compile(r"[a-z][a-z0-9_]+")

    for r in recipes:
        rid = r.get("id", "<no-id>")
        if r.get("domain") and r["domain"] not in domains:
            hard.append((rid, "undeclared domain", r["domain"]))
        for i, step in enumerate(r.get("steps", [])):
            t = step.get("tool")
            # a parenthesized "(…)" tool is a deliberate META-step (agent vision, dispatch,
            # cross-recipe reference), not a real tool — the established convention.
            if t and t.startswith("("):
                continue
            if t and t not in universe:
                hard.append((rid, f"step[{i}] tool", t))
            # advisory: tools referenced in verify strings
            v = step.get("verify", {}) or {}
            for key in ("cheap", "milestone_check"):
                s = v.get(key)
                if not s:
                    continue
                head = s.split("@")[0].split("(")[0].strip()
                tok = head.split()[0] if head.split() else ""
                if tok and tok in catalog:
                    pass
                elif tok and tok not in universe and tool_token.fullmatch(tok):
                    advisory.append((rid, f"step[{i}] verify.{key} tool", tok))
            # opportunity-family signals: validate the shape + that any gated_tool is a live tool.
            for okey in [k for k in step.keys() if k.endswith("_opportunity")]:
                gate = okey[: -len("_opportunity")]
                if gate not in _OPP_GATES:
                    hard.append((rid, f"step[{i}] unknown opportunity kind", okey))
                opp = step.get(okey)
                if not isinstance(opp, dict):
                    hard.append((rid, f"step[{i}] {okey} not an object", type(opp).__name__))
                    continue
                for req in ("why", "propose_via", "consent"):
                    if not opp.get(req):
                        hard.append((rid, f"step[{i}] {okey} missing '{req}'", okey))
                gt = opp.get("gated_tool")
                if gt and gt not in universe:
                    hard.append((rid, f"step[{i}] {okey}.gated_tool", gt))
        for t in r.get("tool_manifest", []):
            if t not in universe:
                hard.append((rid, "tool_manifest", t))

    for row in routing:
        er = row.get("entry_recipe")
        if er and er not in ids:
            hard.append((row.get("input_element", "<route>")[:40], "entry_recipe", er))

    print(f"recipes: {len(recipes)} | routing: {len(routing)} | domains: {len(domains)} | "
          f"catalog tools: {len(catalog)}")
    # advisory verify-string tokens: skip common English verbs that aren't tools
    _VERBS = {"confirm", "open", "list", "check", "verify", "ensure", "read", "see", "run"}
    advisory = [(w, k, o) for (w, k, o) in advisory if o not in _VERBS]
    if advisory:
        print(f"\nADVISORY ({len(advisory)}) - tool named in a verify string not in catalog:")
        for who, kind, off in advisory:
            print(f"  ~ {who}: {kind} = {off!r}")
    if hard:
        print(f"\nHARD VIOLATIONS ({len(hard)}):")
        for who, kind, off in hard:
            print(f"  [X] {who}: {kind} = {off!r}")
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: ALL PASS - every recipe/route references a real tool + recipe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
