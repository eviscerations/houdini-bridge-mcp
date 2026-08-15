# Terrain data — sources & coverage

The terrain downloader turns **"name a place → get terrain"** into one step: it fetches real-world
elevation for a lat/lon (or bbox) from trusted public sources and preps it — reproject to a local UTM
zone, decimate to the target resolution, write a `.npy` plus a scene-position sidecar — so
`import_heightfield` places it at true elevation, aligned to any proximal tiles.

## Sources are a provenance-gated allowlist

Every fetch goes through one guarded egress lane (`downloader/net.py`): **HTTPS-only**, a **fixed host
allowlist** (`downloader/sources.py`), **per-redirect re-validation**, a **resolves-to-public-IP (SSRF)
guard**, and a **response-size cap**. There is no arbitrary-URL import — only the hosts listed below are
reachable. Downloads and the resulting `.npy`/sidecar are written only under your configured working
directory (`realpath`-confined). API keys, where used, come from the environment and are never bundled,
committed, or logged.

Select a source with `--source`, or leave it `auto` (US → 3DEP; a hi-res request outside the US
auto-upgrades to a national portal when the whole bbox sits in a covered country, otherwise falls back
to global 30 m).

## Coverage — anonymous (no key, works out of the box)

| Region | `--source` | Res | Host | Licence / attribution |
|---|---|---|---|---|
| **Global** | `copernicus` | 30 m | copernicus-dem-30m.s3.amazonaws.com | Copernicus DEM (ESA), free |
| **Global** | `srtm` | ~30 m | elevation-tiles-prod.s3.amazonaws.com | SRTM (NASA/USGS), public domain |
| **Global** | `aw3d30` | 30 m | opentopography.s3.sdsc.edu | JAXA ALOS AW3D30 (via OpenTopography mirror) |
| **USA** | `3dep` / `1m` | 30/10/1 m | *.nationalmap.gov, prd-tnm.s3… | USGS 3DEP, public domain |
| **USA (states)** | `mt_lidar` `wa_lidar` `id_lidar` | ~1 m | state portals | MT MSL / WA DNR / Idaho ISU |
| **Netherlands** | `nl_ahn` | 0.5 m | service.pdok.nl | AHN, CC-BY 4.0 |
| **UK (England)** | `uk_dtm1` | 1 m | environment.data.gov.uk | EA LIDAR Composite, OGL |
| **France** | `fr_rgealti` / `fr_lidarhd` | 1 m / 0.5 m | data.geopf.fr | IGN RGE ALTI / LIDAR HD, Etalab OL 2.0 |
| **Spain** | `es_mdt5` | 5 m | servicios.idee.es | IGN/CNIG MDT, CC-BY 4.0 |
| **Australia** | `au_dem5` | 5 m | services.ga.gov.au | Geoscience Australia DEM (LiDAR), CC-BY 4.0 |

National hi-res portals server-side clip the whole bbox to one GeoTIFF (WCS 2.0.1 / WMS 1.3.0); the byte
cap plus a WMS pixel clamp bound the size. Outside the listed countries, requests fall back to the global
30 m sources, so "name a place, get terrain" holds worldwide.

## Coverage — keyed opt-in (your own free OpenTopography account)

`--source ot_aw3d30|ot_srtm1|ot_srtm3|ot_cop30|ot_cop90|ot_nasadem|ot_eudtm|ot_gedtm30` hits the
OpenTopography global API (portal.opentopography.org), server-clipped to the bbox. Requires your own free
key in `HMCP_OPENTOPO_KEY` (environment only, never bundled, redacted from logs). The host is added to the
allowlist only when a key is set.

## Not yet shipped (documented)

- **Canada HRDEM 1 m** — tiles are ~300 GB BigTIFF COGs needing windowed `/vsicurl/` reads, which would
  bypass the `download()` egress guard — a security-design decision owed before it can be added.
- **New Zealand 1 m** — the anonymous mirror hosts `LINZ1m_DTM/`, but the bucket denies LIST, so tiles
  can't be enumerated without the LINZ tile index; NZ is covered at 30 m today.

## How tiles align ("anywhere on Earth")

The prep step picks the **UTM zone for the lat/lon** as the working CRS (metric, local, low distortion)
and holds **one origin per project** — the first tile sets it, and successive tiles share it, so they
align automatically. Elevation is the DEM's own metric height, unchanged. Resolution is user-specified or
auto-by-extent, capped by a voxel budget so a wide area can't blow past the display budget.

## Attribution

Public-domain sources (USGS, SRTM) need no attribution. CC-BY / OGL / Etalab sources require attribution
as listed in the coverage table when you publish work built on their data. Full third-party terms are in
[`THIRD-PARTY-LICENSES.md`](THIRD-PARTY-LICENSES.md).
