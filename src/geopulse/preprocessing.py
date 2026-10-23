"""
geopulse.preprocessing — Spatial validation for multi-band raster inputs.

This module validates that a set of raster inputs share a compatible spatial
grid so they can be processed together.

Validation is **resolution-group aware**:
- **Primary bands** (B03, B04, B08) are at 10 m resolution and must share
  identical CRS, dimensions, and affine transforms.
- **SCL** (Scene Classification Layer) is a categorical raster at 20 m
  resolution.  It is validated for CRS consistency and spatial-extent
  overlap with the primary bands, but its different resolution is expected
  and reported as an informational warning — not an error.

Design decisions:
- Day 1 does **not** perform automatic reprojection. If grids are
  incompatible the validator raises a clear error.
- Any future reprojection of SCL **must** use nearest-neighbor resampling
  to preserve class values (it is categorical, not continuous).
- Affine transform comparison uses a configurable absolute tolerance
  (default 1e-6) to handle floating-point representation differences.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .io import RasterMeta

logger = logging.getLogger(__name__)

# Default absolute tolerance for comparing affine transform coefficients.
# This accommodates floating-point serialization differences across formats
# (e.g. JP2 vs GeoTIFF) without silently accepting genuinely different grids.
TRANSFORM_ABS_TOL: float = 1e-6

# Bands that share the 10 m primary grid and must be strictly compatible.
PRIMARY_BANDS = ("B03", "B04", "B08")

# Bands at a different native resolution (20 m) that are validated for CRS
# and spatial-extent consistency but are expected to differ in dimensions
# and pixel size.
AUXILIARY_BANDS = ("SCL",)


@dataclass
class ValidationResult:
    """Container for spatial-validation outcomes."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.is_valid = False
        self.errors.append(message)
        logger.error(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)
        logger.warning(message)

    def add_info(self, message: str) -> None:
        self.info.append(message)
        logger.info(message)

    def summary(self) -> str:
        """Return a human-readable validation report."""
        lines: list[str] = []
        if self.is_valid:
            lines.append("✓ Spatial validation PASSED.")
        else:
            lines.append("✗ Spatial validation FAILED.")

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  • {e}")

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")

        if self.info:
            lines.append("")
            lines.append("Info:")
            for i in self.info:
                lines.append(f"  ℹ {i}")

        return "\n".join(lines)


def _transforms_close(
    a: tuple[float, ...],
    b: tuple[float, ...],
    tol: float = TRANSFORM_ABS_TOL,
) -> bool:
    """Check whether two affine transform tuples are element-wise close."""
    if len(a) != len(b):
        return False
    return all(math.isclose(ai, bi, abs_tol=tol) for ai, bi in zip(a, b))


def _bounds_close(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    tol: float = 1.0,
) -> bool:
    """Check whether two bounding boxes are close within *tol* map units.

    Default tolerance of 1.0 metre accommodates sub-pixel rounding
    differences between 10 m and 20 m grids covering the same tile.
    """
    return all(math.isclose(ai, bi, abs_tol=tol) for ai, bi in zip(a, b))


def _validate_primary_bands(
    metadata: dict[str, RasterMeta],
    transform_tol: float,
    result: ValidationResult,
) -> RasterMeta | None:
    """Validate strict grid compatibility among primary (10 m) bands.

    Returns the reference band metadata, or None if no primary bands exist.
    """
    primary = {k: v for k, v in metadata.items() if k in PRIMARY_BANDS}
    if not primary:
        return None

    band_names = list(primary.keys())
    reference_name = band_names[0]
    reference = primary[reference_name]

    for name in band_names[1:]:
        other = primary[name]

        # Dimensions
        if reference.width != other.width or reference.height != other.height:
            result.add_error(
                f"Dimension mismatch among 10 m bands: '{reference_name}' is "
                f"{reference.width}×{reference.height} "
                f"but '{name}' is {other.width}×{other.height}."
            )

        # Affine transform
        ref_coeffs = tuple(reference.transform)[:6]
        other_coeffs = tuple(other.transform)[:6]
        if not _transforms_close(ref_coeffs, other_coeffs, tol=transform_tol):
            result.add_error(
                f"Affine transform mismatch among 10 m bands: "
                f"'{reference_name}' has {ref_coeffs} but '{name}' has "
                f"{other_coeffs} (tolerance={transform_tol})."
            )

        # Pixel size (warning only — transform check is authoritative)
        if not math.isclose(
            reference.pixel_size_x, other.pixel_size_x, abs_tol=transform_tol
        ) or not math.isclose(
            reference.pixel_size_y, other.pixel_size_y, abs_tol=transform_tol
        ):
            result.add_warning(
                f"Pixel-size difference among 10 m bands: '{reference_name}' "
                f"({reference.pixel_size_x}, {reference.pixel_size_y}) vs "
                f"'{name}' ({other.pixel_size_x}, {other.pixel_size_y})."
            )

    return reference


def _validate_auxiliary_bands(
    metadata: dict[str, RasterMeta],
    reference: RasterMeta,
    transform_tol: float,
    result: ValidationResult,
) -> None:
    """Validate auxiliary bands (SCL at 20 m) against the primary reference.

    Checks CRS match and spatial-extent overlap.  Reports the expected
    resolution/dimension difference as informational, not as an error.
    """
    for name in AUXILIARY_BANDS:
        if name not in metadata:
            continue
        aux = metadata[name]

        # CRS must still match.
        if reference.crs != aux.crs:
            result.add_error(
                f"CRS mismatch: primary bands use {reference.crs} "
                f"but '{name}' uses {aux.crs}."
            )

        # Spatial extent (bounds) should cover the same area.
        ref_bounds = (
            reference.bounds.left,
            reference.bounds.bottom,
            reference.bounds.right,
            reference.bounds.top,
        )
        aux_bounds = (
            aux.bounds.left,
            aux.bounds.bottom,
            aux.bounds.right,
            aux.bounds.top,
        )
        if not _bounds_close(ref_bounds, aux_bounds):
            result.add_error(
                f"Spatial extent mismatch: primary bands cover "
                f"{ref_bounds} but '{name}' covers {aux_bounds}."
            )

        # Resolution difference is expected — report as info.
        if aux.pixel_size_x != reference.pixel_size_x or aux.pixel_size_y != reference.pixel_size_y:
            result.add_info(
                f"'{name}' is at {aux.pixel_size_x} m resolution "
                f"({aux.width}×{aux.height}) vs primary bands at "
                f"{reference.pixel_size_x} m ({reference.width}×{reference.height}). "
                f"Nearest-neighbor resampling to {reference.pixel_size_x} m "
                f"will be applied in a later processing step (SCL is categorical)."
            )


def validate_spatial_compatibility(
    metadata: dict[str, RasterMeta],
    transform_tol: float = TRANSFORM_ABS_TOL,
) -> ValidationResult:
    """Validate spatial compatibility across a set of raster inputs.

    Validation is **resolution-group aware**:

    1. **CRS check** — every raster must have a defined CRS; all CRS values
       must match.
    2. **Primary-band grid check** (B03, B04, B08) — dimensions and affine
       transforms must be identical within *transform_tol*.
    3. **Auxiliary-band check** (SCL) — CRS and spatial extent must match
       the primary bands.  Dimension and pixel-size differences are expected
       (20 m vs 10 m) and reported as informational.

    Parameters
    ----------
    metadata : dict[str, RasterMeta]
        Band-name → metadata mapping (from :func:`geopulse.io.inspect_all_bands`).
    transform_tol : float
        Absolute tolerance for comparing affine transform coefficients.

    Returns
    -------
    ValidationResult
        Contains ``is_valid`` flag plus any errors, warnings, or info.

    Notes
    -----
    SCL (Scene Classification Layer) is a categorical raster at 20 m
    resolution.  Any future reprojection of SCL **must** use
    nearest-neighbor interpolation to preserve class labels.  This module
    does **not** perform reprojection; it only validates compatibility and
    reports expected differences.
    """
    result = ValidationResult()

    if not metadata:
        result.add_error("No raster metadata provided for validation.")
        return result

    # --- 1. Check every raster has a CRS -----------------------------------
    for name, meta in metadata.items():
        if meta.crs is None:
            result.add_error(
                f"Band '{name}' ({meta.file_path}) has no CRS defined."
            )

    # If any CRS is missing, remaining checks are unreliable.
    if not result.is_valid:
        return result

    # --- 2. Global CRS consistency -----------------------------------------
    band_names = list(metadata.keys())
    first_name = band_names[0]
    first_crs = metadata[first_name].crs

    for name in band_names[1:]:
        if first_crs != metadata[name].crs:
            result.add_error(
                f"CRS mismatch: '{first_name}' has {first_crs} "
                f"but '{name}' has {metadata[name].crs}."
            )

    # If CRS differ, grid/extent checks are meaningless.
    if not result.is_valid:
        return result

    # --- 3. Primary bands — strict grid check ------------------------------
    reference = _validate_primary_bands(metadata, transform_tol, result)

    # --- 4. Auxiliary bands — CRS + extent check ---------------------------
    if reference is not None:
        _validate_auxiliary_bands(metadata, reference, transform_tol, result)

    # --- Summary -----------------------------------------------------------
    if result.is_valid:
        logger.info(
            "Spatial validation passed for bands: %s",
            ", ".join(band_names),
        )
    else:
        logger.error(
            "Spatial validation failed with %d error(s).", len(result.errors)
        )

    return result
