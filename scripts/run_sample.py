#!/usr/bin/env python3
"""
GeoPulse-ThermalAI — Day 1 Sample Validation Script.

Usage:
    python scripts/run_sample.py --config configs/sample.yaml

This script:
1. Loads a YAML configuration specifying Sentinel-2 band file paths.
2. Resolves and validates file existence.
3. Inspects raster metadata (dimensions, CRS, transform, dtype, nodata).
4. Validates spatial compatibility across all configured bands.
5. Prints a concise metadata report.

Exit codes:
    0 — All validations passed.
    1 — Validation failed (missing files, incompatible grids, etc.).
    2 — Usage or configuration error.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the src directory is importable when running from the repo root.
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))

from geopulse.io import (
    load_config,
    resolve_band_paths,
    inspect_all_bands,
    print_metadata_report,
)
from geopulse.preprocessing import validate_spatial_compatibility


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code (0=success, 1=validation failure, 2=usage error)."""
    parser = argparse.ArgumentParser(
        description="GeoPulse-ThermalAI — Validate Sentinel-2 raster inputs."
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to YAML configuration file (e.g. configs/sample.yaml).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG-level) logging.",
    )
    args = parser.parse_args(argv)

    # Configure logging.
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("geopulse")

    # --- Step 1: Load configuration ----------------------------------------
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    # --- Step 2: Resolve and validate file paths ---------------------------
    try:
        band_paths = resolve_band_paths(config, base_dir=_repo_root)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Path resolution error: %s", exc)
        return 1

    # --- Step 3: Inspect raster metadata -----------------------------------
    try:
        metadata = inspect_all_bands(band_paths)
    except Exception as exc:
        logger.error("Raster inspection error: %s", exc)
        return 1

    # --- Step 4: Print metadata report -------------------------------------
    print_metadata_report(metadata)

    # --- Step 5: Validate spatial compatibility ----------------------------
    result = validate_spatial_compatibility(metadata)
    print()
    print(result.summary())

    if not result.is_valid:
        return 1

    print()
    print("Day 1 validation complete. All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
