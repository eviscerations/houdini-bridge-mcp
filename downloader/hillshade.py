"""Derive a hillshade from a DEM — the universal, source-independent texture-overlay path.

Standard Horn hillshade (sun azimuth + altitude) computed from the elevation grid and written as a
georeferenced GeoTIFF matching the DEM's transform/CRS, so it aligns as a terrain texture. Because
it's derived from the DEM itself, the texture-overlay capability works on ANY fetched DEM (USGS TNM,
Copernicus, SRTM), not only where a state portal ships a native hillshade.
"""

import numpy as np


def compute(elev, res_m, azimuth_deg=315.0, altitude_deg=45.0, z_factor=1.0):
    """Hillshade (uint8 0..255) from a 2D elevation array. NaN/void cells are filled to the min so
    the shading stays continuous. azimuth 315 = light from the NW; altitude 45 = sun elevation."""
    e = np.asarray(elev, dtype=np.float64)
    if not np.isfinite(e).all():
        fill = float(np.nanmin(e)) if np.isfinite(e).any() else 0.0
        e = np.nan_to_num(e, nan=fill, posinf=fill, neginf=fill)

    zenith = np.radians(90.0 - altitude_deg)
    azimuth = np.radians(360.0 - azimuth_deg + 90.0)  # map compass -> math convention

    # np.gradient returns (d/drow, d/dcol); rows increase southward in a north-up DEM.
    dz_drow, dz_dcol = np.gradient(e, res_m)
    dzdx = dz_dcol
    dzdy = -dz_drow
    slope = np.arctan(z_factor * np.hypot(dzdx, dzdy))
    aspect = np.arctan2(dzdy, -dzdx)

    shade = (np.cos(zenith) * np.cos(slope)
             + np.sin(zenith) * np.sin(slope) * np.cos(azimuth - aspect))
    return (np.clip(shade, 0.0, 1.0) * 255.0).astype(np.uint8)


def write_geotiff(hs, out_path, transform, crs):
    """Write the uint8 hillshade as a single-band deflate-compressed GeoTIFF on the DEM's grid."""
    import rasterio
    with rasterio.open(
        out_path, "w", driver="GTiff",
        height=hs.shape[0], width=hs.shape[1], count=1, dtype="uint8",
        transform=transform, crs=crs, compress="deflate",
    ) as dst:
        dst.write(hs, 1)
    return out_path
