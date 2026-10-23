# Sample Sentinel-2 Data

## Obtaining a Small Sentinel-2 Level-2A Sample

This directory should contain a small Sentinel-2 Level-2A (L2A) sample covering
an area of interest with crop fields and/or surface-water bodies.

### Required Band Files

| Band | Description               | Resolution | Data Type |
|------|---------------------------|------------|-----------|
| B03  | Green                     | 10 m       | UInt16    |
| B04  | Red                       | 10 m       | UInt16    |
| B08  | Near-Infrared (NIR)       | 10 m       | UInt16    |
| SCL  | Scene Classification Layer| 20 m       | UInt8     |

### Spatial Grid Compatibility

- B03, B04, and B08 share the same 10 m grid (identical CRS, dimensions, and
  affine transform).
- SCL uses a 20 m grid. If your pipeline requires identical grids for all bands,
  SCL must be resampled to 10 m using **nearest-neighbor** resampling (it is a
  categorical raster — do not use bilinear or cubic interpolation).

### Where to Download

1. **Copernicus Data Space Ecosystem** (recommended):
   - URL: https://dataspace.copernicus.eu/
   - Registration: Free account required.
   - Search for "Sentinel-2 Level-2A" products.
   - Select a tile covering your area of interest (e.g., a crop-growing region).
   - Download a single granule and extract the relevant band files from:
     `GRANULE/*/IMG_DATA/R10m/` (for B03, B04, B08) and
     `GRANULE/*/IMG_DATA/R20m/` (for SCL).

2. **Google Earth Engine** (alternative):
   - Collection: `COPERNICUS/S2_SR_HARMONIZED`
   - Export individual bands as GeoTIFF for a small region.

3. **AWS Open Data — Sentinel-2 COGs**:
   - URL: https://registry.opendata.aws/sentinel-2-l2a-cogs/
   - License: Copernicus Sentinel Data Terms and Conditions.
   - Files are Cloud Optimized GeoTIFFs (COG).

### Recommended Sample

- **Region**: Any agricultural area with mixed crops and a nearby water body.
- **Tile size**: A small subset (e.g., 1000×1000 pixels) is sufficient for
  development and testing.
- **Cloud cover**: Select a scene with <10% cloud cover.
- **Season**: Growing season preferred for visible vegetation signal.

### License

Sentinel-2 data is provided free of charge under the
[Copernicus Sentinel Data Terms and Conditions](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice).

### After Downloading

1. Place the band files in this directory (`data/sample/`).
2. Update `configs/sample.yaml` with the actual filenames.
3. Run the validation script:
   ```bash
   python scripts/run_sample.py --config configs/sample.yaml
   ```
