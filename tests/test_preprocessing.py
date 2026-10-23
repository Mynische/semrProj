"""
Tests for geopulse.preprocessing — Spatial validation.

All raster fixtures are small synthetic GeoTIFFs created by Rasterio in
temporary directories. They are clearly test data and must never be
presented as real satellite imagery.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds

import sys

# Ensure the src directory is importable.
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))

from geopulse.io import RasterMeta, inspect_raster, REQUIRED_BANDS
from geopulse.preprocessing import (
    validate_spatial_compatibility,
    TRANSFORM_ABS_TOL,
    PRIMARY_BANDS,
    AUXILIARY_BANDS,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tif(
    path: Path,
    width: int = 100,
    height: int = 100,
    crs: CRS | None = CRS.from_epsg(32643),
    transform=None,
    dtype: str = "uint16",
    nodata: float | None = 0,
) -> Path:
    """Write a minimal GeoTIFF for testing."""
    if transform is None:
        transform = from_bounds(0, 0, width * 10, height * 10, width, height)
    with rasterio.open(
        path, "w", driver="GTiff",
        width=width, height=height, count=1,
        dtype=dtype, crs=crs, transform=transform, nodata=nodata,
    ) as ds:
        ds.write(np.ones((height, width), dtype=dtype), 1)
    return path


def _make_uniform_metadata(
    tmp_path: Path, **per_band_overrides
) -> dict[str, RasterMeta]:
    """Create band files where ALL bands share the same grid (for basic tests).

    *per_band_overrides* maps band names to kwarg dicts passed to _create_tif.
    Bands not mentioned get default (compatible) parameters.
    """
    defaults = dict(width=100, height=100, crs=CRS.from_epsg(32643))
    metadata = {}
    for band in REQUIRED_BANDS:
        overrides = per_band_overrides.get(band, {})
        params = {**defaults, **overrides}
        fpath = tmp_path / f"{band}.tif"
        _create_tif(fpath, **params)
        metadata[band] = inspect_raster(band, fpath)
    return metadata


def _make_realistic_metadata(
    tmp_path: Path, **per_band_overrides
) -> dict[str, RasterMeta]:
    """Create band files mimicking real Sentinel-2 resolution layout.

    B03, B04, B08 → 10 m (1000×1000 over 10 km).
    SCL → 20 m (500×500 over same 10 km extent).
    """
    # Shared spatial extent: 10 km × 10 km.
    extent = 10000  # metres
    origin_x, origin_y = 500000, 3000000

    defaults_10m = dict(
        width=1000, height=1000,
        crs=CRS.from_epsg(32643),
        transform=from_bounds(origin_x, origin_y, origin_x + extent, origin_y + extent, 1000, 1000),
    )
    defaults_20m = dict(
        width=500, height=500,
        crs=CRS.from_epsg(32643),
        transform=from_bounds(origin_x, origin_y, origin_x + extent, origin_y + extent, 500, 500),
        dtype="uint8",
    )

    metadata = {}
    for band in PRIMARY_BANDS:
        overrides = per_band_overrides.get(band, {})
        params = {**defaults_10m, **overrides}
        fpath = tmp_path / f"{band}.tif"
        _create_tif(fpath, **params)
        metadata[band] = inspect_raster(band, fpath)

    for band in AUXILIARY_BANDS:
        overrides = per_band_overrides.get(band, {})
        params = {**defaults_20m, **overrides}
        fpath = tmp_path / f"{band}.tif"
        _create_tif(fpath, **params)
        metadata[band] = inspect_raster(band, fpath)

    return metadata


# ---------------------------------------------------------------------------
# Tests — Basic validation (all bands on same grid)
# ---------------------------------------------------------------------------

class TestValidateSpatialBasic:
    """Tests with all bands on the same grid (uniform resolution)."""

    def test_all_compatible(self, tmp_path):
        """All bands with identical grids should pass."""
        metadata = _make_uniform_metadata(tmp_path)
        result = validate_spatial_compatibility(metadata)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_crs_mismatch_among_primary(self, tmp_path):
        """Different CRS on a primary band should trigger an error."""
        metadata = _make_uniform_metadata(
            tmp_path,
            B04={"crs": CRS.from_epsg(32644)},
        )
        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert any("CRS" in e for e in result.errors)

    def test_missing_crs(self, tmp_path):
        """A raster with no CRS should trigger an error."""
        metadata = _make_uniform_metadata(
            tmp_path,
            B08={"crs": None},
        )
        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert any("no CRS" in e for e in result.errors)

    def test_empty_metadata(self):
        """Empty input should trigger an error."""
        result = validate_spatial_compatibility({})
        assert not result.is_valid
        assert any("No raster" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Tests — Primary-band grid validation (10 m bands)
# ---------------------------------------------------------------------------

class TestValidatePrimaryBands:
    """Tests for strict grid matching among B03, B04, B08."""

    def test_dimension_mismatch_primary(self, tmp_path):
        """Different dimensions among 10 m bands should error."""
        metadata = _make_realistic_metadata(
            tmp_path,
            B04={"width": 900, "height": 900,
                 "transform": from_bounds(500000, 3000000, 509000, 3009000, 900, 900)},
        )
        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert any("Dimension" in e and "10 m" in e for e in result.errors)

    def test_affine_transform_mismatch_primary(self, tmp_path):
        """Different affine transforms among 10 m bands should error."""
        shifted = from_bounds(501000, 3001000, 511000, 3011000, 1000, 1000)
        metadata = _make_realistic_metadata(tmp_path)
        fpath_shifted = tmp_path / "B04_shifted.tif"
        _create_tif(fpath_shifted, width=1000, height=1000, transform=shifted)
        metadata["B04"] = inspect_raster("B04", fpath_shifted)

        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert any("transform" in e.lower() for e in result.errors)

    def test_transform_within_tolerance(self, tmp_path):
        """Transforms differing within tolerance should pass."""
        metadata = _make_realistic_metadata(tmp_path)
        orig = metadata["B04"].transform
        tiny = TRANSFORM_ABS_TOL / 10
        nudged = Affine(
            orig.a + tiny, orig.b, orig.c,
            orig.d, orig.e + tiny, orig.f,
        )
        metadata["B04"] = RasterMeta(
            band_name="B04",
            file_path=metadata["B04"].file_path,
            width=metadata["B04"].width,
            height=metadata["B04"].height,
            count=metadata["B04"].count,
            crs=metadata["B04"].crs,
            transform=nudged,
            pixel_size_x=abs(nudged.a),
            pixel_size_y=abs(nudged.e),
            dtype=metadata["B04"].dtype,
            nodata=metadata["B04"].nodata,
            bounds=metadata["B04"].bounds,
        )
        result = validate_spatial_compatibility(metadata)
        assert result.is_valid


# ---------------------------------------------------------------------------
# Tests — Auxiliary-band (SCL) validation
# ---------------------------------------------------------------------------

class TestValidateAuxiliaryBands:
    """Tests for SCL (20 m) validation against primary (10 m) bands."""

    def test_realistic_sentinel2_passes(self, tmp_path):
        """Real Sentinel-2 layout (10 m + 20 m SCL) should pass."""
        metadata = _make_realistic_metadata(tmp_path)
        result = validate_spatial_compatibility(metadata)
        assert result.is_valid
        # Should have an info message about SCL resolution.
        assert any("SCL" in i and "nearest-neighbor" in i.lower() for i in result.info)

    def test_scl_resolution_reported_as_info(self, tmp_path):
        """SCL dimension/pixel-size difference should be info, not error."""
        metadata = _make_realistic_metadata(tmp_path)
        result = validate_spatial_compatibility(metadata)
        assert result.is_valid
        assert len(result.errors) == 0
        assert any("SCL" in i for i in result.info)

    def test_scl_crs_mismatch_is_error(self, tmp_path):
        """SCL with different CRS is a real error."""
        metadata = _make_realistic_metadata(
            tmp_path,
            SCL={"crs": CRS.from_epsg(32644),
                 "width": 500, "height": 500,
                 "transform": from_bounds(500000, 3000000, 510000, 3010000, 500, 500),
                 "dtype": "uint8"},
        )
        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert any("CRS" in e for e in result.errors)

    def test_scl_extent_mismatch_is_error(self, tmp_path):
        """SCL covering a different area is a real error."""
        # Shift SCL extent by 50 km (well beyond tolerance)
        shifted_transform = from_bounds(550000, 3050000, 560000, 3060000, 500, 500)
        metadata = _make_realistic_metadata(
            tmp_path,
            SCL={"transform": shifted_transform,
                 "width": 500, "height": 500, "dtype": "uint8"},
        )
        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert any("extent" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Tests — Report formatting
# ---------------------------------------------------------------------------

class TestValidationSummary:
    """Tests for the human-readable summary output."""

    def test_summary_pass(self, tmp_path):
        metadata = _make_uniform_metadata(tmp_path)
        result = validate_spatial_compatibility(metadata)
        assert "PASSED" in result.summary()

    def test_summary_fail(self, tmp_path):
        metadata = _make_uniform_metadata(
            tmp_path, B04={"crs": CRS.from_epsg(32644)}
        )
        result = validate_spatial_compatibility(metadata)
        assert "FAILED" in result.summary()

    def test_summary_includes_info(self, tmp_path):
        metadata = _make_realistic_metadata(tmp_path)
        result = validate_spatial_compatibility(metadata)
        summary = result.summary()
        assert "PASSED" in summary
        assert "Info:" in summary

    def test_multiple_errors_reported(self, tmp_path):
        """When multiple primary bands differ, all errors should be reported."""
        metadata = _make_uniform_metadata(
            tmp_path,
            B04={"crs": CRS.from_epsg(32644)},
            B08={"crs": CRS.from_epsg(32644)},
        )
        result = validate_spatial_compatibility(metadata)
        assert not result.is_valid
        assert len(result.errors) >= 2
