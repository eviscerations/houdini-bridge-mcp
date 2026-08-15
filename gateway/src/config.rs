//! Per-user configuration — the single source of truth for every path, host, and token the tool
//! uses. NOTHING here is hardcoded to a developer machine: the config file lives in the OS
//! per-user config directory (resolved via `dirs`), and the working directory is chosen by the
//! user on first run. This is the guarantee that no local file paths leak into shipped code.

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::SystemTime;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    /// The ONE directory the tool may read from and write to. Every executor file operation is
    /// `realpath`-confined under this root. Set by the user; never a shipped default path.
    pub working_dir: PathBuf,

    /// Loopback address of the in-Houdini executor.
    pub executor_host: String, // default "127.0.0.1"
    pub executor_port: u16,     // default 8765

    /// Session token shared with the executor. Generated per install; never committed.
    pub token: String,

    /// Logging on/off (mirrored by the GUI checkbox).
    pub logging_enabled: bool,

    /// Explicit Houdini install dir; auto-detected when None.
    pub houdini_dir: Option<PathBuf>,

    /// Command (executable + args) for the rasterio-capable Python that runs the downloader/prep,
    /// e.g. ["python"] or ["py","-3.14"] or ["C:/env/python.exe"]. Config-driven — never hardcoded.
    #[serde(default = "default_prep_python")]
    pub prep_python: Vec<String>,

    /// Directory containing the `downloader` Python package (the subprocess cwd for `-m
    /// downloader.acquire`). None = alongside the binary.
    #[serde(default)]
    pub downloader_root: Option<PathBuf>,

    /// Base URL of Houdini's local help server (`http://127.0.0.1:<port>/`), used by the GUI's
    /// "Open Houdini help" link. The port is chosen per Houdini session, so this is operator-set
    /// (the out-of-process GUI cannot read it from `hou`). None = the link is shown disabled.
    #[serde(default)]
    pub help_url: Option<String>,
}

fn default_prep_python() -> Vec<String> {
    vec!["python".to_string()]
}

/// SideFX's default local Houdini help-server base URL (port 48626 is hardcoded in
/// `houdinihelp/api.py`); used to pre-fill the GUI's "Open Houdini help" link.
pub const DEFAULT_HELP_URL: &str = "http://127.0.0.1:48626";

impl Config {
    /// Per-user config file path, e.g. `%APPDATA%\houdini-bridge-mcp\config.toml` on Windows —
    /// resolved at runtime, never hardcoded.
    fn config_path() -> Result<PathBuf> {
        let base = dirs::config_dir().context("no OS per-user config dir")?;
        Ok(base.join("houdini-bridge-mcp").join("config.toml"))
    }

    /// Load existing config, or run the first-run wizard to create it.
    ///
    /// ENV-FIRST: when launched embedded (e.g. by Claude Desktop, a packaged app whose child
    /// `%APPDATA%` is unreliable), the whole config is supplied via `HMCP_GW_*` env vars — no
    /// dependence on a config-file location. Setting `HMCP_GW_WORKING_DIR` selects this path.
    pub fn load_or_init() -> Result<Self> {
        if let Ok(working_dir) = std::env::var("HMCP_GW_WORKING_DIR") {
            return Ok(Self::from_env(PathBuf::from(working_dir)));
        }
        let path = Self::config_path()?;
        if path.exists() {
            let text = std::fs::read_to_string(&path)
                .with_context(|| format!("reading config at {}", path.display()))?;
            Ok(toml::from_str(&text)?)
        } else {
            let cfg = Self::first_run_wizard()?;
            cfg.save()?;
            Ok(cfg)
        }
    }

    pub fn save(&self) -> Result<()> {
        let path = Self::config_path()?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&path, toml::to_string_pretty(self)?)?;
        Ok(())
    }

    /// First run: pick a working directory, generate a token, (later) detect Houdini.
    /// Defaults are OS-relative (resolved at runtime), NOT developer paths. The GUI lets the
    /// user change the working directory before anything is read or written.
    fn first_run_wizard() -> Result<Self> {
        let working_dir = dirs::document_dir()
            .context("no OS documents dir")?
            .join("houdini-bridge-mcp");
        Ok(Self {
            working_dir,
            executor_host: "127.0.0.1".into(),
            executor_port: 8765,
            token: generate_token()?,
            logging_enabled: true,
            houdini_dir: None, // TODO: auto-detect from the registry / PATH
            prep_python: default_prep_python(),
            downloader_root: None,
            // 48626 is SideFX's hardcoded default help-server port (houdinihelp/api.py
            // startHelpServer(..., port=48626)); Houdini falls back to another port only if it's
            // taken. A good default for ~every install; the operator can override it in Settings.
            help_url: Some(DEFAULT_HELP_URL.to_string()),
        })
    }

    /// Build the whole config from `HMCP_GW_*` env vars (the embedded/packaged-launch path). Token
    /// is taken from env or freshly generated; prep_python is `;`-separated; unset optionals default.
    fn from_env(working_dir: PathBuf) -> Self {
        // RT-17a: FAIL-CLOSED on token generation. An empty token disables auth; refuse to arm instead
        // (a CSPRNG failure is near-impossible on Windows, so panicking here never fires in practice).
        let token = std::env::var("HMCP_GW_TOKEN").ok().filter(|s| !s.is_empty())
            .unwrap_or_else(|| generate_token()
                .expect("CSPRNG auth-token generation failed - refusing to arm without authentication"));
        let executor_port = std::env::var("HMCP_GW_PORT").ok()
            .and_then(|s| s.parse().ok()).unwrap_or(8765);
        let prep_python = std::env::var("HMCP_GW_PREP_PYTHON").ok()
            .map(|s| s.split(';').map(str::to_string).collect::<Vec<String>>())
            .unwrap_or_else(default_prep_python);
        let downloader_root = std::env::var("HMCP_GW_DOWNLOADER_ROOT").ok().map(PathBuf::from);
        // RT-17c: the executor transport is loopback-only by design (firewall-gated, token sent in
        // cleartext over it). A non-loopback HMCP_GW_HOST would leak the token to a LAN host, so clamp
        // it back to 127.0.0.1 with a warning rather than honor an off-box target.
        let executor_host = {
            let h = std::env::var("HMCP_GW_HOST").unwrap_or_else(|_| "127.0.0.1".into());
            if is_loopback_host(&h) {
                h
            } else {
                eprintln!("HMCP_GW_HOST={h:?} is not loopback; the executor transport is loopback-only \
                           (token sent in cleartext) - forcing 127.0.0.1");
                "127.0.0.1".into()
            }
        };
        Self {
            working_dir,
            executor_host,
            executor_port,
            token,
            logging_enabled: true,
            houdini_dir: None,
            prep_python,
            downloader_root,
            help_url: None,
        }
    }

    /// Environment handed to the executor when it arms, so the Python side also has NO hardcoded
    /// paths — it reads its confinement root, token, and port from here. Reserved for the auto-arm
    /// path (the binary launching/arming the executor); not yet called while arming is manual.
    #[allow(dead_code)]
    pub fn executor_env(&self) -> Vec<(String, String)> {
        vec![
            ("HMCP_WORKING_DIR".into(), self.working_dir.display().to_string()),
            ("HMCP_TOKEN".into(), self.token.clone()),
            ("HMCP_PORT".into(), self.executor_port.to_string()),
        ]
    }
}

// ────────────────────────────────────────────────────────────────────────────
// arm.json — the SINGLE SOURCE OF TRUTH for the confinement root.
//
// `~/.houdini-bridge-mcp/arm.json` is written by the GUI (auto-arm toggle + the Working-dir Apply button)
// and read here by BOTH the GUI's gateway and the headless (AI-facing) gateway. The GUI can thus
// drive the working directory live for every running gateway, with no env change and no restart.
// ────────────────────────────────────────────────────────────────────────────

/// Location of `~/.houdini-bridge-mcp/arm.json` — home dir via `dirs`, or `%USERPROFILE%` as a fallback.
/// Shared by the gateway reader and the GUI writer so both agree on the path.
pub fn arm_json_path() -> Option<PathBuf> {
    let home = dirs::home_dir().or_else(|| std::env::var_os("USERPROFILE").map(PathBuf::from))?;
    Some(home.join(".houdini-bridge-mcp").join("arm.json"))
}

/// mtime-keyed cache of the resolved arm.json working directory, so the hot path (every tool call)
/// avoids re-reading + re-canonicalizing on every request. Refreshes whenever the file's mtime
/// changes (i.e. right after the GUI writes it).
static WD_CACHE: Mutex<Option<(SystemTime, PathBuf)>> = Mutex::new(None);

/// The confinement ROOT for this call: `working_dir` from `~/.houdini-bridge-mcp/arm.json`, canonicalized
/// and confirmed to be a directory. On ANY failure (no file, unreadable, unparseable, missing key,
/// not-a-dir) falls back to `fallback` (the process-start `Config.working_dir`, kept live in the
/// GUI's shared handle). This is what makes the GUI's Apply reach the headless gateway too.
pub fn resolve_working_dir(fallback: &Path) -> PathBuf {
    arm_working_dir().unwrap_or_else(|| fallback.to_path_buf())
}

/// Read + parse + canonicalize the arm.json `working_dir`, using the mtime cache. `None` on any
/// failure so the caller can fall back. Never panics on a poisoned lock (treated as a cache miss).
fn arm_working_dir() -> Option<PathBuf> {
    let path = arm_json_path()?;
    let mtime = std::fs::metadata(&path).ok()?.modified().ok()?;

    // Cache hit: same mtime → reuse the resolved path (cheap fast path).
    if let Ok(guard) = WD_CACHE.lock() {
        if let Some((cached_mtime, cached_dir)) = guard.as_ref() {
            if *cached_mtime == mtime {
                return Some(cached_dir.clone());
            }
        }
    }

    // Cache miss: read, parse, canonicalize, validate — keep confinement semantics identical
    // (confine_path re-canonicalizes the root, so a `\\?\`-verbatim result here stays consistent).
    let text = std::fs::read_to_string(&path).ok()?;
    let value: serde_json::Value = serde_json::from_str(&text).ok()?;
    let raw = value.get("working_dir").and_then(|v| v.as_str())?;
    let canon = Path::new(raw).canonicalize().ok()?;
    if !canon.is_dir() {
        return None;
    }

    if let Ok(mut guard) = WD_CACHE.lock() {
        *guard = Some((mtime, canon.clone()));
    }
    Some(canon)
}

/// mtime-keyed cache of the parsed arm.json object, shared by the port/token resolvers so the GUI's
/// per-frame Settings display and the recurring health poll don't re-read + re-parse on every tick.
static ARM_CACHE: Mutex<Option<(SystemTime, serde_json::Value)>> = Mutex::new(None);

/// Read + parse `~/.houdini-bridge-mcp/arm.json` into a JSON value, using the mtime cache. `None` on ANY
/// failure (no file, unreadable, unparseable) so every caller can fall back to its Config value.
/// Same file-read/parse/cache approach as `arm_working_dir`, minus the working_dir canonicalization.
fn arm_value() -> Option<serde_json::Value> {
    let path = arm_json_path()?;
    let mtime = std::fs::metadata(&path).ok()?.modified().ok()?;

    // Cache hit: same mtime → reuse the parsed value.
    if let Ok(guard) = ARM_CACHE.lock() {
        if let Some((cached_mtime, cached_val)) = guard.as_ref() {
            if *cached_mtime == mtime {
                return Some(cached_val.clone());
            }
        }
    }

    // Cache miss: read + parse, then remember it against this mtime.
    let text = std::fs::read_to_string(&path).ok()?;
    let value: serde_json::Value = serde_json::from_str(&text).ok()?;
    if let Ok(mut guard) = ARM_CACHE.lock() {
        *guard = Some((mtime, value.clone()));
    }
    Some(value)
}

/// The executor PORT for this connection: `port` from `~/.houdini-bridge-mcp/arm.json` when present + valid,
/// else `fallback` (the process-start `Config.executor_port`). arm.json wins so the GUI hits the SAME
/// port the executor auto-armed on (e.g. 8766), not the 8765 Config default.
pub fn resolve_executor_port(fallback: u16) -> u16 {
    arm_value()
        .and_then(|v| v.get("port").and_then(|p| p.as_u64()))
        .and_then(|n| u16::try_from(n).ok())
        .unwrap_or(fallback)
}

/// The executor TOKEN for this connection: non-empty `token` from `~/.houdini-bridge-mcp/arm.json` when
/// present, else `fallback` (the process-start `Config.token`). arm.json wins so the GUI presents the
/// SAME secret the auto-armed executor expects.
pub fn resolve_token(fallback: &str) -> String {
    arm_value()
        .and_then(|v| v.get("token").and_then(|t| t.as_str()).map(str::to_owned))
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| fallback.to_string())
}

/// 128-bit hex session token from the OS CSPRNG.
fn generate_token() -> Result<String> {
    let mut buf = [0u8; 16];
    // `getrandom::Error` predates `std::error::Error` in 0.2, so map it into anyhow by hand.
    getrandom::getrandom(&mut buf).map_err(|e| anyhow!("CSPRNG failed: {e}"))?;
    Ok(buf.iter().map(|b| format!("{b:02x}")).collect())
}

/// True iff `host` is a loopback address or `localhost` (RT-17c: the executor transport is loopback-only;
/// a non-loopback host is refused so the cleartext token can't be sent off-box).
fn is_loopback_host(host: &str) -> bool {
    let h = host.trim();
    if h.eq_ignore_ascii_case("localhost") {
        return true;
    }
    let h = h.strip_prefix('[').and_then(|s| s.strip_suffix(']')).unwrap_or(h); // [::1] -> ::1
    h.parse::<std::net::IpAddr>().map(|ip| ip.is_loopback()).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::is_loopback_host;

    #[test]
    fn loopback_host_detection() {
        for ok in ["127.0.0.1", "127.5.6.7", "::1", "[::1]", "localhost", "LocalHost"] {
            assert!(is_loopback_host(ok), "{ok} should be treated as loopback");
        }
        for bad in ["192.168.1.5", "10.0.0.1", "0.0.0.0", "8.8.8.8", "example.com", ""] {
            assert!(!is_loopback_host(bad), "{bad} must NOT be treated as loopback");
        }
    }
}
