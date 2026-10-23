"""
geopulse.io — Configuration loading and raster metadata inspection.

This module provides:
- YAML configuration loading and path resolution.
- Raster metadata extraction via Rasterio (without loading pixel data).
- Structured metadata reporting for Sentinel-2 band files.

Notes on radiometric scaling (Day 2):
    Sentinel-2 L2A reflectance values are stored as integers. The conversion
    to physical reflectance depends on the processing baseline:
    - Baselines < 04.00: reflectance = DN / QUANTIFICATION_VALUE
    - Baselines >= 04.00: reflectance = (DN + RADIO_ADD_OFFSET) / QUANTIFICATION_VALUE
    Day 1 inspects and reports stored values and metadata only. Radiometric
    scaling will be implemented in Day 2 after verifying the product's
    processing baseline from its XML metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import rasterio
import yaml
from rasterio.crs import CRS
from rasterio.transform import Affine

logger = logging.getLogger(__name__)

# Sentinel-2 bands required by this pipeline.
REQUIRED_BANDS = ("B03", "B04", "B08", "SCL")


@dataclass
class RasterMeta:
    """Structured metadata for a single raster file."""

    band_name: str
    file_path: Path
    width: int
    height: int
    count: int  # number of bands in the file
    crs: CRS | None
    transform: Affine
    pixel_size_x: float
    pixel_size_y: float
    dtype: str
    nodata: Any
    bounds: rasterio.coords.BoundingBox

    def summary(self) -> str:
        """Return a human-readable summary string."""
        lines = [
            f"  Band        : {self.band_name}",
            f"  File        : {self.file_path}",
            f"  Dimensions  : {self.width} x {self.height}",
            f"  Bands       : {self.count}",
            f"  CRS         : {self.crs}",
            f"  Transform   : {self.transform}",
            f"  Pixel size  : ({self.pixel_size_x}, {self.pixel_size_y})",
            f"  Data type   : {self.dtype}",
            f"  Nodata      : {self.nodata}",
            f"  Bounds      : {self.bounds}",
        ]
        return "\n".join(lines)


def load_config(config_path: str | Path) -> dict:
    """Load and validate a YAML configuration file.

    Parameters
    ----------
    config_path : str or Path
        Path to the YAML configuration file.

    Returns
    -------
    dict
        Parsed configuration dictionary.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    ValueError
        If the configuration is empty or missing the 'bands' key.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if config is None:
        raise ValueError(f"Configuration file is empty: {config_path}")
    if not isinstance(config, dict):
        raise ValueError(
            f"Configuration must be a YAML mapping, got {type(config).__name__}"
        )
    if "bands" not in config:
        raise ValueError(
            f"Configuration missing required 'bands' key: {config_path}"
        )
    if not isinstance(config["bands"], dict):
        raise ValueError(
            f"'bands' must be a mapping of band names to file paths: {config_path}"
        )

    return config


def resolve_band_paths(
    config: dict, base_dir: Path | None = None
) -> dict[str, Path]:
    """Resolve band file paths from configuration.

    Relative paths are resolved against *base_dir* (defaults to the current
    working directory).

    Parameters
    ----------
    config : dict
        Parsed configuration with a ``bands`` key.
    base_dir : Path or None
        Base directory for resolving relative paths.

    Returns
    -------
    dict[str, Path]
        Mapping of band name → resolved absolute Path.

    Raises
    ------
    ValueError
        If any required band is missing from the configuration.
    FileNotFoundError
        If any configured band file does not exist on disk.
    """
    if base_dir is None:
        base_dir = Path.cwd()
    base_dir = Path(base_dir).resolve()

    bands_cfg = config.get("bands", {})

    # Check all required bands are present in config.
    missing = [b for b in REQUIRED_BANDS if b not in bands_cfg]
    if missing:
        raise ValueError(
            f"Configuration missing required bands: {', '.join(missing)}"
        )

    resolved: dict[str, Path] = {}
    for band_name in REQUIRED_BANDS:
        raw_path = bands_cfg[band_name]
        if raw_path is None or str(raw_path).strip() == "":
            raise ValueError(
                f"Band '{band_name}' has an empty path in configuration."
            )
        p = Path(raw_path)
        if not p.is_absolute():
            p = base_dir / p
        p = p.resolve()

        if not p.is_file():
            raise FileNotFoundError(
                f"Band '{band_name}' file not found: {p}"
            )

        resolved[band_name] = p

    return resolved


def inspect_raster(band_name: str, file_path: Path) -> RasterMeta:
    """Open a raster file and extract its metadata without loading pixel data.

    Parameters
    ----------
    band_name : str
        Logical band identifier (e.g. ``"B03"``).
    file_path : Path
        Path to the raster file.

    Returns
    -------
    RasterMeta
        Structured metadata extracted from the raster.

    Raises
    ------
    rasterio.errors.RasterioIOError
        If the file cannot be opened as a raster.
    ValueError
        If the raster has no CRS defined.
    """
    file_path = Path(file_path)
    with rasterio.open(file_path) as ds:
        transform = ds.transform
        # Pixel sizes from the affine transform (a = pixel width, e = pixel
        # height which is typically negative for north-up images).
        pixel_size_x = abs(transform.a)
        pixel_size_y = abs(transform.e)

        meta = RasterMeta(
            band_name=band_name,
            file_path=file_path,
            width=ds.width,
            height=ds.height,
            count=ds.count,
            crs=ds.crs,
            transform=transform,
            pixel_size_x=pixel_size_x,
            pixel_size_y=pixel_size_y,
            dtype=ds.dtypes[0],
            nodata=ds.nodata,
            bounds=ds.bounds,
        )

    return meta


def inspect_all_bands(band_paths: dict[str, Path]) -> dict[str, RasterMeta]:
    """Inspect metadata for all configured bands.

    Parameters
    ----------
    band_paths : dict[str, Path]
        Mapping of band name → file path (from :func:`resolve_band_paths`).

    Returns
    -------
    dict[str, RasterMeta]
        Mapping of band name → extracted metadata.
    """
    results: dict[str, RasterMeta] = {}
    for band_name, fpath in band_paths.items():
        logger.info("Inspecting %s → %s", band_name, fpath)
        results[band_name] = inspect_raster(band_name, fpath)
    return results


def print_metadata_report(metadata: dict[str, RasterMeta]) -> None:
    """Print a concise metadata report for all inspected bands.

    Parameters
    ----------
    metadata : dict[str, RasterMeta]
        Band metadata mapping from :func:`inspect_all_bands`.
    """
    separator = "=" * 60
    print(separator)
    print("  GeoPulse-ThermalAI — Raster Metadata Report")
    print(separator)
    for band_name, meta in metadata.items():
        print()
        print(meta.summary())
    print()
    print(separator)
