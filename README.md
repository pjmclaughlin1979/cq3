# City Quays 3 — ArcGIS Indoors model

**Live viewer:** https://pjmclaughlin1979.github.io/cq3/

**Downloads:** [File geodatabase (CQ3_Indoors.gdb.zip)](https://pjmclaughlin1979.github.io/cq3/downloads/CQ3_Indoors.gdb.zip) ·
GeoJSON: [Units](data/Units.geojson), [Levels](data/Levels.geojson), [Details](data/Details.geojson), [Facilities](data/Facilities.geojson), [Sites](data/Sites.geojson)

An indoor model of City Quays 3 (92 Donegall Quay, Belfast), generated from the
RPP Architects general arrangement plans `CQ3_FP.pdf` (drawing series
`2403-RPP-01-ZZ-DR-A-2xx`, scale 1:100).

* `index.html` — 3D viewer (ArcGIS Maps SDK for JavaScript 5.1) with a floor filter,
  rooms coloured by use, extruded walls and a glass shell for the other floors.
  It must be served over HTTP (double-clicking `index.html` will not load the data):

  ```
  cd cq3
  python -m http.server 8000      # or: python3 -m http.server 8000
  ```
  then open <http://localhost:8000/> in Chrome, Edge or Firefox. An internet
  connection is needed for the ArcGIS library and the satellite basemap.
* `data/*.geojson` — the model, one file per ArcGIS Indoors layer:

| File | Geometry | Contents |
| --- | --- | --- |
| `Sites.geojson` | polygon | City Quays site (`SITE_ID`) |
| `Facilities.geojson` | polygon | the building (`FACILITY_ID` = `CQ3`) |
| `Levels.geojson` | polygon | 16 floorplates, `LEVEL_ID`, `LEVEL_NUMBER`, `VERTICAL_ORDER`, `ELEVATION_RELATIVE`, `HEIGHT_RELATIVE` |
| `Units.geojson` | polygon | rooms, cores, offices and terraces with `NAME`, `USE_TYPE`, `ROOM_NUMBER`, `LEVEL_ID` and an area check |
| `Details.geojson` | line | wall faces (`USE_TYPE` = `Wall`) |

Field names follow the ArcGIS Indoors Information Model (Facilities, Levels,
Units, Details with `FACILITY_ID` / `LEVEL_ID` keys), so the layers work as
floor-aware layers in ArcGIS Pro, Map Viewer and the JavaScript SDK.

* `tools/` — the extraction and build scripts (Python). `tools/work/` holds the
  per-sheet extraction results, so the GeoJSON can be rebuilt without re-running
  the slow extraction.

## Rebuilding the data

```
pip install pymupdf shapely opencv-python-headless scipy numpy
export CQ3_PDF=/path/to/CQ3_FP.pdf          # the floor plan PDF (not included)
python3 tools/build.py                      # data/*.geojson from tools/work/
tools/run.sh                                # full re-extraction from the PDF (~2 min per sheet)
```

## File geodatabase

`downloads/CQ3_Indoors.gdb.zip` holds `CQ3_Indoors.gdb` with feature classes
Sites, Facilities, Levels, Units and Details, in Irish Transverse Mercator
(EPSG:2157), Z-enabled with Z at each floor's elevation. Unzip it and add it to
ArcGIS Pro. It is a plain geodatabase with Indoors layer and field names, not a
full Indoors database (no domains, relationship classes or attribute rules);
to get those, append it into a database made with **Create Indoors Database**
(steps below). Rebuild it with `python3 tools/export_gdb.py`.

## Loading into ArcGIS Pro / ArcGIS Indoors

1. Run **Create Indoors Database** (Indoors toolbox) to make an empty Indoors
   geodatabase in WGS 1984 or your project's coordinate system.
2. Use **Append** (field mapping by name) to load the feature classes from
   `CQ3_Indoors.gdb` into the matching Indoors feature classes: Sites,
   Facilities, Levels, Units, Details. (Or run **JSON To Features** on the
   GeoJSON files first and append those.)
4. Set the map's floor-awareness (Map Properties → Floors) to the Sites,
   Facilities and Levels layers if Pro does not detect it automatically.

The GeoJSON is 2D (WGS84) with elevations stored as attributes
(`ELEVATION_RELATIVE`, metres above ground floor), which is how Indoors stores
vertical position.

## How it was made

1. **Scale and grid.** The plans are vector CAD at 1:100 (1 pt = 35.28 mm).
   The structural grid bubbles give the origin (A/01) and confirm the scale:
   bays measure 3.80 m and 6.00 m, matching the dimension strings
   (3800 + 7 × 6000 + 3800 × 2250 / 9040 / 9020 / 1690 / 6850 / 500 / 2250 mm).
2. **Walls.** Wall lines are separated from hatching, fixtures, tags and grid
   lines by line weight, dash pattern, orientation and length.
3. **Rooms.** Every room tag (number, name, area) is read from the PDF text.
   Each room is flood-filled from its tag inside the wall raster (2 cm pixels),
   trying several wall sets and door-closing radii and keeping the result whose
   area best matches the printed area. The two stairs and the lift lobby use
   exact wall-face rectangles instead (stair treads and open lobby ends defeat
   the flood fill).
4. **Checks.** Each unit carries `AREA_PLAN_M2` (printed), `AREA_MODEL_M2`
   (measured) and `AREA_DIFF_PCT`. Across the nine drawn sheets, 251 of 252
   labelled rooms are within 10 % of the printed area and 199 within 5 %
   (traced outlines get a calibrated 2 cm offset to reach the wall face). The
   outlier is the ground-floor accessible WC (−11 %).
5. **Georeferencing.** The sheet's north arrow puts sheet-up at a bearing of
   35.5°. The building centre is placed at an approximate position (see below).

## Assumptions and limits

* **Location was fitted by eye.** No survey coordinates were available. The
  building centre is at 54.60438° N, 5.91984° W: a first estimate moved 60 m
  north-east after checking against satellite imagery. Orientation comes from
  the plan's north arrow (sheet-up = 35.5°). To adjust, change `ANCHOR` (and
  `BEARING` if needed) in `tools/build.py` and run `python3 tools/build.py`.
* **Levels not on the drawings are inferred.** Sheets exist for Ground, 01, 04,
  06, 08, 09, 13, 14 and 15. Levels 02, 03, 05, 07 and 10 copy the nearest
  typical floor; levels 11 and 12 are LV09 less the "LV 11 terrace" strip shown
  on the upper-floor sheets. `SOURCE_NOTE` records this for every level and unit.
* **Heights are assumed.** No sections were supplied: ground floor 5.0 m,
  typical floors 3.9 m floor-to-floor. The building is reported as 70.3 m tall
  including rooftop plant.
* **Shell and core only.** The plans note that office fit-out is by others, so
  office floors are single open-plan units.
* Terraces are derived as the floorplate below minus the floorplate above.
* The LV13 Wellbeing Centre has no area tag; its outline is flood-filled only.
