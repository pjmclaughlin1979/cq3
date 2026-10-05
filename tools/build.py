"""Build an ArcGIS Indoors-style dataset (GeoJSON) for City Quays 3 from the extracted rooms."""
import json, math, re, os, sys
import pymupdf
from shapely.geometry import Polygon, MultiPolygon, LineString, mapping, box
from shapely.ops import unary_union
from shapely import affinity

sys.path.insert(0, os.path.dirname(__file__))
from extract import PDF, K, wall_segments

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
os.makedirs(OUT, exist_ok=True)

# ---- georeference ---------------------------------------------------------------------------
# Local frame: metres, origin at grid intersection A/01, x to the right of the sheet, y up the sheet.
# The sheet's north arrow points 35.5 degrees anticlockwise of sheet-up, so sheet-up bears 35.5 deg.
BEARING = 35.5
ANCHOR = (54.604805, -5.920215)        # building centre (structural grid centre), as supplied
T = math.radians(BEARING)

SHEETS = {0: "00", 1: "01", 2: "04", 3: "06", 4: "08", 5: "09", 6: "13", 7: "14", 8: "15"}
data = {pi: json.load(open(os.path.join(WORK, f"rooms_{pi}.json"))) for pi in SHEETS}

def page_to_local(pi):
    cols, rows = data[pi]["cols"], data[pi]["rows"]
    xA, y01 = cols["A"], rows["01"]
    return lambda x, y: ((x - xA) * K, (y01 - y) * K)

# centre of the grid (A..J, 01..08) in local metres, used as the anchor point
c0 = page_to_local(2)
gx = (data[2]["cols"]["J"] - data[2]["cols"]["A"]) * K
gy = (data[2]["rows"]["08"] - data[2]["rows"]["01"]) * K
CX, CY = gx / 2, -gy / 2

def to_lonlat(x, y):
    dx, dy = x - CX, y - CY
    e = dx * math.cos(T) + dy * math.sin(T)
    n = -dx * math.sin(T) + dy * math.cos(T)
    lat = ANCHOR[0] + n / 111320.0
    lon = ANCHOR[1] + e / (111320.0 * math.cos(math.radians(ANCHOR[0])))
    return [round(lon, 8), round(lat, 8)]

def geo(geom):
    if geom.is_empty: return None
    if isinstance(geom, Polygon): geom = MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        polys = []
        for p in geom.geoms:
            p = p.buffer(0) if not p.is_valid else p
            ext = [to_lonlat(*c) for c in p.exterior.coords]
            polys.append([ext] + [[to_lonlat(*c) for c in i.coords] for i in p.interiors])
        return {"type": "MultiPolygon", "coordinates": polys} if len(polys) > 1 else {"type": "Polygon", "coordinates": polys[0]}
    if isinstance(geom, LineString):
        return {"type": "LineString", "coordinates": [to_lonlat(*c) for c in geom.coords]}
    raise ValueError(geom.geom_type)

# ---- rooms -> shapely in local metres ---------------------------------------------------------
def room_name(page, r):
    """Name printed with the room tag: the text line between the number and the area."""
    sx, sy = r["seed"]
    best = None
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if not t or re.fullmatch(r"[\d.]+( sq m)?|D\.[\d.]+", t): continue
            x0, y0, x1, y1 = l["bbox"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            d = abs(cx - sx) + abs(cy - sy)
            if abs(cx - sx) < 30 and abs(cy - sy) < 14 and (best is None or d < best[0]): best = (d, t)
    return best[1] if best else None

doc = pymupdf.open(PDF)
sheets = {}
for pi, lv in SHEETS.items():
    tf = page_to_local(pi)
    page = doc[pi]
    rooms = []
    for r in data[pi]["rooms"]:
        polys = []
        for ring, holes in r["polys"]:
            p = Polygon([tf(*c) for c in ring], [[tf(*c) for c in h] for h in holes])
            if not p.is_valid: p = p.buffer(0)
            polys.append(p)
        g = unary_union(polys) if polys else Polygon()
        # traced outlines sit one raster pixel inside the wall face; a 2 cm offset (calibrated against
        # every labelled room: median area error -4.7% -> +0.1%) restores it. Wall-face rectangles are exact.
        if r["method"] != "wall-rect" and not g.is_empty: g = g.buffer(0.02, join_style=2)
        rooms.append({"id": r["id"], "name": room_name(page, r), "area_label": r["area"], "area_model": round(g.area, 1),
                      "err": r["err"], "method": r["method"], "geom": g})
    walls = []
    V, H = wall_segments(page)
    for x, a, b in V:
        if (b - a) * K > 0.9: walls.append(LineString([tf(x, a), tf(x, b)]))
    for y, a, b in H:
        if (b - a) * K > 0.9: walls.append(LineString([tf(a, y), tf(b, y)]))
    sheets[lv] = {"rooms": rooms, "walls": walls}
    print(lv, len(rooms), "rooms", len(walls), "wall lines")

# Wellbeing Centre on LV13 has no area tag: flood from its title text
def wellbeing():
    from extract import labels, wall_rasters, region_at, to_polys, _cache, PX
    import numpy as np
    page = doc[6]
    hit = [w for w in page.get_text("words") if w[4] == "WELLBEING"]
    if not hit: return None
    w = hit[0]
    labs, lines = labels(page)
    _cache.clear()
    sets = wall_rasters(page, lines)
    m = region_at(sets[2], ((w[0] + w[2]) / 2 + 20, (w[1] + w[3]) / 2 + 9), 10)
    if m is None: return None
    tf = page_to_local(6)
    ps = [Polygon([tf(*c) for c in ring], [[tf(*c) for c in h] for h in holes]).buffer(0) for ring, holes in to_polys(m)]
    return unary_union(ps)
gf_tf = page_to_local(0)
GF_OUTLINE = Polygon([gf_tf(*c) for c in json.load(open(os.path.join(WORK, "outline_0.json")))]).buffer(0)
rest = GF_OUTLINE.difference(unary_union([r["geom"] for r in sheets["00"]["rooms"]]).buffer(0.25, join_style=2))
rest = rest.buffer(-0.3, join_style=2).buffer(0.3, join_style=2)
for p in sorted((rest.geoms if hasattr(rest, "geoms") else [rest]), key=lambda p: -p.area):
    if p.area < 20: continue
    big = p.area > 300
    sheets["00"]["rooms"].append({"id": None, "name": "Entrance and reception" if big else "Untagged space",
        "area_label": None, "area_model": round(p.area, 1), "err": None, "method": "outline minus tagged rooms", "geom": p})
    print("GF untagged", round(p.area, 1))
wb = wellbeing()
if wb is not None and 50 < wb.area < 600:
    sheets["13"]["rooms"].append({"id": "13.27", "name": "Wellbeing Centre", "area_label": None, "area_model": round(wb.area, 1), "err": None, "method": "flood (no area tag)", "geom": wb})
    print("wellbeing", round(wb.area, 1))

# ---- use types ----------------------------------------------------------------------------
def use_type(name, rid):
    n = (name or "").lower()
    if n.startswith("office"): return "Office"
    if n.startswith("lift lobby"): return "Lift Lobby"
    if n.startswith("lift"): return "Elevator"
    if n.startswith("stair"): return "Stairs"
    if "dis" in n and ("wc" in n or "w/c" in n): return "Restroom - Accessible"
    if re.search(r"\bm wc\b|male wc", n) and "female" not in n: return "Restroom - Male"
    if re.search(r"\bf wc\b|female wc", n): return "Restroom - Female"
    if "wc supply" in n or "wc extract" in n or "smk" in n or n in ("wr", "service") or "plant" in n: return "Mechanical"
    if "ff core" in n or "f.f. core" in n: return "Firefighting Lobby"
    if "lobby" in n or "corridor" in n: return "Circulation"
    if "clnr" in n: return "Janitor"
    if any(k in n for k in ("switchboard", "electrical", "nie", "data", "telecom")): return "Electrical / Data"
    if "refuse" in n: return "Refuse Store"
    if "wellbeing" in n: return "Wellbeing"
    if "reception" in n: return "Reception"
    if "room" in n: return "Support"
    if not name and rid and re.fullmatch(r"\d+", rid): return "Parking"
    return "Unassigned"

# ---- levels -------------------------------------------------------------------------------
GF_H, TYP_H = 5.0, 3.9               # assumed floor-to-floor heights (sections not supplied)
BASE_ELEV = 3.5                      # ground floor level above datum (m); ELEVATION_ABSOLUTE = BASE_ELEV + ELEVATION_RELATIVE
def footprint(rooms, src=None):
    if src == "00": return GF_OUTLINE
    u = unary_union([r["geom"] for r in rooms if not r["geom"].is_empty])
    u = u.buffer(0.45, join_style=2).buffer(-0.15, join_style=2)
    parts = [Polygon(p.exterior) for p in (u.geoms if hasattr(u, "geoms") else [u]) if p.area > 30]
    return unary_union(parts)

# LV11 terrace strip (shown on the LV13/14 sheets): the part of the LV09 floorplate west of the
# LV13 office's western facade and south of the core
lv13_office = next(r["geom"] for r in sheets["13"]["rooms"] if (r["name"] or "").startswith("Office"))
lv09_fp = footprint(sheets["09"]["rooms"])
minx13 = lv13_office.bounds[0]
core_south = min(r["geom"].bounds[1] for r in sheets["09"]["rooms"] if (r["name"] or "").startswith(("Stair", "Lift ")))
strip = box(-10, -60, minx13 - 0.3, core_south)
def clip_rooms(rooms, cutter):
    out = []
    for r in rooms:
        g = r["geom"].difference(cutter)
        if g.area < 0.5: continue
        out.append(dict(r, geom=g, area_model=round(g.area, 1), area_label=r["area_label"] if g.area > r["geom"].area - 0.5 else None,
                        err=r["err"] if g.area > r["geom"].area - 0.5 else None))
    return out

PLAN = [  # level number -> (source sheet, how)
    (0, "00", "drawn"), (1, "01", "drawn"), (2, "04", "inferred: typical floor, as LV04"), (3, "04", "inferred: typical floor, as LV04"),
    (4, "04", "drawn"), (5, "04", "inferred: typical floor, as LV04"), (6, "06", "drawn"), (7, "06", "inferred: typical floor, as LV06"),
    (8, "08", "drawn"), (9, "09", "drawn"), (10, "09", "inferred: typical floor, as LV09"),
    (11, "09", "inferred: LV09 less the LV11 terrace strip"), (12, "09", "inferred: LV09 less the LV11 terrace strip"),
    (13, "13", "drawn"), (14, "14", "drawn"), (15, "15", "drawn")]

FAC = "CQ3"
features = {k: [] for k in ("Sites", "Facilities", "Levels", "Units", "Details")}
elev = 0.0
prev_fp = None
qa = []
used_ids = set()
for num, src, how in PLAN:
    rooms = sheets[src]["rooms"]
    walls = sheets[src]["walls"]
    if num in (11, 12):
        rooms = clip_rooms(rooms, strip)
        walls = [w.difference(strip) for w in walls]
        walls = [w for w in walls if not w.is_empty and w.geom_type == "LineString"]
    fp = footprint(rooms, src)
    lid = f"{FAC}.L{num:02d}"
    h = GF_H if num == 0 else TYP_H
    name = "Ground Floor" if num == 0 else f"Level {num:02d}"
    features["Levels"].append({"type": "Feature", "geometry": geo(fp), "properties": {
        "LEVEL_ID": lid, "NAME": name, "NAME_SHORT": f"{num:02d}", "LEVEL_NUMBER": num, "VERTICAL_ORDER": num,
        "FACILITY_ID": FAC, "ELEVATION_RELATIVE": round(elev, 2), "ELEVATION_ABSOLUTE": round(BASE_ELEV + elev, 2), "HEIGHT_RELATIVE": h,
        "SOURCE_SHEET": f"LV {src} - GA", "SOURCE_NOTE": how, "AREA_GROSS_M2": round(fp.area, 1)}})
    for k, r in enumerate(rooms):
        if r["geom"].is_empty: continue
        rid = r["id"] or "x"
        uid = f"{FAC}.{num:02d}.{rid.split('.')[-1]}" if r["id"] else f"{FAC}.{num:02d}.U{k}"
        while uid in used_ids: uid += "b"                      # the ground floor plan repeats tag "74"
        used_ids.add(uid)
        err = None if r["err"] is None or r["area_label"] is None else round(100 * (r["area_model"] - r["area_label"]) / r["area_label"], 1)
        features["Units"].append({"type": "Feature", "geometry": geo(r["geom"]), "properties": {
            "UNIT_ID": uid, "NAME": r["name"] or (f"Space {rid}" if rid != "x" else "Space"), "USE_TYPE": use_type(r["name"], r["id"]),
            "LEVEL_ID": lid, "FACILITY_ID": FAC, "ELEVATION_RELATIVE": round(elev, 2), "ELEVATION_ABSOLUTE": round(BASE_ELEV + elev, 2), "HEIGHT_RELATIVE": h,
            "ROOM_NUMBER": f"{num:02d}.{rid.split('.')[-1]}" if "." in rid else rid,
            "AREA_PLAN_M2": r["area_label"], "AREA_MODEL_M2": r["area_model"], "AREA_DIFF_PCT": err, "SOURCE_NOTE": how}})
        if how == "drawn": qa.append((num, rid, r["name"], r["area_label"], r["area_model"], err, r["method"]))
    if prev_fp is not None:
        terr = prev_fp.difference(fp.buffer(0.2, join_style=2))
        for p in (terr.geoms if hasattr(terr, "geoms") else [terr]):
            if p.area > 15 and p.minimum_rotated_rectangle.area and min(p.bounds[2] - p.bounds[0], p.bounds[3] - p.bounds[1]) > 1.5:
                features["Units"].append({"type": "Feature", "geometry": geo(p), "properties": {
                    "UNIT_ID": f"{FAC}.{num:02d}.T{len(features['Units'])}",
                    # LV14's step back is the roof over the LV13 Wellbeing Centre ("LV 14 ROOF" on the sheet)
                    "NAME": "Roof over Wellbeing Centre" if num == 14 else f"Level {num:02d} Terrace", "USE_TYPE": "Roof" if num == 14 else "Terrace",
                    "LEVEL_ID": lid, "FACILITY_ID": FAC, "ELEVATION_RELATIVE": round(elev, 2), "ELEVATION_ABSOLUTE": round(BASE_ELEV + elev, 2), "HEIGHT_RELATIVE": 0,
                    "ROOM_NUMBER": None, "AREA_PLAN_M2": None, "AREA_MODEL_M2": round(p.area, 1), "AREA_DIFF_PCT": None,
                    "SOURCE_NOTE": "derived: floorplate below minus this floorplate"}})
    # keep only walls inside this floorplate (the sheets also carry landscaping, section and detail lines)
    inside = fp.buffer(0.6, join_style=2)
    walls = [w for w in walls if inside.contains(w)]
    for i, w in enumerate(walls):
        features["Details"].append({"type": "Feature", "geometry": geo(w), "properties": {
            "DETAIL_ID": f"{lid}.W{i}", "USE_TYPE": "Wall", "LEVEL_ID": lid, "FACILITY_ID": FAC, "ELEVATION_RELATIVE": round(elev, 2),
            "ELEVATION_ABSOLUTE": round(BASE_ELEV + elev, 2)}})
    prev_fp = fp
    elev += h

roof = elev
fp_all = unary_union([footprint(sheets[s]["rooms"], s) for s in ("00", "04")])
features["Facilities"].append({"type": "Feature", "geometry": geo(fp_all), "properties": {
    "FACILITY_ID": FAC, "NAME": "City Quays 3", "NAME_LONG": "City Quays 3, 92 Donegall Quay, Belfast BT1 3FE", "SITE_ID": "CQ",
    "ELEVATION_RELATIVE": 0, "ELEVATION_ABSOLUTE": BASE_ELEV, "HEIGHT_RELATIVE": round(roof, 2), "HEIGHT_REPORTED_M": 70.3, "LEVELS": 16}})
features["Sites"].append({"type": "Feature", "geometry": geo(fp_all.buffer(25, join_style=2)), "properties": {
    "SITE_ID": "CQ", "NAME": "City Quays", "NAME_LONG": "City Quays, Belfast Harbour"}})

for k, fs in features.items():
    json.dump({"type": "FeatureCollection", "name": k, "features": fs}, open(os.path.join(OUT, f"{k}.geojson"), "w"))
    print(k, len(fs))
json.dump([list(q) for q in qa], open(os.path.join(WORK, "qa.json"), "w"))
print("roof of LV15 at", roof)
