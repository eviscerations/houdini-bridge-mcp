"""National high-resolution DEM portals — anonymous, no key, bare-earth DTM by bbox.

Each source returns a bare-earth terrain GeoTIFF for a lat/lon bbox from a national open OGC service in a
single guarded GET. The server reprojects (from EPSG:4326) and clips, so the FETCH LAYER STAYS STDLIB-ONLY
(no pyproj/rasterio here — those live in the prep step inside Houdini). Every endpoint + request shape was
verified live against the real portal. These sit ABOVE the global 30 m fallback (Copernicus/AW3D30/SRTM):
they cover one country each at 0.5-5 m; elsewhere the tool falls back to the global sources.

Coverage today: Netherlands (0.5 m), UK/England (1 m), France (1 m; 0.5 m LIDAR HD), Spain (5 m). More
national portals are added here as they are verified anonymous. Australia (ArcGIS WCS, finicky) and the
COG-windowed sources (Canada HRDEM, New Zealand) are deferred to a later pass.
"""

import math

from .net import download
from .sources import NATIONAL_DEM_HOSTS

_UA_NOTE = "elevation prep"  # download() sets the User-Agent; national portals accept the default.

# Geoscience Australia's ArcGIS gateway sits behind a WAF that 403s a non-browser User-Agent, so the
# AU fetchers pass a browser UA to download() (allowlist + public-IP guard are unchanged).
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _extract_tiff_from_multipart(path):
    """ArcGIS WCS 2.0.1 GetCoverage answers `multipart/related` (a GML part + the GeoTIFF part) even when
    a single coverage is requested. `download()` writes that whole envelope to disk; rewrite the file
    in place to the bare GeoTIFF so the prep step (rasterio) reads it. No-op if the file is already a
    plain TIFF. Stdlib only (byte scan) — the body uses non-standard LF separators, so an email/MIME
    parser is unreliable; scanning for the TIFF magic + the trailing boundary is robust."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] in (b"II*\x00", b"MM\x00*"):
        return path  # already a bare TIFF
    boundary = raw[:120].split(b"\n", 1)[0].strip()  # e.g. b"--wcs"
    for magic in (b"II*\x00", b"MM\x00*"):
        i = raw.find(magic)
        if i != -1:
            j = raw.find(boundary, i) if boundary else -1
            tiff = raw[i:(j if j != -1 else len(raw))].rstrip(b"\r\n-")
            with open(path, "wb") as f:
                f.write(tiff)
            return path
    raise ValueError("WCS response was neither a TIFF nor a multipart carrying one: %s" % path)


def _clamp_px(bbox, res_m, cap=4000):
    """Pixel width/height for a WMS GetMap at ~res_m metres/pixel, clamped to [16, cap] so a large bbox
    coarsens instead of requesting a giant raster. Approximate WGS84 metres-per-degree."""
    min_lon, min_lat, max_lon, max_lat = bbox
    midlat = math.radians((min_lat + max_lat) / 2.0)
    w = (max_lon - min_lon) * 111320.0 * max(0.05, math.cos(midlat)) / res_m
    h = (max_lat - min_lat) * 110540.0 / res_m
    return max(16, min(cap, int(round(w)))), max(16, min(cap, int(round(h))))


def _wcs201_getcoverage(host, path, coverage, bbox, dest, axes=("Lat", "Long"), subset_crs="4326",
                        fmt="image/tiff", max_bytes=500_000_000, timeout=300, on_progress=None,
                        user_agent=None, multipart=False):
    """Fetch a bbox via WCS 2.0.1 GetCoverage. `axes` = the coverage's (lat-axis, lon-axis) names; when
    `subset_crs` is set the lat/lon values are interpreted in that CRS (the server reprojects from it).
    `user_agent` overrides the request UA for a WAF-guarded host; `multipart=True` post-extracts the
    GeoTIFF from an ArcGIS `multipart/related` GetCoverage response."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_axis, lon_axis = axes
    parts = [
        "SERVICE=WCS", "VERSION=2.0.1", "REQUEST=GetCoverage",
        "COVERAGEID=%s" % coverage,
        "SUBSET=%s(%.8f,%.8f)" % (lat_axis, min_lat, max_lat),
        "SUBSET=%s(%.8f,%.8f)" % (lon_axis, min_lon, max_lon),
        "FORMAT=%s" % fmt,
    ]
    if subset_crs:
        parts.append("SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/%s" % subset_crs)
    url = "https://%s%s?%s" % (host, path, "&".join(parts))
    download(url, dest, NATIONAL_DEM_HOSTS, max_bytes=max_bytes, timeout=timeout,
             on_progress=on_progress, user_agent=user_agent)
    if multipart:
        _extract_tiff_from_multipart(dest)
    return dest


def _wms130_getmap(host, path, layer, bbox, dest, res_m=1.0, fmt="image/geotiff",
                   max_bytes=500_000_000, timeout=300, on_progress=None):
    """Fetch a bbox via WMS 1.3.0 GetMap. Under WMS 1.3.0 with CRS=EPSG:4326 the BBOX axis order is
    lat,lon (miny=min_lat). Pixel size derives from `res_m` (clamped)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    w, h = _clamp_px(bbox, res_m)
    parts = [
        "SERVICE=WMS", "VERSION=1.3.0", "REQUEST=GetMap", "STYLES=",
        "LAYERS=%s" % layer, "CRS=EPSG:4326",
        "BBOX=%.8f,%.8f,%.8f,%.8f" % (min_lat, min_lon, max_lat, max_lon),
        "WIDTH=%d" % w, "HEIGHT=%d" % h, "FORMAT=%s" % fmt,
    ]
    url = "https://%s%s?%s" % (host, path, "&".join(parts))
    download(url, dest, NATIONAL_DEM_HOSTS, max_bytes=max_bytes, timeout=timeout, on_progress=on_progress)
    return dest


# ── per-country fetchers (bbox = (min_lon, min_lat, max_lon, max_lat)) ─────────────────────────────
def fetch_nl_ahn(bbox, dest_dir, on_progress=None):
    """Netherlands AHN 0.5 m bare-earth DTM (PDOK WCS). CC-BY 4.0 (attribute AHN)."""
    dest = "%s/nl_ahn_dtm05_%s.tif" % (dest_dir, _tag(bbox))
    return _wcs201_getcoverage("service.pdok.nl", "/rws/ahn/wcs/v1_0", "dtm_05m", bbox, dest,
                               axes=("Lat", "Long"), subset_crs="4326", on_progress=on_progress)


def fetch_uk_dtm1(bbox, dest_dir, on_progress=None):
    """UK (England) LIDAR Composite 1 m bare-earth DTM (Environment Agency WCS). OGL (attribute EA)."""
    dest = "%s/uk_lidar_dtm1_%s.tif" % (dest_dir, _tag(bbox))
    cov = "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m"
    return _wcs201_getcoverage("environment.data.gov.uk",
                               "/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs",
                               cov, bbox, dest, axes=("Lat", "Long"), subset_crs="4326",
                               on_progress=on_progress)


def fetch_es_mdt5(bbox, dest_dir, on_progress=None):
    """Spain IGN/CNIG MDT 5 m bare-earth DTM (WCS, lat/lon coverage). CC-BY 4.0 (attribute IGN/CNIG)."""
    dest = "%s/es_mdt5_%s.tif" % (dest_dir, _tag(bbox))
    # Elevacion4258_5 is the ETRS89 geographic (lat/lon) coverage -> native Lat/Long axes, no subset CRS.
    return _wcs201_getcoverage("servicios.idee.es", "/wcs-inspire/mdt", "Elevacion4258_5", bbox, dest,
                               axes=("Lat", "Long"), subset_crs=None, on_progress=on_progress)


def fetch_fr_rgealti(bbox, dest_dir, on_progress=None):
    """France IGN RGE ALTI 1 m bare-earth DTM (Geoplateforme WMS). Etalab OL 2.0 (attribute IGN)."""
    dest = "%s/fr_rgealti1_%s.tif" % (dest_dir, _tag(bbox))
    return _wms130_getmap("data.geopf.fr", "/wms-r", "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES",
                          bbox, dest, res_m=1.0, on_progress=on_progress)


def fetch_fr_lidarhd(bbox, dest_dir, on_progress=None):
    """France IGN LIDAR HD 0.5 m bare-earth DTM (Geoplateforme WMS, rolling coverage). Etalab OL 2.0."""
    dest = "%s/fr_lidarhd05_%s.tif" % (dest_dir, _tag(bbox))
    return _wms130_getmap("data.geopf.fr", "/wms-r",
                          "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93",
                          bbox, dest, res_m=0.5, on_progress=on_progress)


def fetch_au_5m(bbox, dest_dir, on_progress=None):
    """Australia GA DEM 5 m (LiDAR-derived, 2025) bare-earth DTM (Geoscience Australia ArcGIS WCS). The
    coverage's native CRS is EPSG:4283 (GDA94 geographic, axes y=lat x=lon); the GA gateway needs a
    browser User-Agent (WAF) and returns multipart/related, both handled here. CC-BY 4.0 (attribute GA).
    Partial national coverage — where there is no 5 m tile the request errors and the caller falls back
    to the global 30 m sources."""
    dest = "%s/au_dem5_%s.tif" % (dest_dir, _tag(bbox))
    return _wcs201_getcoverage(
        "services.ga.gov.au", "/gis/services/DEM_LiDAR_5m_2025/MapServer/WCSServer",
        "Coverage1", bbox, dest, axes=("y", "x"), subset_crs="4283",
        user_agent=_BROWSER_UA, multipart=True, on_progress=on_progress)


def _tag(bbox):
    return "%.4f_%.4f_%.4f_%.4f" % (bbox[1], bbox[0], bbox[3], bbox[2])


# ── source registry (fetch(bbox, dest_dir) -> path) ────────────────────────────────────────────────
SOURCES = {
    "nl_ahn": {"label": "Netherlands AHN 0.5 m DTM", "fetch": fetch_nl_ahn, "country": "NL"},
    "uk_dtm1": {"label": "UK (England) LIDAR Composite 1 m DTM", "fetch": fetch_uk_dtm1, "country": "GB"},
    "fr_rgealti": {"label": "France RGE ALTI 1 m DTM", "fetch": fetch_fr_rgealti, "country": "FR"},
    "fr_lidarhd": {"label": "France LIDAR HD 0.5 m DTM", "fetch": fetch_fr_lidarhd, "country": "FR"},
    "es_mdt5": {"label": "Spain MDT 5 m DTM", "fetch": fetch_es_mdt5, "country": "ES"},
    "au_dem5": {"label": "Australia GA DEM 5 m LiDAR DTM", "fetch": fetch_au_5m, "country": "AU"},
}


# Rough national envelopes (min_lon, min_lat, max_lon, max_lat) → the country's nationwide-complete
# hi-res source. Used by the auto picker to upgrade an out-of-US hi-res request to a national portal
# only when the requested bbox falls ENTIRELY inside one country (partial/coastal areas fall back to
# the global 30 m sources). France maps to RGE ALTI 1 m (nationwide), not the rolling LIDAR HD 0.5 m.
_NATIONAL_ENVELOPES = [
    ((3.2, 50.7, 7.3, 53.6), "nl_ahn"),
    ((-8.7, 49.8, 1.9, 61.0), "uk_dtm1"),
    ((-5.3, 41.3, 9.6, 51.1), "fr_rgealti"),
    ((-9.4, 35.9, 4.4, 43.8), "es_mdt5"),
    ((112.9, -43.7, 153.7, -9.9), "au_dem5"),
]


def pick_national(bbox):
    """The national hi-res source id whose country fully contains `bbox`, or None. The bbox must fall
    ENTIRELY within a country envelope to auto-upgrade — so a border/coastal request isn't sent to a
    portal that only half-covers it; the caller then keeps the global 30 m fallback."""
    min_lon, min_lat, max_lon, max_lat = bbox
    for (elon0, elat0, elon1, elat1), src in _NATIONAL_ENVELOPES:
        if min_lon >= elon0 and max_lon <= elon1 and min_lat >= elat0 and max_lat <= elat1:
            return src
    return None
