# GeoPulse-ThermalAI

Satellite monitoring for **crop vegetation stress**, **crop water stress indicators**, and **surface-water extent** using multispectral and thermal Earth Observation data.

> [!NOTE]
> **Day 1 (current)** implements raster input validation and metadata inspection only.
> It does not yet perform NDVI/NDWI computation, thermal calibration, TVDI,
> evapotranspiration estimation, Dynamic World integration, machine learning,
> or dashboard visualization. These are planned for Days 2–5.

## Current Scope (Day 1)

- Load Sentinel-2 L2A band file paths from YAML configuration.
- Identify and validate B03 (green), B04 (red), B08 (NIR), and SCL bands.
- Inspect raster metadata: dimensions, CRS, affine transform, pixel size, dtype, nodata, bounds.
- Detect incompatible grids (CRS, dimensions, transform mismatches).
- Print a concise metadata report.
- Automated test suite with 26 tests.

## Future Scope (Days 2–5)

- Radiometric calibration with processing-baseline-aware scale/offset.
- NDVI and NDWI computation.
- Landsat 8/9 TIRS thermal band integration.
- TVDI (Temperature Vegetation Dryness Index) estimation.
- Dynamic World land-cover classification integration.
- Streamlit dashboard for monitoring and visualization.

## Repository Structure

```
GeoPulse-ThermalAI/
├── README.md                  # This file
├── requirements.txt           # Python dependencies
├── .gitignore                 # Git ignore rules
├── configs/
│   └── sample.yaml            # Band file path configuration
├── data/
│   └── sample/
│       └── README.md          # Instructions for obtaining sample data
├── src/
│   └── geopulse/
│       ├── __init__.py        # Package init
│       ├── io.py              # Config loading & raster metadata inspection
│       └── preprocessing.py   # Spatial validation
├── scripts/
│   └── run_sample.py          # CLI entry point
├── tests/
│   ├── test_io.py             # Tests for io module
│   └── test_preprocessing.py  # Tests for preprocessing module
└── outputs/
    └── .gitkeep               # Placeholder for generated outputs
```

## Setup

### 1. Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Dataset Setup

See [`data/sample/README.md`](data/sample/README.md) for instructions on obtaining Sentinel-2 L2A sample data.

After downloading, update `configs/sample.yaml` with the actual file paths:

```yaml
bands:
  B03: data/sample/YOUR_B03_FILE.tif
  B04: data/sample/YOUR_B04_FILE.tif
  B08: data/sample/YOUR_B08_FILE.tif
  SCL: data/sample/YOUR_SCL_FILE.tif
```

## Usage

### Run Validation

```bash
python scripts/run_sample.py --config configs/sample.yaml
```

For verbose output:

```bash
python scripts/run_sample.py --config configs/sample.yaml --verbose
```

### Expected Output (success)

```
============================================================
  GeoPulse-ThermalAI — Raster Metadata Report
============================================================

  Band        : B03
  File        : data/sample/B03.tif
  Dimensions  : 100 x 100
  CRS         : EPSG:32643
  Pixel size  : (10.0, 10.0)
  Data type   : uint16
  ...

✓ Spatial validation PASSED.

Day 1 validation complete. All checks passed.
```

### Expected Output (failure — missing file)

```
[ERROR] geopulse: Path resolution error: Band 'B03' file not found: /path/to/missing_file
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0    | All validations passed |
| 1    | Validation failure (missing files, grid mismatch, etc.) |
| 2    | Configuration or usage error |

## Running Tests

```bash
python -m pytest tests/ -v
```

All 26 tests use synthetic temporary GeoTIFFs — no external data downloads required.

## Known Limitations

- Radiometric scaling is **not** applied. Sentinel-2 DN values are reported as-is. Scaling depends on the product's processing baseline (quantification value + additive offset) and will be implemented in Day 2.
- SCL (Scene Classification Layer) may have a different resolution (20 m) than B03/B04/B08 (10 m). Day 1 reports this mismatch but does not resample. Any future reprojection of SCL must use **nearest-neighbor** resampling (categorical data).
- No automatic reprojection is performed. Incompatible grids produce an error.
- Configuration paths are relative to the repository root by default.

## License

Sentinel-2 data is provided under the [Copernicus Sentinel Data Terms and Conditions](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice).
