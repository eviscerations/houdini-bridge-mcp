//! Client to the in-Houdini Python executor over loopback. The gateway never talks to Houdini
//! directly — it goes through this typed client. There is NO raw-code path: only named endpoints
//! with validated params reach the executor.
//!
//! Wire contract (matches `houdini_executor/server.py`, verified against live H21.0.671):
//!   - `GET  /health`        — unauthenticated liveness; body `{"ok": true, ...}`.
//!   - `POST /tool/{name}`    — JSON body = params; auth header `X-HMCP-Token`.
//!       success        → 200 `{"ok": true,  "result": <value>}`
//!       handler error  → 400 `{"ok": false, "error": "<msg>"}`
//!       crash          → 500 `{"ok": false, "error": "<msg>", "traceback": "<tb>"}`
//!       dispatch error → 403/413/422 `{"error": "<msg>"}`  (bare, no `ok` field)
//!   - 1 MB body cap; 60 s main-thread timeout on the executor side.

use crate::config::Config;
use anyhow::{anyhow, Result};
use std::time::Duration;

/// The executor runs each handler on Houdini's single main thread with a 60 s timeout, so the
/// client must wait longer than that before giving up on a legitimately slow call.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(90);

pub struct Executor {
    base_url: String, // http://{host}:{port}
    token: String,
    http: reqwest::Client,
}

impl Executor {
    pub fn connect(cfg: &Config) -> Self {
        // A client-wide timeout that clears the executor's 60 s main-thread ceiling. `build()`
        // only fails on TLS/config init, which cannot happen for a plain loopback client, so a
        // fallback to the default client keeps `connect` infallible.
        let http = reqwest::Client::builder()
            .timeout(REQUEST_TIMEOUT)
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self {
            base_url: format!("http://{}:{}", cfg.executor_host, cfg.executor_port),
            token: cfg.token.clone(),
            http,
        }
    }

    /// `GET /health` — is the executor armed inside a live Houdini session, and which Houdini?
    /// Returns `(reachable, houdini_version)`. A transport error (nothing listening yet) is reported
    /// as `(false, None)` rather than an error, so the GUI shows a "disconnected" state instead of
    /// crashing while Houdini isn't up. The health body is
    /// `{"ok": true, "houdini": "21.0.671", ...}` (see `houdini_executor/server.py`).
    pub async fn health(&self) -> (bool, Option<String>) {
        let url = format!("{}/health", self.base_url);
        match self.http.get(&url).send().await {
            Ok(resp) => {
                let body: serde_json::Value = resp.json().await.unwrap_or(serde_json::Value::Null);
                let ok = body.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
                let ver = body.get("houdini").and_then(|v| v.as_str()).map(str::to_owned);
                (ok, ver)
            }
            Err(_) => (false, None),
        }
    }

    /// Invoke a typed endpoint by name with already-validated params. The gateway is responsible
    /// for schema validation, numeric clamps, and path/URL allowlisting BEFORE calling this.
    ///
    /// Returns the handler's `result` value on success; maps every executor-side failure (handler
    /// error, crash-with-traceback, or bare dispatch error) to an `Err` carrying the message.
    pub async fn call(&self, endpoint: &str, params: serde_json::Value) -> Result<serde_json::Value> {
        let url = format!("{}/tool/{}", self.base_url, endpoint);
        let resp = self
            .http
            .post(&url)
            .header("X-HMCP-Token", &self.token)
            .json(&params)
            .send()
            .await
            .map_err(|e| anyhow!("executor unreachable at {url}: {e}"))?;

        let status = resp.status();
        let body: serde_json::Value = resp.json().await.unwrap_or(serde_json::Value::Null);

        // Success envelope: {"ok": true, "result": <value>}.
        if body.get("ok").and_then(|v| v.as_bool()) == Some(true) {
            return Ok(body.get("result").cloned().unwrap_or(serde_json::Value::Null));
        }

        // Failure: handler-level `{"ok": false, "error": ...}` OR dispatch-level bare `{"error": ...}`.
        let msg = body
            .get("error")
            .and_then(|v| v.as_str())
            .map(str::to_owned)
            .unwrap_or_else(|| format!("executor returned HTTP {status} with no error message"));
        match body.get("traceback").and_then(|v| v.as_str()) {
            Some(tb) => Err(anyhow!("{endpoint} failed: {msg}\n--- executor traceback ---\n{tb}")),
            None => Err(anyhow!("{endpoint} failed: {msg}")),
        }
    }
}
