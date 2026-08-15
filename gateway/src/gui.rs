//! The GUI (egui/eframe) — the user's window into the running tool. Modeled on the SideFX
//! Houdini Launcher: near-black charcoal + SideFX-orange accent, an "Armed" status pill, a left
//! section-nav rail, and a live audit log. It owns the app lifecycle: it spawns the MCP gateway +
//! executor client on a background Tokio runtime and streams every call into the audit log.
//!
//! CONTROLS:
//!   1. Working-directory field — the ONE path the tool may touch; editing it (Apply) updates the
//!      confinement root live for every future call (shared `WorkingDir` handle).
//!   2. Logging on/off toggle.
//!   3. Live verbose audit log — every call the AI makes, in real time.
//!   4. Reload handlers  — hot-reload the executor's handler modules (Armed-pill menu).
//!   5. Auto-arm toggle  — writes ~/.houdini-bridge-mcp/arm.json so Houdini arms on launch (Settings).
//!   6. Install package  — copies the Houdini package into the user pref dir (Settings).

use crate::config::Config;
use crate::executor::Executor;
use crate::gateway::{self, AuditEvent, WorkingDir};
use crate::native::NativeCfg;
use anyhow::Result;
use egui::{Color32, RichText};
use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{Duration, SystemTime};

// ── Palette (SideFX-launcher dark) ───────────────────────────────────────────
/// Near-black window background (#1E1E1E).
const BG: Color32 = Color32::from_rgb(30, 30, 30);
/// Slightly lighter panel / card (#262626).
const PANEL: Color32 = Color32::from_rgb(38, 38, 38);
/// SideFX orange accent (#F5641E).
const ORANGE: Color32 = Color32::from_rgb(245, 100, 30);
/// Light-gray body text (#C8C8C8).
const TEXT: Color32 = Color32::from_rgb(200, 200, 200);
/// Muted gray for secondary text (#8A8A8A).
const MUTED: Color32 = Color32::from_rgb(138, 138, 138);
/// Sunken field background.
const SUNKEN: Color32 = Color32::from_rgb(24, 24, 24);
/// Field / card border.
const BORDER: Color32 = Color32::from_rgb(60, 60, 60);

// ── Footer links (kept as constants so they're easy to change) ───────────────
const URL_GITHUB: &str = "https://github.com/eviscerations/houdini-bridge-mcp";
const URL_HOWTO: &str = "https://github.com/eviscerations/houdini-bridge-mcp#readme";
const URL_SECURITY: &str = "https://github.com/eviscerations/houdini-bridge-mcp#security";
const URL_TROUBLE: &str = "https://github.com/eviscerations/houdini-bridge-mcp#troubleshooting";

/// Cap on the live audit log so a long session can't grow memory without bound.
const MAX_LOG: usize = 1000;
/// How often the background task re-checks the executor's health.
const HEALTH_INTERVAL: Duration = Duration::from_secs(2);

/// The allowlisted terrain data sources (read-only, shown in the Data sources tab).
const DATA_SOURCES: &[(&str, &str)] = &[
    ("USGS 3DEP (1/3 arc-second)", "National ~10 m elevation — the default DEM source."),
    ("USGS 1m LIDAR (TNM Access)", "1 m bare-earth LIDAR tiles via The National Map."),
    ("Copernicus GLO-30", "Global 30 m DEM from ESA Copernicus."),
    ("SRTM GL1", "SRTM 30 m global elevation."),
    ("Montana (MSL state library FTP)", "Montana State Library LIDAR / DEM FTP."),
    ("Washington (DNR LIDAR portal)", "WA Dept. of Natural Resources LIDAR portal."),
    ("Idaho (ISU GIS Center)", "Idaho State University GIS Center LIDAR."),
];

/// Which content pane the nav rail has selected.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Nav {
    Status,
    WorkingDir,
    AuditLog,
    DataSources,
    Settings,
}

const NAVS: &[(Nav, &str)] = &[
    (Nav::Status, "Status"),
    (Nav::WorkingDir, "Working dir"),
    (Nav::AuditLog, "Audit log"),
    (Nav::DataSources, "Data sources"),
    (Nav::Settings, "Settings"),
];

/// One rendered line in the live audit log (an `AuditEvent` stamped with a receipt time).
struct LogRow {
    endpoint: String,
    summary: String,
    ok: bool,
    ts: String,
}

struct App {
    config: Config,
    working_dir: WorkingDir, // shared with the running gateway
    working_dir_buf: String, // the editable text-field buffer
    dir_status: Option<String>, // feedback after an Apply
    nav: Nav,
    auto_arm: bool,
    allow_attrib_expr: bool, // safe-VEX (set_attrib_expr) gate, mirrored from arm.json
    allow_attrib_loops: bool, // validated-VEX bounded-loops gate, mirrored from arm.json
    allow_attrib_geoedit: bool, // validated-VEX geo_edit (removepoint/removeprim) gate, mirrored from arm.json
    allow_attrib_geogrow: bool, // validated-VEX geo_grow (addpoint/addprim/addvertex/removevertex) gate, mirrored from arm.json
    audit_rx: tokio::sync::mpsc::UnboundedReceiver<AuditEvent>,
    ui_tx: tokio::sync::mpsc::UnboundedSender<AuditEvent>, // GUI-originated lifecycle lines
    ui_rx: tokio::sync::mpsc::UnboundedReceiver<AuditEvent>,
    log_rx: tokio::sync::mpsc::UnboundedReceiver<AuditEvent>, // tailed from the headless gateway's log file
    help_url_buf: String, // editable buffer for the Houdini help-server URL
    audit_log: VecDeque<LogRow>,
    connected: Arc<AtomicBool>,
    houdini_version: Arc<RwLock<Option<String>>>,
    rt: tokio::runtime::Runtime, // kept alive so the spawned gateway/health tasks keep running
}

pub fn run(cfg: Config) -> Result<()> {
    // Shared confinement root: the GUI edits it, the gateway reads it per call.
    let working_dir: WorkingDir = Arc::new(RwLock::new(cfg.working_dir.clone()));
    let connected = Arc::new(AtomicBool::new(false));
    let houdini_version: Arc<RwLock<Option<String>>> = Arc::new(RwLock::new(None));
    let (audit_tx, audit_rx) = tokio::sync::mpsc::unbounded_channel::<AuditEvent>();
    let (ui_tx, ui_rx) = tokio::sync::mpsc::unbounded_channel::<AuditEvent>();
    let (log_tx, log_rx) = tokio::sync::mpsc::unbounded_channel::<AuditEvent>();

    let rt = tokio::runtime::Builder::new_multi_thread().enable_all().build()?;

    // 1) The MCP stdio gateway — the AI's sole entry point. Owns stdin/stdout.
    {
        let exec = Executor::connect(&cfg);
        let ncfg = Arc::new(NativeCfg::from_config(&cfg));
        let wd = working_dir.clone();
        rt.spawn(async move {
            if let Err(e) = gateway::serve(wd, exec, ncfg, audit_tx).await {
                tracing::error!("MCP gateway stopped: {e}");
            }
        });
    }

    // 2) A background health poll so the GUI can show connect state + the live Houdini version
    //    without blocking the UI thread. Re-resolves the arm.json port/token EACH tick (mtime-cached)
    //    so the poll hits the port the executor auto-armed on even if arm.json appears/changes after
    //    the GUI started — the fix for the pill reading "Disarmed" while polling the wrong port.
    {
        let base_cfg = cfg.clone();
        let connected = connected.clone();
        let hv = houdini_version.clone();
        rt.spawn(async move {
            loop {
                let exec = Executor::connect(&armed_config(&base_cfg));
                let (ok, ver) = exec.health().await;
                connected.store(ok, Ordering::Relaxed);
                if let Ok(mut g) = hv.write() {
                    *g = ver;
                }
                tokio::time::sleep(HEALTH_INTERVAL).await;
            }
        });
    }

    // 3) Tail the newest `houdini-bridge-mcp_*.log` in the working dir so the GUI shows the AI's REAL
    //    activity. The AI drives a SEPARATE headless gateway process; its audit lines land in that
    //    process's log file, never this GUI's in-memory channel — so without this tail the panel
    //    stays empty while Houdini is being driven. Follows the live working-dir + newest file.
    spawn_log_tailer(working_dir.clone(), log_tx, &rt);

    let app = App {
        working_dir_buf: cfg.working_dir.display().to_string(),
        auto_arm: read_arm_enabled(),
        allow_attrib_expr: read_allow_attrib_expr(),
        allow_attrib_loops: read_allow_attrib_loops(),
        allow_attrib_geoedit: read_allow_attrib_geoedit(),
        allow_attrib_geogrow: read_allow_attrib_geogrow(),
        help_url_buf: cfg.help_url.clone().unwrap_or_else(|| crate::config::DEFAULT_HELP_URL.to_string()),
        config: cfg,
        working_dir,
        dir_status: None,
        nav: Nav::Status,
        audit_rx,
        ui_tx,
        ui_rx,
        log_rx,
        audit_log: VecDeque::new(),
        connected,
        houdini_version,
        rt,
    };

    // Window / taskbar icon: the bridge logo (black silhouette on SideFX orange), baked into the
    // binary. Fail-soft — a decode failure just leaves the default icon.
    let mut viewport = egui::ViewportBuilder::default()
        .with_inner_size([880.0, 600.0])
        .with_min_inner_size([640.0, 460.0])
        .with_title("houdini-bridge-mcp");
    if let Ok(icon) = eframe::icon_data::from_png_bytes(include_bytes!("../assets/logo.png")) {
        viewport = viewport.with_icon(std::sync::Arc::new(icon));
    }
    let native_options = eframe::NativeOptions {
        viewport,
        ..Default::default()
    };

    eframe::run_native(
        "houdini-bridge-mcp",
        native_options,
        Box::new(|cc| {
            cc.egui_ctx.set_visuals(launcher_visuals());
            Ok(Box::new(app))
        }),
    )
    .map_err(|e| anyhow::anyhow!("GUI failed: {e}"))
}

/// Dark charcoal base with the orange accent — the Houdini-Launcher feel. Applied EVERY frame in
/// `update` (see the white-box fix note there), not just at startup.
fn launcher_visuals() -> egui::Visuals {
    let mut v = egui::Visuals::dark();
    v.panel_fill = BG;
    v.window_fill = BG;
    v.extreme_bg_color = SUNKEN;
    v.faint_bg_color = PANEL;
    v.override_text_color = Some(TEXT);
    v.hyperlink_color = ORANGE;
    v.selection.bg_fill = ORANGE.linear_multiply(0.4);
    v.selection.stroke = egui::Stroke::new(1.0, ORANGE);
    v.widgets.inactive.bg_fill = PANEL;
    v.widgets.inactive.weak_bg_fill = PANEL;
    v.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, ORANGE);
    v.widgets.active.bg_fill = Color32::from_rgb(48, 48, 48);
    v
}

impl App {
    /// Apply the working-dir text field to the shared confinement root + persist it. Also
    /// merge-writes `working_dir` into ~/.houdini-bridge-mcp/arm.json — the single source of truth the
    /// gateways read — so the change reaches BOTH this GUI's gateway and the headless (AI-facing)
    /// gateway live, without clobbering the auto-arm `enabled` flag.
    fn apply_working_dir(&mut self) {
        let new = PathBuf::from(self.working_dir_buf.trim());
        if !new.is_dir() {
            self.dir_status = Some(format!("⚠ not a directory: {}", new.display()));
            return;
        }
        if let Ok(mut guard) = self.working_dir.write() {
            *guard = new.clone();
        }
        self.config.working_dir = new.clone();
        match self.config.save() {
            Ok(()) => self.dir_status = Some("✓ working directory updated".into()),
            Err(e) => self.dir_status = Some(format!("saved in memory, but config write failed: {e}")),
        }
        // Publish to arm.json so every running gateway picks up the new root on its next call.
        match merge_write_arm(&self.config, serde_json::json!({ "working_dir": fwd(&new) })) {
            Ok(path) => self.note(true, "working-dir", format!("arm.json · {}", fwd(&path))),
            Err(e) => self.note(false, "working-dir", format!("arm.json write failed · {e}")),
        }
    }

    /// Push an audit line into the live log (stamped with the receipt time).
    fn push_event(&mut self, ev: AuditEvent) {
        self.audit_log.push_back(LogRow {
            endpoint: ev.endpoint,
            summary: ev.summary,
            ok: ev.ok,
            ts: now_hms(),
        });
        while self.audit_log.len() > MAX_LOG {
            self.audit_log.pop_front();
        }
    }

    /// Record a GUI-originated status line directly (we're on the UI thread).
    fn note(&mut self, ok: bool, endpoint: &str, summary: String) {
        self.push_event(AuditEvent { endpoint: endpoint.to_string(), ok, summary });
    }

    // ── (A) Reload handlers — POST /tool/reload off the UI thread ─────────────
    fn spawn_reload(&self) {
        let cfg = self.config.clone();
        let tx = self.ui_tx.clone();
        self.rt.spawn(async move {
            let exec = Executor::connect(&armed_config(&cfg));
            match exec.call("reload", serde_json::json!({})).await {
                Ok(v) => {
                    let n = v
                        .get("reloaded")
                        .and_then(|a| a.as_array())
                        .map(|a| a.len())
                        .unwrap_or(0);
                    let _ = tx.send(AuditEvent {
                        endpoint: "reload".into(),
                        ok: true,
                        summary: format!("{n} modules"),
                    });
                }
                Err(e) => {
                    let _ = tx.send(AuditEvent {
                        endpoint: "reload".into(),
                        ok: false,
                        summary: format!("failed · {e}"),
                    });
                }
            }
        });
    }

    /// Re-check connection now (one-shot health probe) and surface the result.
    fn spawn_recheck(&self) {
        let cfg = self.config.clone();
        let connected = self.connected.clone();
        let hv = self.houdini_version.clone();
        let tx = self.ui_tx.clone();
        self.rt.spawn(async move {
            let exec = Executor::connect(&armed_config(&cfg));
            let (ok, ver) = exec.health().await;
            connected.store(ok, Ordering::Relaxed);
            if let Ok(mut g) = hv.write() {
                *g = ver.clone();
            }
            let summary = if ok {
                format!("reachable · Houdini {}", ver.unwrap_or_else(|| "?".into()))
            } else {
                "not reachable".into()
            };
            let _ = tx.send(AuditEvent { endpoint: "health".into(), ok, summary });
        });
    }

    // ── Tear down (disarm) — POST /tool/teardown off the UI thread ─────────────
    // The executor is an independent server inside a user-launched Houdini; the GUI can only ask it
    // to stop over the authed loopback (it holds no process handle). `teardown` is a control-plane
    // endpoint (NOT in the MCP catalog), so only this GUI — never the AI — can reach it.
    fn spawn_teardown(&self) {
        let cfg = self.config.clone();
        let tx = self.ui_tx.clone();
        let connected = self.connected.clone();
        self.rt.spawn(async move {
            let exec = Executor::connect(&armed_config(&cfg));
            match exec.call("teardown", serde_json::json!({})).await {
                Ok(v) => {
                    let status =
                        v.get("status").and_then(|s| s.as_str()).unwrap_or("teardown scheduled");
                    // Optimistic: the 2 s health poll will confirm the executor went away.
                    connected.store(false, Ordering::Relaxed);
                    let _ = tx.send(AuditEvent {
                        endpoint: "teardown".into(),
                        ok: true,
                        summary: status.to_string(),
                    });
                }
                Err(e) => {
                    let _ = tx.send(AuditEvent {
                        endpoint: "teardown".into(),
                        ok: false,
                        summary: format!("failed · {e}"),
                    });
                }
            }
        });
    }

    // ── Harden network — shell scripts/harden-firewall.ps1 elevated (UAC) ──────
    fn spawn_harden(&mut self) {
        let root = resource_root(&self.config);
        let script = root.join("scripts").join("harden-firewall.ps1");
        if !script.exists() {
            self.note(false, "harden", format!("script not found · {}", fwd(&script)));
            return;
        }
        // Self-elevating: a non-admin GUI can't add a firewall rule, so relaunch the script via
        // Start-Process -Verb RunAs (Windows shows the UAC prompt the operator approves). Pass the
        // CONFIGURED executor port explicitly — the script defaults to 8766, so without this it would
        // harden the wrong port and the executor (on `executor_port`) would still refuse to arm.
        let inner = format!(
            "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{}','-Port','{}','-Mode','loopback'",
            script.display(),
            self.config.executor_port
        );
        match std::process::Command::new("powershell")
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &inner])
            .spawn()
        {
            Ok(_) => self.note(true, "harden", "firewall script launched — approve the UAC prompt".into()),
            Err(e) => self.note(false, "harden", format!("launch failed · {e}")),
        }
    }

    // ── (B) Auto-arm — merge-write `enabled` into ~/.houdini-bridge-mcp/arm.json ──────
    // MERGE, so toggling auto-arm never clobbers the working_dir the Apply button wrote.
    fn write_arm(&mut self, enabled: bool) {
        match merge_write_arm(&self.config, serde_json::json!({ "enabled": enabled })) {
            Ok(path) => self.note(
                true,
                "auto-arm",
                format!("{} · {}", if enabled { "enabled" } else { "disabled" }, fwd(&path)),
            ),
            Err(e) => self.note(false, "auto-arm", format!("write failed · {e}")),
        }
    }

    // ── (B2) safe-VEX gate — merge-write `allow_attrib_expr` into arm.json ────────
    // MERGE (same as auto-arm), so flipping the safe-VEX gate never clobbers working_dir/token/port.
    // The executor reads this flag FRESH per call (vexwrangle.py), so the change is live with no
    // restart. Operator-only surface: a driving agent has no path to this GUI, so it can never flip
    // its own code-execution gate — the human at the desk does, here or by hand-editing arm.json.
    fn write_allow_attrib_expr(&mut self, enabled: bool) {
        match merge_write_arm(&self.config, serde_json::json!({ "allow_attrib_expr": enabled })) {
            Ok(path) => self.note(
                true,
                "safe-vex",
                format!("{} · {}", if enabled { "enabled" } else { "disabled" }, fwd(&path)),
            ),
            Err(e) => self.note(false, "safe-vex", format!("write failed · {e}")),
        }
    }

    // ── validated-VEX bounded-loops gate — merge-write `allow_attrib_loops` into arm.json ──────────
    // Same MERGE + operator-only + read-fresh-per-call posture as write_allow_attrib_expr. The
    // executor reads this flag fresh (vexwrangle.py `_allow_attrib_loops`) so it's live with no restart.
    fn write_allow_attrib_loops(&mut self, enabled: bool) {
        match merge_write_arm(&self.config, serde_json::json!({ "allow_attrib_loops": enabled })) {
            Ok(path) => self.note(
                true,
                "safe-vex-loops",
                format!("{} · {}", if enabled { "enabled" } else { "disabled" }, fwd(&path)),
            ),
            Err(e) => self.note(false, "safe-vex-loops", format!("write failed · {e}")),
        }
    }

    // ── validated-VEX geo_edit gate — merge-write `allow_attrib_geoedit` into arm.json ────────────
    fn write_allow_attrib_geoedit(&mut self, enabled: bool) {
        match merge_write_arm(&self.config, serde_json::json!({ "allow_attrib_geoedit": enabled })) {
            Ok(path) => self.note(
                true,
                "safe-vex-geoedit",
                format!("{} · {}", if enabled { "enabled" } else { "disabled" }, fwd(&path)),
            ),
            Err(e) => self.note(false, "safe-vex-geoedit", format!("write failed · {e}")),
        }
    }

    // ── validated-VEX geo_grow gate — merge-write `allow_attrib_geogrow` into arm.json ────────────
    fn write_allow_attrib_geogrow(&mut self, enabled: bool) {
        match merge_write_arm(&self.config, serde_json::json!({ "allow_attrib_geogrow": enabled })) {
            Ok(path) => self.note(
                true,
                "validated-vex-geogrow",
                format!("{} · {}", if enabled { "enabled" } else { "disabled" }, fwd(&path)),
            ),
            Err(e) => self.note(false, "validated-vex-geogrow", format!("write failed · {e}")),
        }
    }

    // ── (B3) Reach arm.json — open the trust-root file / its folder in the OS ─────
    fn open_arm_json(&mut self) {
        // Guarantee the file exists first (merge-write with no changes creates a valid default on a
        // first run), then hand it to the OS default editor so any key can be hand-edited.
        match merge_write_arm(&self.config, serde_json::json!({})) {
            Ok(path) => match open_in_os(&path, false) {
                Ok(_) => self.note(true, "arm.json", format!("opened · {}", fwd(&path))),
                Err(e) => self.note(false, "arm.json", format!("open failed · {e}")),
            },
            Err(e) => self.note(false, "arm.json", format!("prepare failed · {e}")),
        }
    }

    fn open_config_folder(&mut self) {
        match crate::config::arm_json_path().and_then(|p| p.parent().map(Path::to_path_buf)) {
            Some(dir) => {
                let _ = std::fs::create_dir_all(&dir);
                match open_in_os(&dir, true) {
                    Ok(_) => self.note(true, "config-dir", format!("opened · {}", fwd(&dir))),
                    Err(e) => self.note(false, "config-dir", format!("open failed · {e}")),
                }
            }
            None => self.note(false, "config-dir", "no home directory".into()),
        }
    }

    // ── (C) Install Houdini package ───────────────────────────────────────────
    fn install_package(&mut self) {
        let root = resource_root(&self.config);
        let src_json = root.join("houdini_package").join("houdini-bridge-mcp.json");
        let src_py = root
            .join("houdini_package")
            .join("houdini-bridge-mcp")
            .join("scripts")
            .join("456.py");
        let pref = houdini_pref_dir();
        let dst_json = pref.join("packages").join("houdini-bridge-mcp.json");
        let dst_py = pref.join("houdini-bridge-mcp").join("scripts").join("456.py");
        let res = (|| -> std::io::Result<()> {
            copy_into(&src_json, &dst_json)?;
            copy_into(&src_py, &dst_py)?;
            Ok(())
        })();
        match res {
            Ok(()) => self.note(true, "install", format!("package → {}", fwd(&pref))),
            Err(e) => self.note(false, "install", format!("install failed · {e}")),
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // WHITE-BOX FIX: re-apply the dark visuals EVERY frame. eframe follows the OS theme and can
        // stomp the visuals set once in the creation closure with a light theme on the first frame
        // (which rendered the window as a bland white box). Setting them here, in `update`, runs
        // after eframe's theme application each frame, so the dark launcher theme always wins.
        ctx.set_visuals(launcher_visuals());

        // Drain new audit events into the ring buffer (MCP calls respect the logging toggle;
        // GUI-originated lifecycle lines always show).
        while let Ok(ev) = self.audit_rx.try_recv() {
            if self.config.logging_enabled {
                self.push_event(ev);
            }
        }
        while let Ok(ev) = self.ui_rx.try_recv() {
            self.push_event(ev);
        }
        // Real executor activity tailed from the headless gateway's log file — always shown
        // (it reflects what actually happened, independent of this GUI's own logging toggle).
        while let Ok(ev) = self.log_rx.try_recv() {
            self.push_event(ev);
        }

        let armed = self.connected.load(Ordering::Relaxed);
        let version = self.houdini_version.read().ok().and_then(|g| g.clone());

        // Intents collected from the (self-free) header, acted on after the panels close.
        let mut do_reload = false;
        let mut do_recheck = false;
        let mut do_teardown = false;
        let mut want_settings = false;

        egui::TopBottomPanel::top("header")
            .frame(egui::Frame::none().fill(PANEL).inner_margin(egui::Margin::symmetric(12.0, 8.0)))
            .show(ctx, |ui| {
                header_ui(ui, armed, &version, &mut do_reload, &mut do_recheck, &mut do_teardown, &mut want_settings);
            });

        egui::TopBottomPanel::bottom("footer")
            .frame(egui::Frame::none().fill(PANEL).inner_margin(egui::Margin::symmetric(12.0, 6.0)))
            .show(ctx, |ui| footer_ui(ui));

        egui::SidePanel::left("nav")
            .exact_width(150.0)
            .resizable(false)
            .frame(egui::Frame::none().fill(BG).inner_margin(egui::Margin::same(8.0)))
            .show(ctx, |ui| {
                ui.add_space(4.0);
                for (n, label) in NAVS {
                    if nav_item(ui, self.nav == *n, label) {
                        self.nav = *n;
                    }
                }
            });

        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(BG).inner_margin(egui::Margin::same(16.0)))
            .show(ctx, |ui| match self.nav {
                Nav::Status => self.ui_status(ui),
                Nav::WorkingDir => self.ui_working_dir(ui),
                Nav::AuditLog => self.ui_audit(ui),
                Nav::DataSources => self.ui_data_sources(ui),
                Nav::Settings => self.ui_settings(ui),
            });

        if want_settings {
            self.nav = Nav::Settings;
        }
        if do_reload {
            self.spawn_reload();
        }
        if do_recheck {
            self.spawn_recheck();
        }
        if do_teardown {
            self.spawn_teardown();
        }

        // Keep repainting so the live log and connection state stay current without user input.
        ctx.request_repaint_after(Duration::from_millis(400));
    }
}

// ── Content panes ────────────────────────────────────────────────────────────
impl App {
    fn ui_status(&mut self, ui: &mut egui::Ui) {
        section_label(ui, "SESSION");
        ui.add_space(8.0);
        ui.label(RichText::new("Working directory · the only path this tool may touch").strong().color(TEXT));
        ui.add_space(4.0);
        ui.horizontal(|ui| {
            boxed_field(ui, &self.config.working_dir.display().to_string(), 440.0);
            let _ = ui
                .add_enabled(false, egui::Button::new("📁"))
                .on_disabled_hover_text("Native folder picker not bundled — set the path in the Working dir tab");
        });

        ui.add_space(14.0);
        ui.horizontal(|ui| {
            let mut logging = self.config.logging_enabled;
            if toggle_switch(ui, &mut logging).changed() {
                self.config.logging_enabled = logging;
                let _ = self.config.save();
            }
            ui.add_space(6.0);
            ui.label(RichText::new("Logging").color(TEXT));
            ui.label(RichText::new("· record every call to the audit log").small().color(MUTED));
        });

        ui.add_space(14.0);
        ui.label(RichText::new("Live audit log").strong().color(TEXT));
        ui.add_space(4.0);
        render_audit(ui, &self.audit_log, Some(220.0));
    }

    fn ui_working_dir(&mut self, ui: &mut egui::Ui) {
        section_label(ui, "WORKING DIRECTORY");
        ui.add_space(8.0);
        ui.label(
            RichText::new(
                "Every file the tool reads or writes is confined under this one folder. Changing it \
                 takes effect immediately for all future calls.",
            )
            .color(MUTED),
        );
        ui.add_space(10.0);
        ui.add(
            egui::TextEdit::singleline(&mut self.working_dir_buf)
                .desired_width(520.0)
                .hint_text("C:\\path\\to\\your\\project"),
        );
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            if ui.button("Apply").clicked() {
                self.apply_working_dir();
            }
            if let Some(s) = &self.dir_status {
                ui.label(RichText::new(s).small().color(ORANGE));
            }
        });
    }

    fn ui_audit(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            section_label(ui, "AUDIT LOG");
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.button("Clear").clicked() {
                    self.audit_log.clear();
                }
                ui.label(RichText::new(format!("{} calls", self.audit_log.len())).small().color(MUTED));
            });
        });
        ui.add_space(6.0);
        if !self.config.logging_enabled {
            ui.label(RichText::new("logging paused").italics().color(MUTED));
        }
        render_audit(ui, &self.audit_log, None);
    }

    fn ui_data_sources(&mut self, ui: &mut egui::Ui) {
        section_label(ui, "DATA SOURCES");
        ui.add_space(6.0);
        ui.label(RichText::new("Downloads are restricted to these allowlisted hosts.").small().color(MUTED));
        ui.add_space(10.0);
        egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
            for (title, desc) in DATA_SOURCES {
                egui::Frame::none()
                    .fill(PANEL)
                    .rounding(egui::Rounding::same(6.0))
                    .inner_margin(egui::Margin::symmetric(10.0, 8.0))
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.label(RichText::new(*title).strong().color(TEXT));
                        ui.label(RichText::new(*desc).small().color(MUTED));
                    });
                ui.add_space(6.0);
            }
        });
    }

    fn ui_settings(&mut self, ui: &mut egui::Ui) {
        section_label(ui, "SETTINGS");
        ui.add_space(10.0);

        // Show the arm.json-resolved values (the port the executor auto-armed on, e.g. 8766), not
        // the Config default — falling back to Config when arm.json is absent/invalid.
        let port = crate::config::resolve_executor_port(self.config.executor_port);
        let token = crate::config::resolve_token(&self.config.token);

        ui.label(RichText::new("Executor port").strong().color(TEXT));
        boxed_field(ui, &port.to_string(), 120.0);
        ui.label(RichText::new("loopback port the in-Houdini executor listens on").small().color(MUTED));

        ui.add_space(12.0);
        ui.label(RichText::new("Session token").strong().color(TEXT));
        boxed_field(ui, &mask_token(&token), 260.0);
        ui.label(RichText::new("shared secret for loopback calls — never leaves this machine").small().color(MUTED));

        ui.add_space(16.0);
        ui.horizontal(|ui| {
            let mut a = self.auto_arm;
            if toggle_switch(ui, &mut a).changed() {
                self.auto_arm = a;
                self.write_arm(a);
            }
            ui.add_space(6.0);
            ui.label(RichText::new("Auto-arm Houdini").color(TEXT));
        });
        ui.label(
            RichText::new("writes ~/.houdini-bridge-mcp/arm.json so Houdini arms the executor on launch")
                .small()
                .color(MUTED),
        );

        ui.add_space(16.0);
        ui.label(RichText::new("Houdini help server").strong().color(TEXT));
        ui.label(
            RichText::new(
                "Houdini serves its full offline node/param reference over local HTTP. The port is \
                 chosen per session, so paste the base URL here (e.g. http://127.0.0.1:48626).",
            )
            .small()
            .color(MUTED),
        );
        ui.add_space(4.0);
        ui.horizontal(|ui| {
            ui.add(
                egui::TextEdit::singleline(&mut self.help_url_buf)
                    .desired_width(300.0)
                    .hint_text("http://127.0.0.1:<port>"),
            );
            if ui.button("Save").clicked() {
                let v = self.help_url_buf.trim();
                self.config.help_url = if v.is_empty() { None } else { Some(v.to_string()) };
                let _ = self.config.save();
                self.note(true, "help-url", "saved".into());
            }
            let url = self.help_url_buf.trim().to_string();
            let can_open = url.starts_with("http://") || url.starts_with("https://");
            if ui.add_enabled(can_open, egui::Button::new("Open help ↗")).clicked() {
                ui.ctx().open_url(egui::OpenUrl::new_tab(url));
            }
        });

        ui.add_space(16.0);
        ui.label(RichText::new("Validated VEX (advanced)").strong().color(TEXT));
        ui.horizontal(|ui| {
            let mut v = self.allow_attrib_expr;
            if toggle_switch(ui, &mut v).changed() {
                self.allow_attrib_expr = v;
                self.write_allow_attrib_expr(v);
            }
            ui.add_space(6.0);
            ui.label(RichText::new("Enable validated VEX (allow_attrib_expr)").color(TEXT));
        });
        ui.label(
            RichText::new(
                "Default OFF. When ON, the set_attrib_expr tool may run VALIDATED safe-subset VEX \
                 (no file / exec / system access) against your geometry — the one code-execution \
                 lane. Operator-only: a driving agent cannot flip this, only you can. Takes effect \
                 immediately (no restart). Writes allow_attrib_expr into ~/.houdini-bridge-mcp/arm.json.",
            )
            .small()
            .color(MUTED),
        );
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            let mut v = self.allow_attrib_loops;
            if toggle_switch(ui, &mut v).changed() {
                self.allow_attrib_loops = v;
                self.write_allow_attrib_loops(v);
            }
            ui.add_space(6.0);
            ui.label(RichText::new("Enable bounded loops (allow_attrib_loops)").color(TEXT));
        });
        ui.label(
            RichText::new(
                "Default OFF. When ON, validated VEX may use rigidly-bounded counted for-loops (fixed \
                 iteration ceiling) AND foreach over an array (finite: VEX snapshots the length at entry); \
                 while/do stay banned. A loop cooks like a hand-written one would — cost is surfaced, you \
                 fire the cook. Operator-only; live (no restart). Writes allow_attrib_loops into \
                 ~/.houdini-bridge-mcp/arm.json.",
            )
            .small()
            .color(MUTED),
        );
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            let mut v = self.allow_attrib_geoedit;
            if toggle_switch(ui, &mut v).changed() {
                self.allow_attrib_geoedit = v;
                self.write_allow_attrib_geoedit(v);
            }
            ui.add_space(6.0);
            ui.label(RichText::new("Enable geo delete (allow_attrib_geoedit)").color(TEXT));
        });
        ui.label(
            RichText::new(
                "Default OFF. When ON, validated VEX may DELETE topology (removepoint/removeprim) \
                 against input 0 only — deletion-only, self-bounding. Growth (add*) is a SEPARATE consent \
                 below. Operator-only; live (no restart). Writes allow_attrib_geoedit into \
                 ~/.houdini-bridge-mcp/arm.json.",
            )
            .small()
            .color(MUTED),
        );
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            let mut v = self.allow_attrib_geogrow;
            if toggle_switch(ui, &mut v).changed() {
                self.allow_attrib_geogrow = v;
                self.write_allow_attrib_geogrow(v);
            }
            ui.add_space(6.0);
            ui.label(RichText::new("Enable geo grow (allow_attrib_geogrow)").color(TEXT));
        });
        ui.label(
            RichText::new(
                "Default OFF. When ON, validated VEX may CONSTRUCT topology (addpoint/addprim/addvertex/ \
                 removevertex) on input 0 only. A SEPARATE consent from geo delete — enabling deletion \
                 does NOT grant growth. Growth is big-but-finite (adds are bounded by loop caps × \
                 elements), so a heavy build cooks slowly, not forever — you fire the cook. Operator-only; \
                 live (no restart). Writes allow_attrib_geogrow into ~/.houdini-bridge-mcp/arm.json.",
            )
            .small()
            .color(MUTED),
        );
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            if ui.button("Open arm.json").clicked() {
                self.open_arm_json();
            }
            if ui.button("Open config folder").clicked() {
                self.open_config_folder();
            }
        });
        ui.label(
            RichText::new(
                "arm.json is the trust root (working dir, token, port, flags) at \
                 ~/.houdini-bridge-mcp/arm.json — edit it by hand for anything not exposed here.",
            )
            .small()
            .color(MUTED),
        );

        ui.add_space(16.0);
        ui.label(RichText::new("Network").strong().color(TEXT));
        ui.label(
            RichText::new(
                "Add the Windows Firewall rule that scopes the executor port (loopback-only by \
                 default). Required before the executor will arm.",
            )
            .small()
            .color(MUTED),
        );
        ui.add_space(4.0);
        if ui.button("Harden network (firewall)").clicked() {
            self.spawn_harden();
        }

        ui.add_space(16.0);
        if ui.button("Install Houdini package").clicked() {
            self.install_package();
        }
        ui.label(
            RichText::new("copies houdini-bridge-mcp.json + 456.py into your Houdini user pref dir")
                .small()
                .color(MUTED),
        );
    }
}

// ── Header / footer / nav (self-free helpers) ────────────────────────────────
fn header_ui(
    ui: &mut egui::Ui,
    armed: bool,
    version: &Option<String>,
    do_reload: &mut bool,
    do_recheck: &mut bool,
    do_teardown: &mut bool,
    want_settings: &mut bool,
) {
    ui.horizontal(|ui| {
        // The "Armed" pill: orange when armed, gray when not.
        let pill_fill = if armed { ORANGE } else { Color32::from_rgb(64, 64, 64) };
        let on_pill = if armed { Color32::from_rgb(20, 20, 20) } else { TEXT };
        egui::Frame::none()
            .fill(pill_fill)
            .rounding(egui::Rounding::same(9.0))
            .inner_margin(egui::Margin::symmetric(10.0, 4.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.spacing_mut().item_spacing.y = 0.0;
                        let title = if armed { "Armed" } else { "Disarmed" };
                        ui.label(RichText::new(title).strong().color(on_pill));
                        let v = version
                            .clone()
                            .map(|s| format!("Houdini {s}"))
                            .unwrap_or_else(|| "— ".to_string());
                        let sub = if armed { Color32::from_rgb(70, 35, 15) } else { MUTED };
                        ui.label(RichText::new(v).small().color(sub));
                    });
                    ui.menu_button(RichText::new("▾").strong().color(on_pill), |ui| {
                        if ui.button("Reload handlers").clicked() {
                            *do_reload = true;
                            ui.close_menu();
                        }
                        if ui.button("Re-check connection").clicked() {
                            *do_recheck = true;
                            ui.close_menu();
                        }
                        ui.separator();
                        if ui
                            .add_enabled(armed, egui::Button::new(RichText::new("Tear down (disarm)").color(ORANGE)))
                            .on_hover_text(
                                "Ask the in-Houdini executor to stop its loopback server. Best-effort: \
                                 hwebserver may not release the port instantly, so wait a moment before re-arming.",
                            )
                            .clicked()
                        {
                            *do_teardown = true;
                            ui.close_menu();
                        }
                        let _ = ui.add_enabled(
                            false,
                            egui::Button::new(RichText::new("Executor · loopback only").small()),
                        );
                    });
                });
            });

        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if ui.button(RichText::new("⚙").size(16.0)).on_hover_text("Settings").clicked() {
                *want_settings = true;
            }
            ui.add_space(2.0);
            ui.label(RichText::new("executor · loopback").color(MUTED));
            let dot = if armed {
                Color32::from_rgb(70, 200, 90)
            } else {
                Color32::from_rgb(120, 120, 120)
            };
            ui.colored_label(dot, "●");
        });
    });
}

fn footer_ui(ui: &mut egui::Ui) {
    ui.columns(4, |c| {
        footer_link(&mut c[0], "HOW-TO", URL_HOWTO);
        footer_link(&mut c[1], "SECURITY", URL_SECURITY);
        footer_link(&mut c[2], "TROUBLESHOOTING", URL_TROUBLE);
        footer_link(&mut c[3], "GITHUB", URL_GITHUB);
    });
}

fn footer_link(ui: &mut egui::Ui, text: &str, url: &str) {
    ui.vertical_centered(|ui| {
        let resp = ui.add(
            egui::Label::new(RichText::new(text).color(ORANGE).strong().small())
                .sense(egui::Sense::click()),
        );
        if resp.hovered() {
            ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
        }
        if resp.clicked() {
            ui.ctx().open_url(egui::OpenUrl::new_tab(url));
        }
    });
}

/// A vertical nav row with an orange left-border highlight when active. Returns `true` on click.
fn nav_item(ui: &mut egui::Ui, active: bool, label: &str) -> bool {
    let resp = ui.add_sized(
        [ui.available_width(), 30.0],
        egui::SelectableLabel::new(active, RichText::new(label).color(if active { ORANGE } else { TEXT })),
    );
    if active {
        let r = resp.rect;
        let bar = egui::Rect::from_min_size(r.left_top(), egui::vec2(3.0, r.height()));
        ui.painter().rect_filled(bar, egui::Rounding::ZERO, ORANGE);
    }
    resp.clicked()
}

// ── Small reusable widgets ───────────────────────────────────────────────────
/// A small caps-ish section label in muted gray.
fn section_label(ui: &mut egui::Ui, text: &str) {
    ui.label(RichText::new(text).small().strong().color(MUTED));
}

/// A read-only, boxed (sunken) monospace value field.
fn boxed_field(ui: &mut egui::Ui, text: &str, min_width: f32) {
    egui::Frame::none()
        .fill(SUNKEN)
        .rounding(egui::Rounding::same(4.0))
        .stroke(egui::Stroke::new(1.0, BORDER))
        .inner_margin(egui::Margin::symmetric(8.0, 5.0))
        .show(ui, |ui| {
            ui.set_min_width(min_width);
            ui.label(RichText::new(text).monospace().color(TEXT));
        });
}

/// A compact orange on/off switch (self-contained — no extra deps). Returns the `Response`
/// (`.changed()` fires on toggle).
fn toggle_switch(ui: &mut egui::Ui, on: &mut bool) -> egui::Response {
    let desired = egui::vec2(34.0, 18.0);
    let (rect, mut resp) = ui.allocate_exact_size(desired, egui::Sense::click());
    if resp.clicked() {
        *on = !*on;
        resp.mark_changed();
    }
    let t = ui.ctx().animate_bool(resp.id, *on);
    let radius = 0.5 * rect.height();
    let bg = if *on { ORANGE } else { Color32::from_rgb(80, 80, 80) };
    ui.painter().rect_filled(rect, egui::Rounding::same(radius), bg);
    let cx = egui::lerp((rect.left() + radius)..=(rect.right() - radius), t);
    ui.painter()
        .circle_filled(egui::pos2(cx, rect.center().y), radius - 2.5, Color32::WHITE);
    resp
}

/// Render the audit log: a colored dot, the tool name, `→`, a short detail, and a right-aligned
/// timestamp per row. `max_height` bounds the mini-log on the Status pane.
fn render_audit(ui: &mut egui::Ui, rows: &VecDeque<LogRow>, max_height: Option<f32>) {
    let mut area = egui::ScrollArea::vertical().auto_shrink([false, false]).stick_to_bottom(true);
    if let Some(h) = max_height {
        area = area.max_height(h);
    }
    area.show(ui, |ui| {
        if rows.is_empty() {
            ui.add_space(8.0);
            ui.label(RichText::new("No calls yet. Connect your AI client and drive Houdini.").color(MUTED));
            return;
        }
        for r in rows {
            ui.horizontal(|ui| {
                let dot = if r.ok {
                    Color32::from_rgb(70, 200, 90)
                } else {
                    Color32::from_rgb(220, 90, 80)
                };
                ui.colored_label(dot, "●");
                ui.label(RichText::new(&r.endpoint).monospace().strong().color(ORANGE));
                ui.label(RichText::new("→").color(MUTED));
                ui.label(RichText::new(&r.summary).monospace().color(TEXT));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(RichText::new(&r.ts).small().color(MUTED));
                });
            });
        }
    });
}

// ── Free helpers ─────────────────────────────────────────────────────────────
/// A `Config` clone whose executor port + token are single-sourced from `~/.houdini-bridge-mcp/arm.json`
/// (falling back to the stored Config when arm.json is absent/invalid). Every GUI→executor client is
/// built through this so the GUI always talks to the port the executor auto-armed on (e.g. 8766),
/// never the 8765 Config default. The working_dir the gateway confines to already single-sources from
/// arm.json via `resolve_working_dir`, so this closes the loop for port + token.
fn armed_config(cfg: &Config) -> Config {
    let mut c = cfg.clone();
    c.executor_port = crate::config::resolve_executor_port(cfg.executor_port);
    c.token = crate::config::resolve_token(&cfg.token);
    c
}

/// Path → forward-slash string (arm.json / audit lines want portable slashes).
/// Locate the directory holding the bundled resources (`scripts/`, `houdini_package/`). Robust to
/// both layouts: dev (exe deep under `<repo>/gateway/target/release/`, resources at the repo root)
/// and a flat distribution (exe next to the resources). Walks up from the exe looking for the marker
/// dirs, then falls back to the configured `downloader_root`, then the cwd.
fn resource_root(cfg: &Config) -> PathBuf {
    let has_markers = |d: &Path| d.join("houdini_package").is_dir() && d.join("scripts").is_dir();
    if let Ok(exe) = std::env::current_exe() {
        let mut cur = exe.parent();
        for _ in 0..6 {
            match cur {
                Some(dir) if has_markers(dir) => return dir.to_path_buf(),
                Some(dir) => cur = dir.parent(),
                None => break,
            }
        }
    }
    if let Some(r) = &cfg.downloader_root {
        if has_markers(r) {
            return r.clone();
        }
    }
    std::env::current_dir().unwrap_or_default()
}

fn fwd(p: &Path) -> String {
    p.display().to_string().replace('\\', "/")
}

/// Merge-write `~/.houdini-bridge-mcp/arm.json`: load the existing object (if any), apply `updates` over
/// it, filling any still-missing keys from `cfg`, then write it back pretty-printed. This is the ONE
/// writer both callers share — the auto-arm toggle passes `{enabled}`, the Apply button passes
/// `{working_dir}`, and neither clobbers the other's field. Returns the written path.
fn merge_write_arm(cfg: &Config, updates: serde_json::Value) -> std::io::Result<PathBuf> {
    let path = crate::config::arm_json_path()
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::NotFound, "no home directory"))?;

    // Start from the existing file when present + valid, else an empty object.
    let mut obj = std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default();

    // Fill any key not already present (first-time creation) from the current config.
    // executor_root is DERIVED (the repo/deploy root that holds houdini_executor), not user config,
    // so resolve it from the exe location and ALWAYS write it — otherwise a stale/empty value in an
    // existing arm.json would stick and the in-Houdini executor would refuse to arm.
    let executor_root = resource_root(cfg);
    obj.entry("enabled").or_insert(serde_json::json!(false));
    obj.entry("working_dir").or_insert(serde_json::json!(fwd(&cfg.working_dir)));
    obj.entry("token").or_insert(serde_json::json!(cfg.token));
    obj.entry("port").or_insert(serde_json::json!(cfg.executor_port));
    obj.insert("executor_root".to_string(), serde_json::json!(fwd(&executor_root)));

    // Apply the explicit updates last, so they win over the fill-ins above.
    if let Some(u) = updates.as_object() {
        for (k, v) in u {
            obj.insert(k.clone(), v.clone());
        }
    }

    if let Some(p) = path.parent() {
        std::fs::create_dir_all(p)?;
    }
    let text = serde_json::to_string_pretty(&serde_json::Value::Object(obj)).unwrap_or_default();
    std::fs::write(&path, text)?;
    Ok(path)
}

/// Copy `src` → `dst`, creating the destination's parent directories first.
fn copy_into(src: &Path, dst: &Path) -> std::io::Result<()> {
    if let Some(p) = dst.parent() {
        std::fs::create_dir_all(p)?;
    }
    std::fs::copy(src, dst)?;
    Ok(())
}

/// The Houdini user pref dir: `HOUDINI_USER_PREF_DIR` if set, else `<USERPROFILE>/Documents/houdini21.0`.
fn houdini_pref_dir() -> PathBuf {
    if let Ok(p) = std::env::var("HOUDINI_USER_PREF_DIR") {
        if !p.is_empty() {
            return PathBuf::from(p);
        }
    }
    let home = std::env::var("USERPROFILE")
        .ok()
        .map(PathBuf::from)
        .or_else(dirs::home_dir)
        .unwrap_or_default();
    home.join("Documents").join("houdini21.0")
}

/// Mask a token for display: first 4 + bullets + last 4.
fn mask_token(t: &str) -> String {
    if t.len() <= 8 {
        "•".repeat(t.len().max(4))
    } else {
        format!("{}{}{}", &t[..4], "•".repeat(t.len() - 8), &t[t.len() - 4..])
    }
}

/// Read the current auto-arm state from `~/.houdini-bridge-mcp/arm.json` (default `false`).
fn read_arm_enabled() -> bool {
    crate::config::arm_json_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get("enabled").and_then(|b| b.as_bool()))
        .unwrap_or(false)
}

/// Read the current safe-VEX gate (`allow_attrib_expr`) from arm.json — the SAME key + default the
/// executor reads (vexwrangle.py `_allow_attrib_expr`), so the GUI toggle mirrors live state.
fn read_allow_attrib_expr() -> bool {
    crate::config::arm_json_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get("allow_attrib_expr").and_then(|b| b.as_bool()))
        .unwrap_or(false)
}

/// Read the bounded-loops gate (`allow_attrib_loops`) from arm.json — same key + default the executor
/// reads (vexwrangle.py `_allow_attrib_loops`), so the GUI toggle mirrors live state.
fn read_allow_attrib_loops() -> bool {
    crate::config::arm_json_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get("allow_attrib_loops").and_then(|b| b.as_bool()))
        .unwrap_or(false)
}

/// Read the geo_edit gate (`allow_attrib_geoedit`) from arm.json — same key + default the executor
/// reads (vexwrangle.py `_allow_attrib_geoedit`), so the GUI toggle mirrors live state.
fn read_allow_attrib_geoedit() -> bool {
    crate::config::arm_json_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get("allow_attrib_geoedit").and_then(|b| b.as_bool()))
        .unwrap_or(false)
}

/// Read the geo_grow gate (`allow_attrib_geogrow`) from arm.json — same key + default the executor
/// reads (vexwrangle.py `_allow_attrib_geogrow`), so the GUI toggle mirrors live state.
fn read_allow_attrib_geogrow() -> bool {
    crate::config::arm_json_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get("allow_attrib_geogrow").and_then(|b| b.as_bool()))
        .unwrap_or(false)
}

/// Open a file (default handler) or a folder (file manager) with the OS. Fire-and-forget — we
/// `spawn` and never wait, so a launcher's own exit code (explorer.exe returns non-zero even on
/// success) is irrelevant. Windows-first; a POSIX fallback keeps non-Windows dev builds honest.
fn open_in_os(path: &Path, is_dir: bool) -> std::io::Result<()> {
    use std::process::Command;
    #[cfg(windows)]
    {
        if is_dir {
            Command::new("explorer").arg(path).spawn().map(|_| ())
        } else {
            // `cmd /C start "" "<file>"` launches the file's default app; the empty "" is start's
            // (otherwise-swallowed) window-title argument, required when the target path is quoted.
            Command::new("cmd").args(["/C", "start", ""]).arg(path).spawn().map(|_| ())
        }
    }
    #[cfg(not(windows))]
    {
        let _ = is_dir;
        Command::new("xdg-open").arg(path).spawn().map(|_| ())
    }
}

/// Tail the newest `houdini-bridge-mcp_*.log` in the (live) working dir and forward its audit + error
/// lines as `AuditEvent`s. This is the fix for the empty-panel bug: the AI drives a SEPARATE
/// headless gateway process whose calls are written to that process's log file (`main.rs`
/// `init_logging`), not to this GUI's in-memory audit channel. Re-resolves the working dir + the
/// newest file each tick, so it follows a working-dir change or a freshly-launched headless gateway,
/// and reads only up to the last complete line (a trailing partial line waits for the next tick).
fn spawn_log_tailer(
    working_dir: WorkingDir,
    tx: tokio::sync::mpsc::UnboundedSender<AuditEvent>,
    rt: &tokio::runtime::Runtime,
) {
    use std::io::{Read, Seek, SeekFrom};
    rt.spawn(async move {
        let mut cur: Option<PathBuf> = None;
        let mut offset: u64 = 0;
        loop {
            let dir = working_dir.read().ok().map(|g| g.clone()).unwrap_or_default();
            let newest = newest_log(&dir);
            if newest != cur {
                cur = newest;
                offset = 0; // a new file (headless relaunch / dir change) → read from its start
            }
            if let Some(path) = &cur {
                if let Ok(meta) = std::fs::metadata(path) {
                    let len = meta.len();
                    if len < offset {
                        offset = 0; // rotated / truncated
                    }
                    if len > offset {
                        if let Ok(mut f) = std::fs::File::open(path) {
                            if f.seek(SeekFrom::Start(offset)).is_ok() {
                                let mut bytes = Vec::new();
                                if f.take(len - offset).read_to_end(&mut bytes).is_ok() {
                                    if let Some(last_nl) = bytes.iter().rposition(|&b| b == b'\n') {
                                        let text = String::from_utf8_lossy(&bytes[..=last_nl]);
                                        for line in text.lines() {
                                            if let Some(ev) = parse_log_line(line) {
                                                let _ = tx.send(ev);
                                            }
                                        }
                                        offset += (last_nl + 1) as u64;
                                    }
                                }
                            }
                        }
                    }
                }
            }
            tokio::time::sleep(Duration::from_millis(600)).await;
        }
    });
}

/// The `houdini-bridge-mcp_*.log` in `dir` with the most recent mtime (the actively-written one), if any.
fn newest_log(dir: &Path) -> Option<PathBuf> {
    let mut best: Option<(SystemTime, PathBuf)> = None;
    for entry in std::fs::read_dir(dir).ok()?.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with("houdini-bridge-mcp_") && name.ends_with(".log") {
            if let Ok(mt) = entry.metadata().and_then(|m| m.modified()) {
                if best.as_ref().map_or(true, |(bt, _)| mt > *bt) {
                    best = Some((mt, entry.path()));
                }
            }
        }
    }
    best.map(|(_, p)| p)
}

/// Parse one log line into an `AuditEvent`, or `None` to ignore it. Recognizes the headless
/// gateway's audit lines (`… audit: OK <endpoint> — <summary>` / `ERR …`, emitted by
/// `run_headless`) and surfaces gateway ERROR lines so a crash isn't invisible in the window.
fn parse_log_line(line: &str) -> Option<AuditEvent> {
    if let Some(idx) = line.find("audit: ") {
        let rest = &line[idx + "audit: ".len()..];
        let (ok, tail) = if let Some(t) = rest.strip_prefix("OK ") {
            (true, t)
        } else if let Some(t) = rest.strip_prefix("ERR ") {
            (false, t)
        } else {
            (true, rest)
        };
        let (endpoint, summary) = match tail.split_once(" — ") {
            Some((e, s)) => (e.trim().to_string(), s.trim().to_string()),
            None => (tail.trim().to_string(), String::new()),
        };
        return Some(AuditEvent { endpoint, ok, summary });
    }
    if line.contains(" ERROR ") {
        let msg = line.rsplit_once(": ").map(|(_, m)| m).unwrap_or(line).trim();
        return Some(AuditEvent { endpoint: "error".into(), ok: false, summary: msg.to_string() });
    }
    None
}

/// A wall-clock HH:MM:SS stamp for audit rows (UTC; no chrono dependency).
fn now_hms() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let s = secs % 86_400;
    format!("{:02}:{:02}:{:02}", s / 3600, (s % 3600) / 60, s % 60)
}
