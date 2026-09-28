"""Export data/*.geojson to an Esri File Geodatabase (downloads/CQ3_Indoors.gdb.zip).

Feature classes use the ArcGIS Indoors layer names and field names. Geometry is
projected to Irish Transverse Mercator (EPSG:2157, metres) and made Z-aware, with
Z set to each feature's floor elevation (ELEVATION_RELATIVE).

    pip install geopandas pyogrio        # GDAL >= 3.6 (OpenFileGDB write support)
    python3 tools/export_gdb.py
"""
import os, shutil, zipfile
import geopandas as gpd
import shapely

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "downloads")
GDB = os.path.join(OUT_DIR, "CQ3_Indoors.gdb")
CRS = "EPSG:2157"                                    # Irish Transverse Mercator

INT_FIELDS = {"LEVEL_NUMBER", "VERTICAL_ORDER", "LEVELS"}
LAYERS = ["Sites", "Facilities", "Levels", "Units", "Details"]

os.makedirs(OUT_DIR, exist_ok=True)
shutil.rmtree(GDB, ignore_errors=True)
for name in LAYERS:
    gdf = gpd.read_file(os.path.join(DATA, f"{name}.geojson")).to_crs(CRS)
    z = gdf["ELEVATION_RELATIVE"].fillna(0).astype(float).to_numpy() if "ELEVATION_RELATIVE" in gdf else 0.0
    gdf["geometry"] = shapely.force_3d(gdf.geometry.values, z)
    if gdf.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        gdf["geometry"] = [shapely.MultiPolygon([g]) if g.geom_type == "Polygon" else g for g in gdf.geometry]
    for col in gdf.columns:
        if col in INT_FIELDS: gdf[col] = gdf[col].astype("Int32")
    gdf.to_file(GDB, layer=name, driver="OpenFileGDB", engine="pyogrio")
    print(f"{name}: {len(gdf)} features, {gdf.geom_type.iloc[0]}, Z={gdf.has_z.all()}")

zpath = os.path.join(OUT_DIR, "CQ3_Indoors.gdb.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for dirpath, _, files in os.walk(GDB):
        for f in files:
            full = os.path.join(dirpath, f)
            z.write(full, os.path.relpath(full, OUT_DIR))
shutil.rmtree(GDB)
print("wrote", zpath, os.path.getsize(zpath), "bytes")
