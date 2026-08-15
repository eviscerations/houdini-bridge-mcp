"""Trusted ONNX-model downloader — the ONE model-acquisition egress lane for the ML/ONNX tools.

Mirrors the DEM downloader's discipline: egress is confined to a HuggingFace host allowlist
(`MODEL_HOSTS`), goes through the shared https-only, size-capped, redirect-checked `net.download`,
and there is **no arbitrary-URL path** — the caller supplies a repo id + filename + revision + a
**pinned sha256**, and the URL is constructed here. A hash mismatch deletes the file and fails. The
model lands under `<dest>/models/`, where the executor's `confined_path()` (working-dir confinement)
then resolves it for `onnx_inference` / `ml_volume_upres`.

CLI (invoked by the gateway's native `acquire_model`):
    python -m downloader.model --dest <dir> --repo <org/model> --file <name.onnx> \
        --sha256 <hex> [--revision main] [--max-bytes N]
Prints progress lines then a final single-line JSON object (last `{...}` line), like acquire.py.
"""

import argparse
import hashlib
import json
import os
import re
import sys

from downloader.net import download, EgressError

# --- the model-acquisition allowlist: HuggingFace + its LFS/Xet CDNs (redirect targets must be here,
# because net.download re-checks the host on every redirect hop). Fails CLOSED if HF adds a new CDN
# host — extend this set rather than widening to a wildcard. ------------------------------------------
MODEL_HOSTS = {
    "huggingface.co",                 # the resolve/ endpoint (302-redirects to a CDN below)
    "cdn-lfs.huggingface.co",         # classic LFS CDN
    "cdn-lfs-us-1.huggingface.co",    # regional LFS CDNs
    "cdn-lfs-eu-1.huggingface.co",
    "cas-bridge.xethub.hf.co",        # newer Xet-backed CDN
}

_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_REV_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def hf_url(repo, filename, revision="main"):
    """Construct the canonical HuggingFace resolve URL. Validates repo/revision/filename shape so a
    caller can neither smuggle another host nor traverse out of the repo path."""
    if not _REPO_RE.match(repo):
        raise ValueError("repo must look like 'org/model' (alnum . _ - only)")
    if not _REV_RE.match(revision):
        raise ValueError("revision has invalid characters")
    fn = filename.replace("\\", "/")
    if fn.startswith("/") or ".." in fn.split("/"):
        raise ValueError("filename must be a repo-relative path with no '..'")
    return "https://huggingface.co/%s/resolve/%s/%s" % (repo, revision, fn)


def _safe_local_name(repo, filename):
    """A flat, collision-resistant, traversal-proof local filename under <dest>/models/."""
    base = os.path.basename(filename.replace("\\", "/")) or "model.onnx"
    tag = re.sub(r"[^A-Za-z0-9._-]+", "_", repo)
    return "%s__%s" % (tag, base)


def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def acquire(dest, repo, filename, sha256, revision="main", max_bytes=2_000_000_000):
    """Download an HF model file into <dest>/models/, verify the pinned sha256, return a result dict.
    Raises EgressError / ValueError on a guard or integrity failure (the file is removed)."""
    if not _SHA_RE.match(sha256 or ""):
        raise ValueError("sha256 must be a 64-char hex digest (integrity pinning is required)")
    url = hf_url(repo, filename, revision)
    models_dir = os.path.join(os.path.abspath(dest), "models")
    out = os.path.join(models_dir, _safe_local_name(repo, filename))
    n = download(url, out, MODEL_HOSTS, max_bytes=max_bytes,
                 on_progress=lambda got, tot: print("  downloaded %d / %s bytes" % (got, tot), flush=True))
    got = _sha256(out)
    if got.lower() != sha256.lower():
        try:
            os.remove(out)
        except OSError:
            pass
        raise ValueError("sha256 mismatch: expected %s, got %s (file removed)" % (sha256, got))
    return {"ok": True, "repo": repo, "file": filename, "revision": revision,
            "path": out, "bytes": n, "sha256": got}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="downloader.model")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--revision", default="main")
    ap.add_argument("--max-bytes", type=int, default=2_000_000_000)
    a = ap.parse_args(argv)
    try:
        result = acquire(a.dest, a.repo, a.file, a.sha256, a.revision, a.max_bytes)
    except (EgressError, ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
