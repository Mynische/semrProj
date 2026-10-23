"""
Tests for geopulse.io — Configuration loading and raster metadata inspection.

All raster fixtures are small synthetic GeoTIFFs created by Rasterio in
temporary directories. They are clearly test data and must never be
presented as real satellite imagery.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

import sys

# Ensure the src directory is importable.
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))

from geopulse.io import (
    RasterMeta,
    load_config,
    resolve_band_paths,
    inspect_raster,
    inspect_all_bands,
    REQUIRED_BANDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_tif(
    path: Path,
    width: int = 100,
    height: int = 100,
    crs: CRS | None = CRS.from_epsg(32643),
    transform=None,
    dtype: str = "uint16",
    nodata: float | None = 0,
    count: int = 1,
) -> Path:
    """Write a minimal single-band GeoTIFF for testing."""
    if transform is None:
        transform = from_bounds(0, 0, width * 10, height * 10, width, height)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=count,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as ds:
        data = np.ones((height, width), dtype=dtype)
        for i in range(count):
            ds.write(data, i + 1)

    return path


def _create_band_files(tmp_path: Path, **overrides) -> dict[str, Path]:
    """Create a full set of test band files under *tmp_path*.

    Any key in *overrides* is passed through to ``_create_test_tif`` for
    **all** bands (useful for changing CRS, dimensions, etc. uniformly).
    """
    paths = {}
    for band in REQUIRED_BANDS:
        fpath = tmp_path / f"test_{band}.tif"
        _create_test_tif(fpath, **overrides)
        paths[band] = fpath
    return paths


def _write_config(tmp_path: Path, band_paths: dict[str, Path]) -> Path:
    """Write a YAML config pointing at the given band paths."""
    config_path = tmp_path / "test_config.yaml"
    lines = ["bands:"]
    for band_name, fpath in band_paths.items():
        lines.append(f"  {band_name}: {fpath}")
    config_path.write_text("\n".join(lines) + "\n")
    return config_path


# ---------------------------------------------------------------------------
# Tests — load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    """Tests for YAML configuration loading."""

    def test_load_valid_config(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text(
            textwrap.dedent("""\
            bands:
              B03: some/path/b03.tif
              B04: some/path/b04.tif
              B08: some/path/b08.tif
              SCL: some/path/scl.tif
            """)
        )
        config = load_config(cfg_path)
        assert "bands" in config
        assert config["bands"]["B03"] == "some/path/b03.tif"

    def test_config_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_config(tmp_path / "missing.yaml")

    def test_empty_config(self, tmp_path):
        cfg_path = tmp_path / "empty.yaml"
        cfg_path.write_text("")
        with pytest.raises(ValueError, match="empty"):
            load_config(cfg_path)

    def test_config_missing_bands_key(self, tmp_path):
        cfg_path = tmp_path / "bad.yaml"
        cfg_path.write_text("other_key: 42\n")
        with pytest.raises(ValueError, match="bands"):
            load_config(cfg_path)

    def test_config_bands_not_mapping(self, tmp_path):
        cfg_path = tmp_path / "bad.yaml"
        cfg_path.write_text("bands:\n  - item1\n  - item2\n")
        with pytest.raises(ValueError, match="mapping"):
            load_config(cfg_path)

    def test_config_not_mapping(self, tmp_path):
        cfg_path = tmp_path / "scalar.yaml"
        cfg_path.write_text("just a string\n")
        with pytest.raises(ValueError, match="mapping"):
            load_config(cfg_path)


# ---------------------------------------------------------------------------
# Tests — resolve_band_paths
# ---------------------------------------------------------------------------

class TestResolveBandPaths:
    """Tests for band-path resolution and existence checks."""

    def test_resolve_valid_paths(self, tmp_path):
        band_files = _create_band_files(tmp_path)
        config = {"bands": {k: str(v) for k, v in band_files.items()}}
        resolved = resolve_band_paths(config, base_dir=tmp_path)
        for band in REQUIRED_BANDS:
            assert resolved[band].is_file()

    def test_missing_required_band(self, tmp_path):
        config = {
            "bands": {
                "B03": "a.tif",
                "B04": "b.tif",
                # B08 and SCL missing
            }
        }
        with pytest.raises(ValueError, match="B08"):
            resolve_band_paths(config, base_dir=tmp_path)

    def test_file_not_found(self, tmp_path):
        config = {
            "bands": {
                "B03": "nonexistent_b03.tif",
                "B04": "nonexistent_b04.tif",
                "B08": "nonexistent_b08.tif",
                "SCL": "nonexistent_scl.tif",
            }
        }
        with pytest.raises(FileNotFoundError, match="B03"):
            resolve_band_paths(config, base_dir=tmp_path)

    def test_empty_path_value(self, tmp_path):
        config = {
            "bands": {
                "B03": "",
                "B04": "b.tif",
                "B08": "c.tif",
                "SCL": "d.tif",
            }
        }
        with pytest.raises(ValueError, match="empty"):
            resolve_band_paths(config, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Tests — inspect_raster
# ---------------------------------------------------------------------------

class TestInspectRaster:
    """Tests for single-raster metadata inspection."""

    def test_inspect_valid_raster(self, tmp_path):
        fpath = _create_test_tif(
            tmp_path / "band.tif", width=200, height=150, dtype="uint16"
        )
        meta = inspect_raster("B03", fpath)
        assert isinstance(meta, RasterMeta)
        assert meta.band_name == "B03"
        assert meta.width == 200
        assert meta.height == 150
        assert meta.dtype == "uint16"
        assert meta.crs is not None
        assert meta.count == 1

    def test_inspect_nodata(self, tmp_path):
        fpath = _create_test_tif(tmp_path / "nd.tif", nodata=65535)
        meta = inspect_raster("B04", fpath)
        assert meta.nodata == 65535

    def test_inspect_no_nodata(self, tmp_path):
        fpath = _create_test_tif(tmp_path / "nn.tif", nodata=None)
        meta = inspect_raster("B08", fpath)
        assert meta.nodata is None

    def test_inspect_pixel_size(self, tmp_path):
        # 100x100 pixels spanning 1000 m → 10 m/pixel
        transform = from_bounds(0, 0, 1000, 1000, 100, 100)
        fpath = _create_test_tif(
            tmp_path / "ps.tif", width=100, height=100, transform=transform
        )
        meta = inspect_raster("B03", fpath)
        assert meta.pixel_size_x == pytest.approx(10.0)
        assert meta.pixel_size_y == pytest.approx(10.0)

    def test_summary_string(self, tmp_path):
        fpath = _create_test_tif(tmp_path / "s.tif")
        meta = inspect_raster("B03", fpath)
        summary = meta.summary()
        assert "B03" in summary
        assert "CRS" in summary
        assert "Dimensions" in summary


# ---------------------------------------------------------------------------
# Tests — inspect_all_bands
# ---------------------------------------------------------------------------

class TestInspectAllBands:
    """Tests for batch metadata inspection."""

    def test_inspect_all(self, tmp_path):
        band_files = _create_band_files(tmp_path)
        metadata = inspect_all_bands(band_files)
        assert set(metadata.keys()) == set(REQUIRED_BANDS)
        for meta in metadata.values():
            assert isinstance(meta, RasterMeta)
