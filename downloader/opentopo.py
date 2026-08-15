"""OpenTopography globaldem API — the OPT-IN, keyed global lane.

The no-key lane (usgs_3dep / global_dem / state portals) already covers most of the planet at 30 m and
the US + a few countries at 1 m. This adds the ONE keyed source that unlocks 1-30 m DEM/LIDAR for the
rest of the world through a single free account: OpenTopography's `globaldem` API server-side-clips a
chosen global dataset to a bbox and returns one GeoTIFF. It is reached ONLY when the user has supplied
their own free API key (env `HMCP_OPENTOPO_KEY`) — so the default build stays no-key, and a user in
Japan / Australia / Iceland / South America can plug in a key to get their region.

Security: the key is a user secret. It is read from the environment (never a tool parameter, so the AI
never sees or transmits it), the host is only reached through this module's own allowlist, and the key
is REDACTED from every log line and error message (`_redact`) so it can't leak via the caller-facing
error path. The key travels in the query string because that is the API's documented design; we never
log or return a URL that still contains it.
"""

import os
import urllib.parse

from .net import download, EgressError
from .sources import OPENTOPO_HOSTS

_API = "https://portal.opentopography.org/API/globaldem"

# Friendly source id -> OpenTopography `demtype`. All are global (or continental) and unlocked by one key.
DEMTYPES = {
    "ot_aw3d30": "AW3D30",      # ALOS World 3D 30 m (JAXA) — geoid
    "ot_aw3d30e": "AW3D30_E",   # ALOS World 3D 30 m — ellipsoidal
    "ot_srtm1": "SRTMGL1",      # SRTM GL1 30 m
    "ot_srtm3": "SRTMGL3",      # SRTM GL3 90 m
    "ot_cop30": "COP30",        # Copernicus GLO-30
    "ot_cop90": "COP90",        # Copernicus GLO-90
    "ot_nasadem": "NASADEM",    # NASADEM 30 m (improved SRTM)
    "ot_eudtm": "EU_DTM",       # GEDTM / EU DTM (Europe)
    "ot_gedtm30": "GEDTM30",    # Global Ensemble DTM 30 m
}


def api_key():
    """The user's OpenTopography API key from the environment, or None (keyed lane simply stays off)."""
    return (os.environ.get("HMCP_OPENTOPO_KEY") or "").strip() or None


def _redact(text, key):
    """Remove the API key from any string before it is logged or returned to the caller."""
    if key and text:
        return text.replace(key, "***REDACTED***").replace(urllib.parse.quote(key), "***REDACTED***")
    return text


def globaldem_url(demtype, bbox, key, out_format="GTiff"):
    """Build the globaldem request URL. `bbox` = (min_lon, min_lat, max_lon, max_lat). `demtype` is the
    API token (e.g. 'AW3D30'). Callers must not log the returned URL (it carries the key)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    qs = urllib.parse.urlencode({
        "demtype": demtype,
        "south": min_lat, "north": max_lat, "west": min_lon, "east": max_lon,
        "outputFormat": out_format,
        "API_Key": key,
    })
    return "%s?%s" % (_API, qs)


def fetch_globaldem(source_or_demtype, bbox, dest_dir, key=None, max_bytes=500_000_000, timeout=300,
                    on_progress=None):
    """Fetch a bbox of a global dataset via the keyed API into dest_dir; return the .tif path.

    `source_or_demtype` accepts either a friendly id ('ot_aw3d30') or a raw API demtype ('AW3D30').
    Raises RuntimeError (key-redacted) if no key is configured or the request fails. The server clips to
    the bbox, so ONE request yields ONE GeoTIFF — no client-side tiling.
    """
    key = key or api_key()
    if not key:
        raise RuntimeError("OpenTopography keyed lane is off: set HMCP_OPENTOPO_KEY to a free API key "
                           "from opentopography.org to enable global keyed DEM access")
    demtype = DEMTYPES.get(source_or_demtype, source_or_demtype)
    min_lon, min_lat, max_lon, max_lat = bbox
    fname = "OT_%s_%.4f_%.4f_%.4f_%.4f.tif" % (demtype, min_lat, min_lon, max_lat, max_lon)
    dest = os.path.join(dest_dir, fname)
    url = globaldem_url(demtype, bbox, key)
    try:
        download(url, dest, OPENTOPO_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    except (EgressError, Exception) as exc:  # noqa: BLE001 — redact the key from WHATEVER surfaced
        raise RuntimeError("OpenTopography globaldem fetch failed (%s): %s"
                           % (demtype, _redact(str(exc), key))) from None
    return dest
