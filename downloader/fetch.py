"""Fetch 3DEP DEM tiles into a destination directory — CLI + importable API.

No hardcoded paths: the destination is always supplied by the caller (`--dest`). Tiles are chosen
either by a lat/lon bounding box (`--bbox`) or by an explicit tile list (`--tiles`). Tiles already
present in the destination (any version) are skipped, so this is safe to re-run to fill gaps.

Examples:
    # by bbox — fill 47–49°N, 117–123°W at 1/3 arc-second
    python -m downloader.fetch --dest "D:/terrain" --product 13 --bbox -123 47 -117 49
    # by explicit tiles
    python -m downloader.fetch --dest "D:/terrain" --product 13 --tiles n48w118 n48w119
    # preview only (HEAD each URL, no download)
    python -m downloader.fetch --dest "D:/terrain" --product 13 --bbox -123 47 -117 49 --dry-run
"""

import argparse
import sys

from . import usgs_3dep as t3
from .net import download, head, EgressError
from .sources import USGS_3DEP_HOSTS


def _head(url):
    """Return (status, content_length) for a guarded HEAD, or (error_str, None). Routed through the
    egress guard (https + host allowlist + per-redirect re-validation) — no raw urlopen."""
    try:
        headers = head(url, USGS_3DEP_HOSTS, timeout=30)
        return 200, headers.get("Content-Length")
    except Exception as e:  # noqa: BLE001 - report any HEAD failure to the caller
        return f"ERR {e}", None


def plan(dest, product, tiles):
    """Split requested tiles into (already_present, to_fetch) for `dest`."""
    present, todo = [], []
    for tile in tiles:
        existing = t3.have_tile(dest, tile, product)
        (present if existing else todo).append((tile, existing))
    return present, todo


def run(dest, product="13", bbox=None, tiles=None, dry_run=False, max_bytes=2_000_000_000):
    if not tiles:
        if not bbox:
            raise SystemExit("provide --bbox or --tiles")
        tiles = t3.tiles_for_bbox(*bbox)
    tiles = sorted(dict.fromkeys(tiles))  # dedupe, stable order

    present, todo = plan(dest, product, tiles)
    prefix, label = t3.PRODUCTS[product]
    print(f"[3dep] product {product} = {label}")
    print(f"[3dep] dest: {dest}")
    print(f"[3dep] {len(tiles)} tiles requested · {len(present)} already present,{len(todo)} to fetch")
    for tile, path in present:
        print(f"   have  {tile}  ({path})")

    if dry_run:
        print("[3dep] --dry-run: checking availability (HEAD) ...")
        total = 0
        for tile, _ in todo:
            url = t3.url_for(tile, product)
            status, clen = _head(url)
            mb = f"{int(clen)/1e6:.0f} MB" if clen else "?"
            if clen:
                total += int(clen)
            print(f"   {tile}: {status}  {mb}")
        print(f"[3dep] would download ~{total/1e9:.2f} GB")
        return

    done, failed = [], []
    for i, (tile, _) in enumerate(todo, 1):
        url = t3.url_for(tile, product)
        dest_path = f"{dest}/{t3.filename_for(tile, product)}"

        def prog(got, tot, _tile=tile, _i=i):
            pct = f"{100*got/tot:.0f}%" if tot else "?"
            sys.stdout.write(f"\r   [{_i}/{len(todo)}] {_tile}  {got/1e6:6.0f} MB  {pct}   ")
            sys.stdout.flush()

        try:
            n = download(url, dest_path, USGS_3DEP_HOSTS, max_bytes=max_bytes, timeout=120, on_progress=prog)
            print(f"\r   [{i}/{len(todo)}] {tile}  {n/1e6:.0f} MB  done            ")
            done.append(tile)
        except (EgressError, Exception) as e:  # noqa: BLE001 - keep going on a single tile failure
            print(f"\r   [{i}/{len(todo)}] {tile}  FAILED: {e}          ")
            failed.append((tile, str(e)))

    print(f"[3dep] downloaded {len(done)}, failed {len(failed)}")
    for tile, err in failed:
        print(f"   FAIL {tile}: {err}")
    if failed:
        raise SystemExit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch USGS 3DEP DEM tiles into a directory.")
    ap.add_argument("--dest", required=True, help="destination directory (created if missing)")
    ap.add_argument("--product", default="13", choices=sorted(t3.PRODUCTS), help="1 (~30m) or 13 (~10m)")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))
    ap.add_argument("--tiles", nargs="+", help="explicit tile ids, e.g. n48w118 n48w119")
    ap.add_argument("--dry-run", action="store_true", help="HEAD each tile and report size; do not download")
    a = ap.parse_args(argv)
    run(a.dest, a.product, a.bbox, a.tiles, a.dry_run)


if __name__ == "__main__":
    main()
