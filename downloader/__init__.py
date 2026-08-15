"""Trusted DEM downloader — fetch + prep real-world elevation for scene construction.

Egress is confined to a hostname allowlist (`sources.py`); the network primitive (`net.py`) is
https-only, size-capped, and redirect-checked. `usgs_3dep.py` builds tile URLs from tile math;
`fetch.py` is the CLI/API that fills a destination directory, skipping tiles already present.
"""
