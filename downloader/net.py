"""Allowlisted, size-capped HTTP download — the single, guarded egress primitive.

Every fetch goes through `download()`, which enforces: https only, host in the caller's allowlist
(re-checked on every redirect hop so a redirect can't smuggle egress to an off-list host), a hard
byte cap (checked against Content-Length AND while streaming), a timeout, and atomic write
(.part → rename) so an interrupted download never leaves a half-file that looks complete.

Stdlib only (urllib) — no third-party dependency for the network layer.
"""

import ipaddress
import os
import socket
import urllib.parse
import urllib.request


class EgressError(Exception):
    """A request was refused by the egress guard (bad scheme, off-allowlist host, or too large)."""


def _addr_is_public(ip):
    """True only if `ip` is a normal routable public address. Rejects loopback / private / link-local /
    reserved / multicast / unspecified — so an allowlisted hostname whose DNS resolves to an INTERNAL
    target (DNS-rebinding / split-horizon) can't be used to reach the local network."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False  # unparseable -> refuse (fail-closed)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


def _host_ok(url, allow_hosts):
    p = urllib.parse.urlparse(url)
    if p.scheme != "https":
        raise EgressError(f"refusing non-https URL: {url}")
    host = (p.hostname or "").lower()
    if host not in allow_hosts:
        raise EgressError(f"host not in allowlist: {host!r}")
    # Defence-in-depth (SSRF/DNS-rebinding): even an allowlisted host must resolve to a PUBLIC address.
    # Resolves at check time AND on every redirect hop (redirect_request calls back here).
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise EgressError(f"cannot resolve host {host!r}: {exc}")
    for info in infos:
        ip = info[4][0]
        if not _addr_is_public(ip):
            raise EgressError(f"host {host!r} resolves to a non-public address {ip} (refused)")
    return host


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    """Re-validate the destination host on every redirect — the allowlist must hold across hops."""

    def __init__(self, allow_hosts):
        self.allow_hosts = allow_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _host_ok(newurl, self.allow_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, dest, allow_hosts, max_bytes=2_000_000_000, timeout=60, chunk=1 << 20, on_progress=None,
             user_agent=None):
    """Download `url` to `dest`, confined to `allow_hosts`, capped at `max_bytes`.

    Returns the number of bytes written. Raises EgressError on a guard violation, or the underlying
    URL/HTTP/OS error on a transport failure (the .part file is removed on failure).

    `user_agent` overrides the default UA for the (rare) allowlisted host whose WAF rejects a
    non-browser agent (e.g. Geoscience Australia's ArcGIS gateway). It changes only the request header,
    never the egress guard — the host must still be on `allow_hosts` and resolve to a public address.
    """
    _host_ok(url, allow_hosts)
    opener = urllib.request.build_opener(_AllowlistRedirect(allow_hosts))
    ua = user_agent or "houdini-bridge-mcp/0.1 (+elevation prep)"
    req = urllib.request.Request(url, headers={"User-Agent": ua})

    tmp = dest + ".part"
    total = 0
    try:
        with opener.open(req, timeout=timeout) as resp:
            clen = resp.headers.get("Content-Length")
            if clen is not None and int(clen) > max_bytes:
                raise EgressError(f"response Content-Length {clen} exceeds cap {max_bytes}")
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(tmp, "wb") as f:
                while True:
                    block = resp.read(chunk)
                    if not block:
                        break
                    total += len(block)
                    if total > max_bytes:
                        raise EgressError(f"stream exceeded cap {max_bytes} bytes")
                    f.write(block)
                    if on_progress:
                        on_progress(total, clen and int(clen))
        os.replace(tmp, dest)
        return total
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


_UA = {"User-Agent": "houdini-bridge-mcp/0.1 (+elevation prep)"}


def _guarded_opener(allow_hosts):
    return urllib.request.build_opener(_AllowlistRedirect(allow_hosts))


def get_json(url, allow_hosts, max_bytes=16_000_000, timeout=60):
    """Guarded GET of a JSON discovery/metadata endpoint. Same egress guard as `download` — https-only,
    host allowlist, per-redirect re-validation — plus a hard read cap so an oversized (or hostile)
    response can't exhaust memory via `json.load`. Returns the parsed JSON."""
    import json

    _host_ok(url, allow_hosts)
    req = urllib.request.Request(url, headers=_UA)
    with _guarded_opener(allow_hosts).open(req, timeout=timeout) as resp:
        clen = resp.headers.get("Content-Length")
        if clen is not None:
            try:
                clen_val = int(clen)
            except (ValueError, TypeError):
                # a malformed/hostile Content-Length must fail as an egress error, not leak a raw ValueError
                raise EgressError(f"discovery response has a non-integer Content-Length: {clen!r}")
            if clen_val > max_bytes:
                raise EgressError(f"discovery response Content-Length {clen} exceeds cap {max_bytes}")
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise EgressError(f"discovery response exceeded cap {max_bytes} bytes")
    return json.loads(data)


def head(url, allow_hosts, timeout=30):
    """Guarded HEAD request (allowlist + per-redirect re-validation) for an existence/size probe
    without downloading the body. Returns the response headers as a dict."""
    _host_ok(url, allow_hosts)
    req = urllib.request.Request(url, method="HEAD", headers=_UA)
    with _guarded_opener(allow_hosts).open(req, timeout=timeout) as resp:
        return {k: v for k, v in resp.headers.items()}


def safe_extractall(zip_path, dest_dir):
    """Extract every member of `zip_path` into `dest_dir`, validating each member path FIRST — reject
    absolute paths, drive letters, and `..` traversal — so a hostile archive can't write outside
    `dest_dir` (zip-slip). Does not rely on the stdlib's implicit sanitization. Returns the member
    count."""
    import zipfile

    dest = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        for name in members:
            if name.startswith("/") or name.startswith("\\") or (len(name) > 1 and name[1] == ":"):
                raise EgressError(f"zip member has an absolute path (rejected): {name!r}")
            target = os.path.abspath(os.path.join(dest, name))
            if target != dest and not target.startswith(dest + os.sep):
                raise EgressError(f"zip member escapes the destination (zip-slip, rejected): {name!r}")
        zf.extractall(dest)
    return len(members)
