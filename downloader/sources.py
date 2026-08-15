"""Trusted DEM sources + the egress allowlist — the tool's ONE network lane.

Every download the tool performs must go to a host in ALLOWED_HOSTS. There is no arbitrary-URL
path (unlike tools that let a model pass any download URL). All sources here are FREE public
elevation data; keyed/account-gated sources are template-only until the user supplies a key.

Verified 2026-07. Hostnames are exact — the egress guard matches the URL host against this set.
"""

# --- exact hostnames the tool may reach, grouped by source ------------------------------------

USGS_3DEP_HOSTS = {
    "prd-tnm.s3.amazonaws.com",        # StagedProducts GeoTIFF bytes (the actual DEM files)
    "tnmaccess.nationalmap.gov",       # TNM Access product-discovery API (JSON)
    "elevation.nationalmap.gov",       # 3DEPElevation ImageServer exportImage (dynamic bbox)
    "rockyweb.usgs.gov",               # some TNM downloadURL targets
}

COPERNICUS_HOSTS = {
    "copernicus-dem-30m.s3.amazonaws.com",   # GLO-30 (global 30 m), anonymous S3, COG
    "copernicus-dem-90m.s3.amazonaws.com",   # GLO-90 sibling
}

SRTM_HOSTS = {
    "elevation-tiles-prod.s3.amazonaws.com",  # skadi .hgt.gz (SRTMGL1-equivalent, global) — bucket-scoped host
}

# State lidar portals — native DEM deliveries (often with hillshades/DSM/intensity). Regional
# (per-state); expandable as portals are found. A broad set also means no single state's presence
# is revealing. USGS TNM stays the universal fallback everywhere.
STATE_LIDAR_HOSTS = {
    "ftpgeoinfo.msl.mt.gov",     # Montana — full-delivery quad zips (MSDI Elevation/Lidar/Quads)
    "lidarportal.dnr.wa.gov",    # Washington — DNR portal: /project catalog + /download AOI zips
    "giscenter-sl.isu.edu",      # Idaho — ISU AOC_DEM bulk per-quad DTM zips
    "giscenter.rdc.isu.edu",     # Idaho — ISU ArcGIS ImageServer (1 m mosaic, exportImage by bbox)
}

# National high-resolution DEM portals (anonymous OGC WCS/WMS) — bare-earth DTM by bbox, no key. Each
# is a per-country hi-res source (0.5-5 m) sitting above the global 30 m fallback; expandable as more
# national open portals are verified. Hostnames exact (the egress guard matches the URL host).
NATIONAL_DEM_HOSTS = {
    "service.pdok.nl",              # Netherlands AHN 0.5 m DTM (WCS 2.0.1)
    "environment.data.gov.uk",     # UK (England) LIDAR Composite 1 m DTM (WCS 2.0.1)
    "data.geopf.fr",               # France IGN RGE ALTI 1 m / LIDAR HD 0.5 m (WMS 1.3.0)
    "servicios.idee.es",           # Spain IGN/CNIG MDT 5 m (WCS 2.0.1)
    "services.ga.gov.au",          # Australia GA DEM 5 m LiDAR (ArcGIS WCS 2.0.1; browser-UA + multipart)
}

# OpenTopography's public SDSC MinIO mirror — ANONYMOUS, no key, no login. The `raster` bucket hosts
# many global + national DEMs behind one uniform download mechanism (bytes over https), including
# AW3D30 (ALOS World 3D 30 m, geoid), NASADEM, GEDTM30, EU_DTM and LINZ NZ 1 m. This is the free path
# to JAXA's AW3D30 that side-steps the account-gated JAXA portal. Bucket-scoped virtual-host form.
OPENTOPO_S3_HOSTS = {"opentopography.s3.sdsc.edu"}

# Keyed/account-gated — template only; not reached unless the user configures a key.
OPENTOPO_HOSTS = {"portal.opentopography.org"}   # globaldem API (free key) — an alternate keyed path

# The active free, no-key allowlist. The keyed OpenTopography API host is added at runtime only when a key is set.
ALLOWED_HOSTS = (USGS_3DEP_HOSTS | COPERNICUS_HOSTS | SRTM_HOSTS | STATE_LIDAR_HOSTS
                 | OPENTOPO_S3_HOSTS | NATIONAL_DEM_HOSTS)

# NOTE: the shared `s3.amazonaws.com` path-style endpoint is deliberately NOT allowlisted — it is a
# global S3 front door that a host-only allowlist cannot confine to one bucket. We use the
# bucket-scoped virtual-host form (`elevation-tiles-prod.s3.amazonaws.com`) instead, which pins the
# bucket by hostname.
