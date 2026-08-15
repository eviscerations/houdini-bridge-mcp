//! The MCP stdio server — the SOLE entry point for the AI client. This is where the security
//! boundary is enforced on the way IN:
//!   - exposes only the fixed, typed endpoint set as MCP tools (schemas from `tools.rs`);
//!   - validates every param (numeric clamps, enums, path allowlists) before it can reach the
//!     executor — via `ToolDef::validate`;
//!   - confines every filesystem path to the configured working directory (`realpath`);
//!   - RENDER endpoints are WIRE-ONLY: they build the render graph but expose no execute call
//!     (there simply is no such tool in the catalog);
//!   - emits every call to the audit sink for the GUI's live log.
//!
//! It never forwards raw code — there is no exec / node_op / raw-wrangle tool in the catalog.
//!
//! Transport: newline-delimited JSON-RPC 2.0 over stdin/stdout (the MCP stdio transport). STDOUT
//! carries ONLY protocol frames — all logging goes to stderr (see `main.rs`). Requests are handled
//! one at a time: the executor runs on Houdini's single main thread, so serializing here keeps the
//! audit log ordered and avoids pointless pile-up at the executor.

use crate::{executor::Executor, native::{self, NativeCfg}, tools::ToolDef};
use anyhow::Result;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

/// The MCP protocol revision this server implements. If the client asks for a different one we
/// echo theirs back (best-effort negotiation) rather than fail the handshake.
const PROTOCOL_VERSION: &str = "2025-06-18";

/// A single line in the live audit log surfaced by the GUI.
#[derive(Debug, Clone)]
pub struct AuditEvent {
    pub endpoint: String,
    pub summary: String,
    pub ok: bool,
}

pub type AuditSink = tokio::sync::mpsc::UnboundedSender<AuditEvent>;

/// A shared handle to the confinement root. The GUI owns it and may edit it live (the working-dir
/// field); `serve` reads it fresh on every call so a change takes effect for all future calls.
pub type WorkingDir = Arc<RwLock<PathBuf>>;

/// Max bytes for one inbound `\n`-delimited JSON-RPC frame — the gateway's memory-DoS guard so a
/// single unterminated multi-GB line can never buffer unbounded into memory here. Tool calls are
/// small; the executor separately enforces a 1 MB request-body cap, so 8 MB is ample headroom for any
/// real inbound frame while bounding the read.
const MAX_INBOUND_LINE_BYTES: usize = 8 * 1024 * 1024;

/// The outcome of reading one inbound frame.
enum Frame {
    /// A complete `\n`-delimited line (newline stripped).
    Line(String),
    /// The line exceeded the cap; it has been drained to the next newline and must be skipped.
    TooLong,
    /// End of input (client disconnected).
    Eof,
}

/// Read one `\n`-delimited line from `reader`, capped at `MAX_INBOUND_LINE_BYTES`. On overflow it
/// drains the remainder of the over-long line (to the next newline / EOF) and returns `TooLong`, so an
/// oversized frame neither buffers into memory nor kills the session — the caller logs it and keeps
/// serving. `buf` is a reusable scratch buffer.
async fn read_capped_line<R: AsyncBufReadExt + Unpin>(reader: &mut R, buf: &mut Vec<u8>) -> Result<Frame> {
    buf.clear();
    let mut overflow = false;
    loop {
        let chunk = reader.fill_buf().await?;
        if chunk.is_empty() {
            return Ok(if overflow {
                Frame::TooLong
            } else if buf.is_empty() {
                Frame::Eof
            } else {
                Frame::Line(String::from_utf8_lossy(buf).into_owned())
            });
        }
        if let Some(pos) = chunk.iter().position(|&b| b == b'\n') {
            if !overflow {
                buf.extend_from_slice(&chunk[..pos]);
                if buf.len() > MAX_INBOUND_LINE_BYTES {
                    overflow = true; // the completed line is over the cap — reject it
                }
            }
            reader.consume(pos + 1);
            return Ok(if overflow {
                Frame::TooLong
            } else {
                Frame::Line(String::from_utf8_lossy(buf).into_owned())
            });
        }
        let n = chunk.len();
        if !overflow {
            buf.extend_from_slice(chunk);
            if buf.len() > MAX_INBOUND_LINE_BYTES {
                overflow = true;
                buf.clear();
                buf.shrink_to_fit();
            }
        }
        reader.consume(n);
    }
}

/// Serve the MCP tool surface over stdio until stdin closes (the client disconnects).
pub async fn serve(working_dir: WorkingDir, exec: Executor, ncfg: Arc<NativeCfg>, audit: AuditSink) -> Result<()> {
    let catalog = crate::tools::mvp_catalog();
    let index: HashMap<&str, &ToolDef> = catalog.iter().map(|t| (t.name, t)).collect();

    let mut reader = BufReader::new(tokio::io::stdin());
    let mut linebuf: Vec<u8> = Vec::with_capacity(8192);
    let mut stdout = tokio::io::stdout();

    // Timestamp of the last DESTRUCTIVE tool call (see `THROTTLED_TOOLS`), for the optional action
    // throttle. The serve loop handles one request at a time (the executor is Houdini's single main
    // thread), so a plain `&mut` threaded through the call chain is correct — no lock needed.
    let mut last_action: Option<Instant> = None;

    tracing::info!("MCP stdio server ready — {} tools", catalog.len());

    loop {
        match read_capped_line(&mut reader, &mut linebuf).await? {
            Frame::Eof => break,
            Frame::TooLong => {
                tracing::warn!(
                    "dropped an inbound frame exceeding {} bytes (memory-DoS guard)",
                    MAX_INBOUND_LINE_BYTES
                );
                continue;
            }
            Frame::Line(line) => {
                if line.trim().is_empty() {
                    continue;
                }
                if let Some(response) = handle_line(&line, &working_dir, &exec, &ncfg, &index, &audit, &mut last_action).await {
                    let mut text = serde_json::to_string(&response)?;
                    text.push('\n'); // newline-delimited framing
                    stdout.write_all(text.as_bytes()).await?;
                    stdout.flush().await?;
                }
            }
        }
    }
    Ok(())
}

/// Parse and dispatch one JSON-RPC line. Returns `Some(response)` for requests, `None` for
/// notifications (which carry no `id` and must not be answered).
async fn handle_line(
    line: &str,
    working_dir: &RwLock<PathBuf>,
    exec: &Executor,
    ncfg: &NativeCfg,
    index: &HashMap<&str, &ToolDef>,
    audit: &AuditSink,
    last_action: &mut Option<Instant>,
) -> Option<Value> {
    let msg: Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(_) => return Some(rpc_error(Value::Null, -32700, "parse error")),
    };

    let id = msg.get("id").cloned(); // absent ⇒ notification
    let method = msg.get("method").and_then(Value::as_str).unwrap_or_default();
    let params = msg.get("params").cloned().unwrap_or(Value::Null);

    match method {
        "initialize" => Some(rpc_ok(id?, initialize_result(&params))),
        // Notifications — no response, ever.
        m if m.starts_with("notifications/") => None,
        "ping" => Some(rpc_ok(id?, json!({}))),
        "tools/list" => Some(rpc_ok(id?, tools_list(index))),
        "tools/call" => {
            let id = id?;
            match tools_call(&params, working_dir, exec, ncfg, index, audit, last_action).await {
                Ok(result) => Some(rpc_ok(id, result)),
                Err(code_msg) => Some(rpc_error(id, code_msg.0, &code_msg.1)),
            }
        }
        other => {
            // Unknown method: error a request, ignore a notification.
            id.map(|id| rpc_error(id, -32601, &format!("method not found: {other}")))
        }
    }
}

fn initialize_result(params: &Value) -> Value {
    // Echo the client's protocol version when they name one, else advertise ours.
    let version = params
        .get("protocolVersion")
        .and_then(Value::as_str)
        .unwrap_or(PROTOCOL_VERSION);
    json!({
        "protocolVersion": version,
        "capabilities": { "tools": {} },
        "serverInfo": { "name": "houdini-bridge-mcp", "version": env!("CARGO_PKG_VERSION") },
        // Bootstrap handed to the agent ON CONNECT — before any tool search — so a fresh agent finds
        // the guided path (capabilities -> recipe_reference) without needing its insider vocabulary.
        "instructions": "houdini-bridge-mcp is a DATA-ONLY Houdini 21 control surface: you build node \
networks; the USER fires cooks/renders. Renders and heavy caches are WIRE-ONLY (you build the network, \
the user runs it), and there is no arbitrary-code / VEX / Python path — every capability is a fixed, \
typed, schema-validated tool. NEW HERE / GETTING STARTED: call `capabilities` first to orient (the \
data-only boundary, the build-to-a-budget governor, and where to look things up), then \
`recipe_reference` with classify=<your task> (e.g. 'a building', 'terrain', 'rig the mesh I built') for \
the ordered, tool-mapped steps that carry the conventions — plant OUT_ nulls, verify each step, hand off \
at WIRE-ONLY / wrangle gates. Look up node types with `node_reference`, propose VEX text with \
`vex_reference`, read live scene state with `scene_info`, and run many ops in one round-trip with `batch`."
    })
}

fn tools_list(index: &HashMap<&str, &ToolDef>) -> Value {
    // Stable ordering so the client sees a consistent list.
    let mut tools: Vec<Value> = index.values().map(|t| t.listing()).collect();
    tools.sort_by(|a, b| a["name"].as_str().unwrap_or("").cmp(b["name"].as_str().unwrap_or("")));
    json!({ "tools": tools })
}

/// Destructive tools whose rapid-fire would let a runaway loop / prompt-injection tear down a scene
/// before a human can react. When the action throttle is enabled (`HMCP_MIN_ACTION_INTERVAL_MS > 0`),
/// each of these is PACED — a brief sleep so successive destructive calls can't fire back-to-back.
/// (All four are confirmed present in `tools::mvp_catalog`.) Non-destructive tools are never delayed,
/// so batch-building / reads stay fast. This is a safety pacer, NOT a security gate: it never rejects.
const THROTTLED_TOOLS: &[&str] = &["delete_node", "clear_scene", "save_scene", "delete_keyframes"];

/// Pure helper: how long (if at all) `call_one` must sleep before dispatching `name`, given the
/// throttle interval, the last destructive-action timestamp, and `now`. Returns `None` when the
/// throttle is off, the tool isn't destructive, there was no prior action, or enough time has already
/// elapsed. Kept pure so the pacing logic is unit-testable without a live dispatch.
fn throttle_delay(name: &str, min_interval_ms: u64, last: Option<Instant>, now: Instant) -> Option<Duration> {
    if min_interval_ms == 0 || !THROTTLED_TOOLS.contains(&name) {
        return None;
    }
    let interval = Duration::from_millis(min_interval_ms);
    let prev = last?; // the first destructive action is never delayed
    let elapsed = now.saturating_duration_since(prev);
    if elapsed < interval {
        Some(interval - elapsed)
    } else {
        None
    }
}

/// Handle `tools/call`. Returns `Ok(result)` where a tool-level failure (unknown tool, validation
/// rejection, executor error) is surfaced as an `isError: true` result the model can read and
/// react to — NOT a protocol error. Only a genuinely malformed request (`name` not a string) is a
/// JSON-RPC `-32602`.
///
/// `batch` is the ONE tool handled specially here: it validates its ops list (structurally) then runs
/// each op through `call_one` — the SAME lookup + `ToolDef::validate` + dispatch + audit path a direct
/// call takes. Every other tool (including each batch sub-op) goes through `call_one`, which is the
/// single choke point where the security invariants live.
async fn tools_call(
    params: &Value,
    working_dir: &RwLock<PathBuf>,
    exec: &Executor,
    ncfg: &NativeCfg,
    index: &HashMap<&str, &ToolDef>,
    audit: &AuditSink,
    last_action: &mut Option<Instant>,
) -> std::result::Result<Value, (i64, String)> {
    let name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or((-32602, "tools/call requires a string 'name'".to_string()))?;
    let arguments = params.get("arguments").cloned().unwrap_or(Value::Null);

    if name == "batch" {
        return run_batch(&arguments, working_dir, exec, ncfg, index, audit, last_action).await;
    }
    Ok(call_one(name, &arguments, working_dir, exec, ncfg, index, audit, last_action).await)
}

/// Run the `batch` meta-tool: validate the ops list via the batch `ToolDef` (structural gate — 1..64
/// ops, each `{name, arguments?}`, no nested `batch`), then dispatch each op through `call_one`, which
/// applies the full per-op validation + confinement + audit + throttle. Ops run in order; a failing op
/// stops the batch iff `stop_on_error`. Returns one text block whose payload is `{results:[{name, ok,
/// result|error}]}`, with `isError` true iff any op errored. Batching is a latency envelope only — it
/// grants no capability a direct call lacks.
async fn run_batch(
    arguments: &Value,
    working_dir: &RwLock<PathBuf>,
    exec: &Executor,
    ncfg: &NativeCfg,
    index: &HashMap<&str, &ToolDef>,
    audit: &AuditSink,
    last_action: &mut Option<Instant>,
) -> std::result::Result<Value, (i64, String)> {
    // Validate `batch`'s own args through its ToolDef — this is the structural ops-list check (and it
    // rejects a nested `batch` op). `batch` must be in the catalog.
    let Some(batch_def) = index.get("batch").copied() else {
        return Ok(tool_error("batch", audit, "internal error: 'batch' missing from catalog".to_string()));
    };
    // batch takes no filesystem paths, but validate needs a working dir; resolve it once for confinement
    // parity (sub-ops re-resolve their own fresh working dir inside call_one).
    let fallback = match working_dir.read() {
        Ok(g) => g.clone(),
        Err(_) => return Ok(tool_error("batch", audit, "internal error: working-dir lock poisoned".to_string())),
    };
    let wd = crate::config::resolve_working_dir(&fallback);
    let clean = match batch_def.validate(arguments, &wd) {
        Ok(v) => v,
        Err(e) => return Ok(tool_error("batch", audit, format!("invalid arguments: {e}"))),
    };

    let ops = clean.get("ops").and_then(Value::as_array).cloned().unwrap_or_default();
    let stop_on_error = clean.get("stop_on_error").and_then(Value::as_bool).unwrap_or(false);

    let mut results: Vec<Value> = Vec::with_capacity(ops.len());
    let mut any_error = false;
    for op in &ops {
        // Structure guaranteed by OpList validation: name is a non-empty, non-"batch" string.
        let op_name = op.get("name").and_then(Value::as_str).unwrap_or_default();
        let op_args = op.get("arguments").cloned().unwrap_or(Value::Null);
        let res = call_one(op_name, &op_args, working_dir, exec, ncfg, index, audit, last_action).await;
        let ok = !res.get("isError").and_then(Value::as_bool).unwrap_or(false);
        if !ok {
            any_error = true;
        }
        results.push(json!({ "name": op_name, "ok": ok, "result": res }));
        if stop_on_error && !ok {
            break;
        }
    }

    let payload = json!({ "results": results });
    let text = serde_json::to_string_pretty(&payload).unwrap_or_else(|_| payload.to_string());
    emit(audit, "batch", !any_error, format!("batch · {} op(s) · {} error(s)",
        ops.len(), results.iter().filter(|r| !r["ok"].as_bool().unwrap_or(false)).count()));
    Ok(json!({ "content": [{ "type": "text", "text": text }], "isError": any_error }))
}

/// Run ONE tool op end-to-end: lookup → `ToolDef::validate` (schema + clamp + path-confine) → optional
/// action-throttle for destructive tools → dispatch (native in-gateway, else the executor) → wrap as an
/// MCP result, emit the audit event, embed any inline image. This is the single security choke point;
/// both a direct `tools/call` and every `batch` sub-op funnel through here, so nothing can bypass the
/// gate by going through a batch. A tool-level failure returns an `isError: true` result (model-visible),
/// never a panic. `batch` is defensively refused here so it can never be reached as a sub-op (no nesting).
#[allow(clippy::too_many_arguments)]
async fn call_one(
    name: &str,
    arguments: &Value,
    working_dir: &RwLock<PathBuf>,
    exec: &Executor,
    ncfg: &NativeCfg,
    index: &HashMap<&str, &ToolDef>,
    audit: &AuditSink,
    last_action: &mut Option<Instant>,
) -> Value {
    // Defense in depth: `batch` is dispatched only by the special path in `tools_call`; if it ever
    // reaches here (e.g. as a sub-op) refuse it, so nesting is structurally impossible.
    if name == "batch" {
        return tool_error(name, audit, "'batch' cannot be invoked as a sub-op (no nesting)".to_string());
    }

    // Unknown tool → model-visible error (it can pick a real one).
    let Some(tool) = index.get(name).copied() else {
        return tool_error(name, audit, format!("unknown tool '{name}'"));
    };

    // Read the confinement root fresh, then validate + clamp + confine before anything reaches
    // Houdini. `~/.houdini-bridge-mcp/arm.json`'s `working_dir` is the single source of truth (written by
    // the GUI's Apply, live for THIS gateway AND the headless one); the process-start handle is the
    // fallback when arm.json is absent/invalid.
    let fallback = match working_dir.read() {
        Ok(g) => g.clone(),
        Err(_) => return tool_error(name, audit, "internal error: working-dir lock poisoned".to_string()),
    };
    let wd = crate::config::resolve_working_dir(&fallback);
    let clean = match tool.validate(arguments, &wd) {
        Ok(v) => v,
        Err(e) => return tool_error(name, audit, format!("invalid arguments: {e}")),
    };

    // Action throttle: PACE (never reject) destructive tools so a runaway/injection can't rapid-fire
    // scene-destroying calls. Off by default (`min_action_interval_ms == 0`); non-destructive tools are
    // never delayed. Applied right before dispatch, after validation, so a rejected call costs nothing.
    if let Some(remaining) = throttle_delay(name, ncfg.min_action_interval_ms, *last_action, Instant::now()) {
        tokio::time::sleep(remaining).await;
    }
    if ncfg.min_action_interval_ms > 0 && THROTTLED_TOOLS.contains(&name) {
        // Stamp AFTER any sleep so the next destructive op paces from when this one actually ran.
        *last_action = Some(Instant::now());
    }

    // Dispatch: native (gateway-local) tools run here; everything else goes to the executor.
    let outcome = if name == "acquire_terrain" {
        native::acquire_terrain(&clean, &wd, ncfg).await
    } else if name == "acquire_model" {
        native::acquire_model(&clean, &wd, ncfg).await
    } else if name == "node_reference" {
        native::node_reference(&clean, ncfg)
    } else if name == "vex_reference" {
        native::vex_reference(&clean, ncfg)
    } else if name == "recipe_reference" {
        native::recipe_reference(&clean, ncfg)
    } else if name == "capabilities" {
        native::capabilities(&clean, ncfg)
    } else {
        exec.call(name, clean).await
    };
    match outcome {
        Ok(result) => {
            let text = serde_json::to_string_pretty(&result).unwrap_or_else(|_| result.to_string());
            emit(audit, name, true, summarize(&result));
            let mut content = vec![json!({ "type": "text", "text": text })];
            // Inline-images: the "show me" tools return a confined PNG path — embed it as an MCP image
            // content block so the caller SEES it, not just a disk path. Only these tools are scanned;
            // the path is re-confined to the working dir + size-capped before any read (a non-existent
            // path, e.g. a flipbook $F sequence pattern, simply fails confinement and is skipped).
            if IMAGE_TOOLS.contains(&name) {
                if let Some(img) = try_embed_image(&result, &wd) {
                    content.push(img);
                }
            }
            json!({ "content": content, "isError": false })
        }
        Err(e) => tool_error(name, audit, e.to_string()),
    }
}

/// Tools whose result carries a PNG the caller should SEE inline.
const IMAGE_TOOLS: &[&str] = &["capture_ui", "snapshot", "flipbook"];
/// Cap embedded images so a huge render can't bloat the MCP response (~4 MB → ~5.3 MB base64).
const MAX_IMAGE_BYTES: u64 = 4_000_000;

/// If `result` carries an image path that confines under `wd` and is a small existing file, return an
/// MCP `image` content block (base64). Returns None on any miss — never fails the tool call.
fn try_embed_image(result: &Value, wd: &std::path::Path) -> Option<Value> {
    let raw = find_image_path(result)?;
    // Re-confine (read) against the working dir — rejects anything outside it or non-existent.
    let confined = crate::tools::confine_path(wd, &raw, false).ok()?;
    let meta = std::fs::metadata(&confined).ok()?;
    if !meta.is_file() || meta.len() == 0 || meta.len() > MAX_IMAGE_BYTES {
        return None;
    }
    let bytes = std::fs::read(&confined).ok()?;
    let mime = if raw.to_lowercase().ends_with(".png") { "image/png" } else { "image/jpeg" };
    Some(json!({ "type": "image", "data": base64_encode(&bytes), "mimeType": mime }))
}

/// First string value anywhere in the result that looks like an image path.
fn find_image_path(v: &Value) -> Option<String> {
    match v {
        Value::String(s) => {
            let l = s.to_lowercase();
            if l.ends_with(".png") || l.ends_with(".jpg") || l.ends_with(".jpeg") {
                Some(s.clone())
            } else {
                None
            }
        }
        Value::Object(m) => m.values().find_map(find_image_path),
        Value::Array(a) => a.iter().find_map(find_image_path),
        _ => None,
    }
}

/// Standard base64 (RFC 4648), inlined to avoid an extra crate dependency on the offline build.
fn base64_encode(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = *chunk.get(1).unwrap_or(&0) as u32;
        let b2 = *chunk.get(2).unwrap_or(&0) as u32;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(T[(n >> 18 & 63) as usize] as char);
        out.push(T[(n >> 12 & 63) as usize] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6 & 63) as usize] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[(n & 63) as usize] as char } else { '=' });
    }
    out
}

/// Build an `isError` tool result and record it in the audit log.
fn tool_error(name: &str, audit: &AuditSink, message: String) -> Value {
    emit(audit, name, false, message.clone());
    json!({ "content": [{ "type": "text", "text": message }], "isError": true })
}

fn emit(audit: &AuditSink, endpoint: &str, ok: bool, summary: String) {
    // A closed receiver (GUI gone) is not fatal to serving — just drop the line.
    let _ = audit.send(AuditEvent { endpoint: endpoint.to_string(), ok, summary: truncate(&summary, 200) });
}

/// A short one-line summary of a success payload for the audit log.
fn summarize(result: &Value) -> String {
    match result {
        Value::Object(m) => {
            let keys: Vec<&str> = m.keys().map(String::as_str).collect();
            format!("ok · {{{}}}", keys.join(", "))
        }
        Value::Null => "ok".to_string(),
        other => truncate(&other.to_string(), 120),
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let cut: String = s.chars().take(max).collect();
        format!("{cut}…")
    }
}

// ---- JSON-RPC envelope helpers ----

fn rpc_ok(id: Value, result: Value) -> Value {
    json!({ "jsonrpc": "2.0", "id": id, "result": result })
}

fn rpc_error(id: Value, code: i64, message: &str) -> Value {
    json!({ "jsonrpc": "2.0", "id": id, "error": { "code": code, "message": message } })
}

#[cfg(test)]
mod tests {
    use super::*;

    // The inbound memory-DoS guard: an over-cap frame is dropped (never buffered whole), and the
    // stream keeps serving — the frame AFTER the oversized one is still read intact.
    #[tokio::test]
    async fn capped_reader_drops_oversized_frame_and_recovers() {
        let big = "x".repeat(MAX_INBOUND_LINE_BYTES + 10);
        let input = format!("{{\"a\":1}}\n{{\"b\":2}}\n{big}\n{{\"c\":3}}\n");
        let mut reader = BufReader::new(input.as_bytes());
        let mut buf = Vec::new();

        assert!(matches!(read_capped_line(&mut reader, &mut buf).await.unwrap(), Frame::Line(l) if l == r#"{"a":1}"#));
        assert!(matches!(read_capped_line(&mut reader, &mut buf).await.unwrap(), Frame::Line(l) if l == r#"{"b":2}"#));
        assert!(matches!(read_capped_line(&mut reader, &mut buf).await.unwrap(), Frame::TooLong));
        assert!(matches!(read_capped_line(&mut reader, &mut buf).await.unwrap(), Frame::Line(l) if l == r#"{"c":3}"#));
        assert!(matches!(read_capped_line(&mut reader, &mut buf).await.unwrap(), Frame::Eof));
    }

    // A frame at exactly the cap is accepted; only strictly-over is rejected.
    #[tokio::test]
    async fn capped_reader_accepts_frame_at_limit() {
        let input = format!("{}\n", "y".repeat(MAX_INBOUND_LINE_BYTES));
        let mut reader = BufReader::new(input.as_bytes());
        let mut buf = Vec::new();
        assert!(matches!(read_capped_line(&mut reader, &mut buf).await.unwrap(),
                         Frame::Line(l) if l.len() == MAX_INBOUND_LINE_BYTES));
    }

    // ---- action-throttle pacing logic (pure helper `throttle_delay`) ----

    #[test]
    fn throttle_paces_destructive_but_not_normal() {
        let now = Instant::now();
        // Throttle OFF (interval 0) → never delays, even a destructive tool with a recent action.
        assert_eq!(throttle_delay("delete_node", 0, Some(now), now), None);

        // Throttle ON, but a NON-destructive tool is never delayed (batch-building stays fast).
        assert_eq!(throttle_delay("merge", 1000, Some(now), now), None);

        // Throttle ON, destructive tool, a prior action just happened → must sleep ~the full interval.
        let d = throttle_delay("delete_node", 1000, Some(now), now).expect("must delay");
        assert!(d > Duration::from_millis(500) && d <= Duration::from_millis(1000), "got {d:?}");

        // Destructive tool but the FIRST action (no prior timestamp) → no delay.
        assert_eq!(throttle_delay("save_scene", 1000, None, now), None);

        // Destructive tool but enough time already elapsed → no delay.
        let long_ago = now.checked_sub(Duration::from_secs(5)).unwrap();
        assert_eq!(throttle_delay("delete_keyframes", 1000, Some(long_ago), now), None);

        // All three destructive tools are recognized; a lookalike non-catalog name is not.
        for t in THROTTLED_TOOLS {
            assert!(throttle_delay(t, 1000, Some(now), now).is_some(), "{t} should be throttled");
        }
        assert_eq!(throttle_delay("delete_node_now", 1000, Some(now), now), None);
    }
}
