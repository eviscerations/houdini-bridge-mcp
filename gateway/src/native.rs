//! Native (gateway-local) tools that run OUTSIDE Houdini. Currently just `acquire_terrain`, which
//! shells out to the rasterio-capable Python downloader (fetch + prep). This is the tool's one
//! network-egress lane; the downloader itself confines egress to an allowlist of trusted DEM hosts.
//!
//! Args reaching here are already schema-validated and clamped by `tools::ToolDef::validate`.

use crate::config::Config;
use anyhow::{anyhow, Result};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::process::Command;

/// Immutable config the native tools need for the session.
pub struct NativeCfg {
    pub prep_python: Vec<String>,
    pub downloader_root: Option<PathBuf>,
    /// Action-throttle floor in milliseconds: the minimum wall-clock gap enforced between successive
    /// DESTRUCTIVE tool calls (see `gateway::THROTTLED_TOOLS`). 0 (the default) disables throttling.
    /// Set at startup from `HMCP_MIN_ACTION_INTERVAL_MS`. This PACES destructive ops (a brief sleep),
    /// it never rejects them — a safety governor so a runaway loop / injection can't rapid-fire
    /// scene-destroying calls. Non-destructive tools (builds, reads) are never delayed.
    pub min_action_interval_ms: u64,
}

impl NativeCfg {
    pub fn from_config(cfg: &Config) -> Self {
        Self {
            prep_python: cfg.prep_python.clone(),
            downloader_root: cfg.downloader_root.clone(),
            min_action_interval_ms: read_min_action_interval_ms(),
        }
    }
}

/// Read the action-throttle floor from `HMCP_MIN_ACTION_INTERVAL_MS` (milliseconds). Absent, empty,
/// or unparseable => 0 (throttle OFF). Fail-open to OFF so a malformed env var can never wedge the
/// gateway; the throttle is a safety pacer, not a security control.
fn read_min_action_interval_ms() -> u64 {
    std::env::var("HMCP_MIN_ACTION_INTERVAL_MS")
        .ok()
        .and_then(|s| s.trim().parse::<u64>().ok())
        .unwrap_or(0)
}

/// Run `downloader.acquire` with the validated args, writing into `working_dir`. Returns the JSON
/// object the downloader prints on stdout (fetch + prep result).
pub async fn acquire_terrain(args: &Value, working_dir: &Path, ncfg: &NativeCfg) -> Result<Value> {
    let (exe, pre_args) = ncfg
        .prep_python
        .split_first()
        .ok_or_else(|| anyhow!("prep_python is empty — set it in config (e.g. [\"py\",\"-3.14\"])"))?;

    let mut cmd = Command::new(exe);
    cmd.args(pre_args);
    cmd.arg("-m").arg("downloader.acquire");
    cmd.arg("--dest").arg(working_dir);

    let num = |k: &str| args.get(k).and_then(Value::as_f64);
    if let Some(v) = num("lat") {
        cmd.arg("--lat").arg(v.to_string());
    }
    if let Some(v) = num("lon") {
        cmd.arg("--lon").arg(v.to_string());
    }
    if let Some(v) = num("radius_m") {
        cmd.arg("--radius-m").arg(v.to_string());
    }
    if let Some(arr) = args.get("bbox").and_then(Value::as_array) {
        cmd.arg("--bbox");
        for n in arr {
            cmd.arg(n.as_f64().unwrap_or(0.0).to_string());
        }
    }
    if let Some(v) = args.get("scale").and_then(Value::as_str) {
        cmd.arg("--scale").arg(v);
    }
    if let Some(v) = args.get("source").and_then(Value::as_str) {
        cmd.arg("--source").arg(v);
    }
    if let Some(v) = args.get("product").and_then(Value::as_str) {
        cmd.arg("--product").arg(v);
    }
    if let Some(v) = args.get("mode").and_then(Value::as_str) {
        cmd.arg("--mode").arg(v);
    }
    if let Some(v) = num("res") {
        cmd.arg("--res").arg(v.to_string());
    }
    if let Some(v) = args.get("max_side").and_then(Value::as_i64) {
        cmd.arg("--max-side").arg(v.to_string());
    }
    if let Some(v) = args.get("max_tiles").and_then(Value::as_i64) {
        cmd.arg("--max-tiles").arg(v.to_string());
    }

    if let Some(root) = &ncfg.downloader_root {
        cmd.current_dir(root);
    }
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let out = cmd
        .output()
        .await
        .map_err(|e| anyhow!("failed to launch prep Python ({exe}): {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(anyhow!("acquire_terrain failed: {}", err.trim()));
    }

    // The downloader prints progress lines then a final JSON object — take the last `{...}` line.
    let stdout = String::from_utf8_lossy(&out.stdout);
    let json_line = stdout
        .lines()
        .rev()
        .find(|l| l.trim_start().starts_with('{'))
        .ok_or_else(|| anyhow!("acquire_terrain produced no JSON result:\n{stdout}"))?;
    serde_json::from_str(json_line.trim())
        .map_err(|e| anyhow!("acquire_terrain returned unparseable JSON: {e}\n{json_line}"))
}

/// Acquire an ONNX model for the ML/ONNX tools from the HuggingFace host allowlist, sha256-pinned,
/// landing under `<working_dir>/models/`. Mirrors `acquire_terrain`: the guarded egress + integrity
/// check live in the Python `downloader.model` module (host allowlist, https-only, size-cap,
/// redirect-checked, hash-verify). There is NO arbitrary-URL path — the caller passes repo/file/sha.
pub async fn acquire_model(args: &Value, working_dir: &Path, ncfg: &NativeCfg) -> Result<Value> {
    let (exe, pre_args) = ncfg
        .prep_python
        .split_first()
        .ok_or_else(|| anyhow!("prep_python is empty — set it in config (e.g. [\"py\",\"-3.14\"])"))?;

    let req = |k: &str| -> Result<&str> {
        args.get(k)
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("acquire_model requires string arg '{k}'"))
    };
    let repo = req("repo")?;
    let file = req("file")?;
    let sha256 = req("sha256")?;

    let mut cmd = Command::new(exe);
    cmd.args(pre_args);
    cmd.arg("-m").arg("downloader.model");
    cmd.arg("--dest").arg(working_dir);
    cmd.arg("--repo").arg(repo);
    cmd.arg("--file").arg(file);
    cmd.arg("--sha256").arg(sha256);
    if let Some(v) = args.get("revision").and_then(Value::as_str) {
        cmd.arg("--revision").arg(v);
    }
    if let Some(v) = args.get("max_bytes").and_then(Value::as_i64) {
        cmd.arg("--max-bytes").arg(v.to_string());
    }
    if let Some(root) = &ncfg.downloader_root {
        cmd.current_dir(root);
    }
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let out = cmd
        .output()
        .await
        .map_err(|e| anyhow!("failed to launch prep Python ({exe}): {e}"))?;
    // The downloader prints progress then a final JSON object (ok:true/false) — take the last `{...}`.
    let stdout = String::from_utf8_lossy(&out.stdout);
    let json_line = stdout
        .lines()
        .rev()
        .find(|l| l.trim_start().starts_with('{'))
        .ok_or_else(|| {
            let err = String::from_utf8_lossy(&out.stderr);
            anyhow!("acquire_model produced no JSON result:\n{stdout}\n{}", err.trim())
        })?;
    serde_json::from_str(json_line.trim())
        .map_err(|e| anyhow!("acquire_model returned unparseable JSON: {e}\n{json_line}"))
}

/// Query the bundled, authoritative live-probed Houdini node reference (`reference/houdini_nodes.json`
/// under `downloader_root`). Synchronous (a local JSON read) — the agent can consult it while
/// planning, with no Houdini session. Modes: `node` (exact -> its probed params), `search`
/// (substring over node-type names), `category` (list a category), or none (summary).
pub fn node_reference(args: &Value, ncfg: &NativeCfg) -> Result<Value> {
    let base = ncfg
        .downloader_root
        .clone()
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    let path = base.join("reference").join("houdini_nodes.json");
    let text = std::fs::read_to_string(&path)
        .map_err(|e| anyhow!("node reference not found at {}: {e}", path.display()))?;
    let data: Value = serde_json::from_str(&text)?;
    let params = data.get("params").and_then(Value::as_object);
    let node_types = data.get("node_types").and_then(Value::as_object);

    // node=<type> -> its probed parameters, or a catalog search if not probed yet.
    if let Some(node) = args.get("node").and_then(Value::as_str) {
        if let Some(p) = params.and_then(|m| m.get(node)) {
            return Ok(json!({ "node": node, "probed": true, "params": p }));
        }
        return Ok(json!({
            "node": node, "probed": false,
            "note": "not in the probed param set yet; matching node types in the live catalog:",
            "matches": search_types(node_types, node, 40)
        }));
    }
    // search=<substr> across node-type names.
    if let Some(q) = args.get("search").and_then(Value::as_str) {
        let hits = search_types(node_types, q, 60);
        return Ok(json!({ "search": q, "count": hits.len(), "matches": hits }));
    }
    // category=<Sop|...> -> a sample of that category's node types.
    if let Some(cat) = args.get("category").and_then(Value::as_str) {
        let list = node_types.and_then(|m| m.get(cat)).and_then(Value::as_array);
        let sample: Vec<&str> = list
            .map(|a| a.iter().filter_map(Value::as_str).take(250).collect())
            .unwrap_or_default();
        return Ok(json!({ "category": cat, "count": list.map(|a| a.len()).unwrap_or(0), "sample": sample }));
    }
    // No args -> summary.
    Ok(json!({
        "houdini_version": data.get("houdini_version"),
        "categories": data.get("categories"),
        "probed_param_sets": params.map(|m| m.len()).unwrap_or(0),
        "usage": "pass node=<type> for its params, search=<substring> to find types, or category=<Sop|Object|Dop|Driver|Cop|Cop2|Lop|Vop|Chop|Shop|Top>.",
        "see_also": "vex_reference (VEX builtins), recipe_reference (tool-mapped workflows), capabilities (tool catalog + local HTTP help-server URL)."
    }))
}

fn search_types(node_types: Option<&serde_json::Map<String, Value>>, query: &str, cap: usize) -> Vec<String> {
    let q = query.to_lowercase();
    let mut out = Vec::new();
    if let Some(map) = node_types {
        for arr in map.values() {
            if let Some(list) = arr.as_array() {
                for n in list {
                    if let Some(s) = n.as_str() {
                        if s.to_lowercase().contains(&q) {
                            out.push(s.to_string());
                            if out.len() >= cap {
                                return out;
                            }
                        }
                    }
                }
            }
        }
    }
    out
}

// ---- recipe reference (offline; bundled tool-mapped workflow recipes) ----

fn recipe_brief(r: &Value) -> Value {
    json!({ "id": r.get("id"), "domain": r.get("domain"),
            "title": r.get("title"), "summary": r.get("summary") })
}

fn recipe_hay(r: &Value) -> String {
    // Index id/title/summary + the STEP TOOL NAMES + tool_manifest + classify, so `search` finds a
    // recipe by the tool it uses (a driving agent searches "how do I use polywire" and lands the
    // recipe, never guessing a query — recipes are the retrieval index for intent).
    let mut hay = format!("{} {} {} {}",
        r.get("id").and_then(Value::as_str).unwrap_or(""),
        r.get("title").and_then(Value::as_str).unwrap_or(""),
        r.get("summary").and_then(Value::as_str).unwrap_or(""),
        r.get("classify").and_then(Value::as_str).unwrap_or(""),
    );
    if let Some(steps) = r.get("steps").and_then(Value::as_array) {
        for s in steps {
            if let Some(t) = s.get("tool").and_then(Value::as_str) { hay.push(' '); hay.push_str(t); }
        }
    }
    if let Some(man) = r.get("tool_manifest").and_then(Value::as_array) {
        for t in man { if let Some(t) = t.as_str() { hay.push(' '); hay.push_str(t); } }
    }
    // Index the presence of ANY `*_opportunity` signal on a step (the gated-capability family:
    // wrangle / render / rop / solver / vop), so `search=render` (or solver/vop/wrangle/opportunity)
    // surfaces the recipes where the AI should proactively offer the gated capability — a human-gated
    // safe-VEX wrangle, a WIRE-ONLY render/ROP, a deferred DOP solver, or a VOP graph.
    if let Some(steps) = r.get("steps").and_then(Value::as_array) {
        for s in steps {
            if let Some(obj) = s.as_object() {
                for k in obj.keys() {
                    if let Some(gate) = k.strip_suffix("_opportunity") {
                        hay.push_str(" opportunity ");
                        hay.push_str(k);       // e.g. "render_opportunity"
                        hay.push(' ');
                        hay.push_str(gate);    // the bare gate word: render/rop/solver/vop/wrangle
                    }
                }
                // Keep the legacy safe-vex alias so `search=safe-vex`/`vex` still lands wrangle steps.
                if obj.contains_key("wrangle_opportunity") {
                    hay.push_str(" safe-vex vex");
                }
            }
        }
    }
    hay.to_lowercase()
}

/// Query the bundled workflow-recipe reference (`reference/recipes.json`) — canonical, tool-mapped
/// "how to actually do X" recipes, each an ordered sequence of THIS server's real tools + the params
/// that matter + per-step landmark/verify/geometry_out. Read-only + offline (a local JSON read); no
/// Houdini session. Modes: `classify`=<what you're looking at> -> the ROUTING table (input element ->
/// lane -> entry_recipe; START HERE); `recipe`=<id> -> the full ordered steps; `domain`=<any domain
/// name> -> that domain's recipes (brief); `search`=<substring> over id/title/summary + step tools;
/// none -> the recipe index + routing table. Serves data; never actuates.
pub fn recipe_reference(args: &Value, ncfg: &NativeCfg) -> Result<Value> {
    let base = ncfg
        .downloader_root
        .clone()
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    let path = base.join("reference").join("recipes.json");
    let text = std::fs::read_to_string(&path)
        .map_err(|e| anyhow!("recipe reference not found at {}: {e}", path.display()))?;
    let data: Value = serde_json::from_str(&text)?;
    let recipes = data.get("recipes").and_then(Value::as_array).cloned().unwrap_or_default();

    // recipe=<id> -> the full recipe (exact id, case-insensitive; else closest matches).
    if let Some(id) = args.get("recipe").and_then(Value::as_str) {
        if let Some(r) = recipes.iter().find(|r| {
            r.get("id").and_then(Value::as_str).map(|s| s.eq_ignore_ascii_case(id)).unwrap_or(false)
        }) {
            return Ok(r.clone());
        }
        let idl = id.to_lowercase();
        let matches: Vec<Value> =
            recipes.iter().filter(|r| recipe_hay(r).contains(&idl)).map(recipe_brief).collect();
        return Ok(json!({ "recipe": id, "found": false,
                          "note": "no recipe with that id; closest matches:", "matches": matches }));
    }
    // domain=<x> -> that domain's recipes (brief).
    if let Some(dom) = args.get("domain").and_then(Value::as_str) {
        let list: Vec<Value> = recipes.iter().filter(|r| {
            r.get("domain").and_then(Value::as_str).map(|s| s.eq_ignore_ascii_case(dom)).unwrap_or(false)
        }).map(recipe_brief).collect();
        return Ok(json!({ "domain": dom, "count": list.len(), "recipes": list }));
    }
    // search=<substr> over id/title/summary + step tools + tool_manifest + classify.
    if let Some(q) = args.get("search").and_then(Value::as_str) {
        let ql = q.to_lowercase();
        let list: Vec<Value> =
            recipes.iter().filter(|r| recipe_hay(r).contains(&ql)).map(recipe_brief).collect();
        return Ok(json!({ "search": q, "count": list.len(), "matches": list }));
    }
    // classify=<element> -> the ROUTING table: which lane + entry_recipe fits an input element
    // ("a building", "a photo of a facade", "terrain"). The router is the front door: what am I
    // looking at -> which recipe. `classify` with no value (or an empty string) returns the whole
    // routing table so an agent can see every lane.
    let routing = data.get("routing").and_then(Value::as_array).cloned().unwrap_or_default();
    if let Some(el) = args.get("classify").and_then(Value::as_str) {
        let ell = el.to_lowercase();
        let matches: Vec<Value> = if ell.is_empty() {
            routing.clone()
        } else {
            routing.iter().filter(|row| {
                ["input_element", "geometry_class", "lane", "entry_recipe", "notes", "axis"].iter().any(|k| {
                    row.get(*k).and_then(Value::as_str).map(|s| s.to_lowercase().contains(&ell)).unwrap_or(false)
                })
            }).cloned().collect()
        };
        return Ok(json!({ "classify": el, "count": matches.len(), "routes": matches,
            "routing_note": data.get("routing_note"),
            "note": "each route names an entry_recipe — call recipe=<entry_recipe> for its ordered, verifiable steps. Each route also carries axis=image-element (reach by decomposing a photo/scene) vs axis=task-intent (invoke by task on geometry you already have — not image-reachable); classify=task-intent lists every verb lane." }));
    }
    // No args -> the recipe index (+ the routing table front door).
    Ok(json!({
        "note": data.get("note"),
        "routing_note": data.get("routing_note"),
        "domains": data.get("domains"),
        "routing": routing,
        "count": recipes.len(),
        "recipes": recipes.iter().map(recipe_brief).collect::<Vec<_>>(),
        "usage": "classify=<what you're looking at> -> routing table (start here); recipe=<id> -> full ordered steps; domain=<name> -> a domain's recipes; search=<substring> (indexes step tools too). Routes carry axis=image-element vs task-intent (see routing_note); classify=task-intent lists the verb lanes."
    }))
}

// ---- VEX reference (offline; reads only the two bundled reference assets) ----

/// Map a short `topic=` key to the matching `##` heading in the curated VEX guide.
pub(crate) const VEX_TOPICS: &[(&str, &str)] = &[
    ("handoff", "The wrangle handoff"),
    ("surface", "Surfacing a wrangle — when to offer, and the consent handshake"),
    ("contexts", "Wrangle contexts & run-over"),
    ("types", "Attribute syntax & types"),
    ("core", "Core functions"),
    ("noise", "Noise"),
    ("lookups", "Geometry lookups"),
    ("groups", "Groups & selection"),
    ("patterns", "Common terrain / geo patterns"),
    ("gotchas", "Gotchas"),
    ("index", "Quick index"),
    // ---- cookbook domains (curated, verified idioms appended after the fundamentals) ----
    ("kinefx", "KineFX rigs & skeletons"),
    ("curves", "Curves & polylines"),
    ("matrix", "Matrices & quaternions"),
    ("rbd", "RBD & destruction"),
    ("pyro", "Pyro & smoke"),
    ("flip", "FLIP fluids"),
    ("pops", "Particles (POP wrangles)"),
    ("vellum", "Vellum (constraint authoring)"),
    ("crowds", "Crowds (agent wrangles)"),
    ("orient", "Copy, instancing & orient"),
    ("noise2", "Procedural noise (fractal, worley, curl)"),
    ("pointclouds", "Point clouds & proximity"),
    ("modeling", "Modeling by attribute"),
    ("uv", "UV & texture"),
    ("heightfield", "Terrain & heightfields"),
    ("attribs", "Attribute recipes"),
    ("groups_adv", "Advanced groups & selection"),
    ("vdb", "Volumes & VDB"),
    ("sceneprep", "Scene prep, utility & debug"),
    ("solver", "Solver & time feedback"),
];

/// Orientation / discoverability entry point. Reads the bundled tool catalog
/// (`reference/catalog.json`) and returns a summary of what this server can do — tool count by
/// category — plus pointers to the deeper offline references (`node_reference`, `vex_reference`)
/// and the live Houdini help server. A planning agent should call this first to find the full
/// surface cheaply. READ-ONLY and offline (a local JSON read); no Houdini session, no network.
pub fn capabilities(_args: &Value, ncfg: &NativeCfg) -> Result<Value> {
    let base = ncfg
        .downloader_root
        .clone()
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    let path = base.join("reference").join("catalog.json");
    let text = std::fs::read_to_string(&path)
        .map_err(|e| anyhow!("tool catalog not found at {}: {e}", path.display()))?;
    let data: Value = serde_json::from_str(&text)?;
    let tools = data.get("tools").and_then(Value::as_array);
    let tool_count = tools.map(|a| a.len()).unwrap_or(0);

    // Per-category counts, preserving first-seen (catalog) order.
    let mut cats: Vec<(String, usize)> = Vec::new();
    if let Some(list) = tools {
        for t in list {
            if let Some(c) = t.get("category").and_then(Value::as_str) {
                match cats.iter_mut().find(|(name, _)| name == c) {
                    Some(entry) => entry.1 += 1,
                    None => cats.push((c.to_string(), 1)),
                }
            }
        }
    }
    let categories: serde_json::Map<String, Value> =
        cats.into_iter().map(|(k, v)| (k, json!(v))).collect();

    Ok(json!({
        "server": "houdini-bridge-mcp",
        "summary": format!(
            "{tool_count} typed, validated, data-only tools for driving Houdini 21.0.671 (geospatial reconstruction + VFX). Every capability is a fixed, schema-checked operation — there is no arbitrary-code, generic-node-set, or raw-VEX tool. Consult the references below to discover exactly which node chains and VEX are possible before you build."
        ),
        "tool_count": tool_count,
        "categories": categories,
        "references": {
            "node_reference": "Offline authoritative Houdini node catalog (live-probed) — real node types + real parameter names; the source of truth for what node chains are possible. Call node_reference with node=<type>, search=<substring>, or category=<Sop|Object|Dop|Driver|Cop|Cop2|Lop|Vop|Chop|Shop|Top>.",
            "vex_reference": "Offline VEX reference — builtin functions (signatures + summaries) plus a wrangle workflow guide. REFERENCE ONLY: the executor never runs VEX; use it to propose VEX text for the user to paste into a wrangle by hand. Call vex_reference with function=<name>, search=<substring>, category=<group>, or topic=<key>.",
            "recipe_reference": "Canonical, tool-mapped workflow recipes — how to actually do X with these tools (FLIP/pyro/RBD/procedural/material), each an ordered sequence of real tools + the params that matter. Call recipe_reference with classify=<what you're looking at> for the routing table (start here), recipe=<id>, domain=<any domain name>, or search=<substring>; no args for the index.",
            "houdini_help_server": "The running Houdini instance serves its full offline help over local HTTP (default http://127.0.0.1:48626/) — node docs, VEX, and examples, straight from the installed version.",
            "tool_params": "Each tool's exact typed parameters (names, kinds, ranges, enum tokens) are enforced by the gateway — pass them verbatim. Unknown params are rejected; numerics are clamped; every filesystem path is confined to the one working directory."
        },
        "boundary": "Data-only by construction: a fixed registry of typed operations. No arbitrary-code / generic-node-parameter / raw-VEX-or-Python tool exists, so the boundary cannot be talked past. Renders and heavy caches are wire-only — this server builds the network; you fire the cook/render.",
        "how_to_discover": "How to do X (FLIP/pyro/RBD/procedural/material) -> recipe_reference. Planning a node chain -> node_reference. Need VEX text for a wrangle -> vex_reference. A task that needs conditional/measured logic (threshold breaking, cluster boundary, custom particle/point masks, per-piece naming) -> SURFACE a wrangle to the user: vex_reference topic=surface (propose the VEX + teach it; run only with user consent via set_attrib_expr + allow_attrib_expr, or hand it over to paste). Live scene state -> scene_info / read_geo_stats. A node erroring -> find_error_nodes.",
        "governor": "Build to the TARGET budget, not the tool's ceiling — a 2M-poly coffee cup is a failure, not a feature. Heavy geometry/sim tools return advisory FLAGS: `envelope` (live VRAM/RAM band + guidance), `magnitude` (ok/caution/heavy for the requested count/resolution/iterations), and after the cook `geo_cost` plus a `geo_cost_flag` when the output is dense. These GUIDE, they do not limit: on caution/heavy or a geo_cost_flag, down-scale (fewer points, larger voxel/edge size, fewer subdivisions) to the deliverable's budget. Only a catastrophic VRAM/RAM band refuses. Call `mem` for the live envelope (incl. per-GPU VRAM)."
    }))
}

/// Query the bundled, offline VEX reference: the authoritative function catalog
/// (`reference/vex_functions.json`, mined from the local Houdini help) plus the curated
/// workflow/patterns guide (`reference/VEX_REFERENCE.md`). READ-ONLY and offline — no Houdini,
/// no network. This tool NEVER runs VEX; the executor is deliberately data-only. Its output is
/// documentation the AI uses to propose VEX *text* that the USER pastes into a wrangle by hand
/// (the "wrangle handoff"). Modes: `function` (signatures + summary + guide examples), `search`
/// (substring over names + summaries), `category` (list one group), `topic` (a guide section), or
/// none (summary + the reference-only boundary note).
pub fn vex_reference(args: &Value, ncfg: &NativeCfg) -> Result<Value> {
    let base = ncfg
        .downloader_root
        .clone()
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    let json_path = base.join("reference").join("vex_functions.json");
    let text = std::fs::read_to_string(&json_path)
        .map_err(|e| anyhow!("VEX function catalog not found at {}: {e}", json_path.display()))?;
    let data: Value = serde_json::from_str(&text)?;
    let functions = data.get("functions").and_then(Value::as_object);

    // function=<name> -> its signature(s) + summary + categories (+ guide examples if present).
    if let Some(name) = args.get("function").and_then(Value::as_str) {
        if let Some(entry) = functions.and_then(|m| m.get(name)) {
            let examples = guide_examples(&base, name);
            return Ok(json!({
                "function": name,
                "found": true,
                "signatures": entry.get("signatures"),
                "summary": entry.get("summary"),
                "categories": entry.get("categories"),
                "guide_examples": examples,
            }));
        }
        // Not an exact name -> offer substring matches so the agent can retry.
        return Ok(json!({
            "function": name,
            "found": false,
            "note": "no VEX function by that exact name; matching names in the catalog:",
            "matches": search_functions(functions, name, 40),
        }));
    }
    // search=<substr> across function names AND summaries.
    if let Some(q) = args.get("search").and_then(Value::as_str) {
        let hits = search_functions(functions, q, 80);
        return Ok(json!({ "search": q, "count": hits.len(), "matches": hits }));
    }
    // category=<name> -> the functions in one help group (case-insensitive on the group name).
    if let Some(cat) = args.get("category").and_then(Value::as_str) {
        let want = cat.to_lowercase();
        let mut list = Vec::new();
        if let Some(map) = functions {
            for (fname, info) in map {
                let in_cat = info
                    .get("categories")
                    .and_then(Value::as_array)
                    .map(|a| a.iter().filter_map(Value::as_str).any(|c| c.to_lowercase() == want))
                    .unwrap_or(false);
                if in_cat {
                    list.push(json!({ "name": fname, "summary": info.get("summary") }));
                }
            }
        }
        list.sort_by(|a, b| a.get("name").and_then(Value::as_str).cmp(&b.get("name").and_then(Value::as_str)));
        return Ok(json!({ "category": cat, "count": list.len(), "functions": list }));
    }
    // topic=<key> -> a section of the curated guide.
    if let Some(topic) = args.get("topic").and_then(Value::as_str) {
        let key = topic.to_lowercase();
        if let Some((_, heading)) = VEX_TOPICS.iter().find(|(k, _)| *k == key) {
            match guide_section(&base, heading) {
                Some(body) => return Ok(json!({ "topic": topic, "heading": heading, "content": body })),
                None => return Ok(json!({ "topic": topic, "note": format!("guide section '{heading}' not found") })),
            }
        }
        let keys: Vec<&str> = VEX_TOPICS.iter().map(|(k, _)| *k).collect();
        return Ok(json!({ "topic": topic, "note": "unknown topic", "valid_topics": keys }));
    }
    // No args -> summary + the reference-only boundary note.
    let categories = data.get("categories");
    let topic_keys: Vec<&str> = VEX_TOPICS.iter().map(|(k, _)| *k).collect();
    Ok(json!({
        "houdini_version": data.get("houdini_version"),
        "function_count": data.get("function_count"),
        "categories": categories,
        "topics": topic_keys,
        "usage": "pass function=<name> for signatures, search=<substring> to find functions, category=<group> to list one, or topic=<key> for a guide section.",
        "boundary": "REFERENCE ONLY. This tool serves VEX documentation offline; it never runs VEX. The executor is data-only (no wrangle/exec path). The AI proposes VEX text for the USER to paste into a wrangle node by hand."
    }))
}

/// Substring match over VEX function names and summaries (case-insensitive).
fn search_functions(functions: Option<&serde_json::Map<String, Value>>, query: &str, cap: usize) -> Vec<Value> {
    let q = query.to_lowercase();
    let mut out = Vec::new();
    if let Some(map) = functions {
        // Deterministic order: sort names first.
        let mut names: Vec<&String> = map.keys().collect();
        names.sort();
        for name in names {
            let info = &map[name];
            let summary = info.get("summary").and_then(Value::as_str).unwrap_or("");
            if name.to_lowercase().contains(&q) || summary.to_lowercase().contains(&q) {
                out.push(json!({ "name": name, "summary": summary }));
                if out.len() >= cap {
                    break;
                }
            }
        }
    }
    out
}

/// Return the body of a `## <heading>` section of the curated guide, up to the next `## ` heading.
fn guide_section(base: &Path, heading: &str) -> Option<String> {
    let path = base.join("reference").join("VEX_REFERENCE.md");
    let text = std::fs::read_to_string(path).ok()?;
    let mut lines = text.lines();
    // Advance to the target heading line.
    let target = format!("## {heading}");
    lines.by_ref().find(|l| l.trim() == target)?;
    let mut body = Vec::new();
    for line in lines {
        if line.starts_with("## ") {
            break;
        }
        body.push(line);
    }
    // Trim leading/trailing blank + horizontal-rule lines.
    while matches!(body.first(), Some(l) if l.trim().is_empty() || l.trim() == "---") {
        body.remove(0);
    }
    while matches!(body.last(), Some(l) if l.trim().is_empty() || l.trim() == "---") {
        body.pop();
    }
    Some(body.join("\n"))
}

/// Scan the curated guide for lines that reference a function (as `name(`), returning a few as
/// ready-to-adapt examples. Best-effort — an empty list just means the guide has no snippet for it.
fn guide_examples(base: &Path, func: &str) -> Vec<String> {
    let path = base.join("reference").join("VEX_REFERENCE.md");
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => return Vec::new(),
    };
    let needle = format!("{func}(");
    let mut out = Vec::new();
    for line in text.lines() {
        let t = line.trim();
        if t.contains(&needle) && !t.starts_with('#') && !t.starts_with('|') {
            out.push(t.to_string());
            if out.len() >= 5 {
                break;
            }
        }
    }
    out
}
