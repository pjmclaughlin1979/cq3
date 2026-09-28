import re, json, sys, numpy as np, cv2
from scipy import ndimage
from raster import *
K = 0.035278                     # metres per point at 1:100

def labels(page):
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t: lines.append((t, pymupdf.Rect(l["bbox"])))
    out = []
    for t, r in lines:
        m = re.fullmatch(r"(\d+(?:\.\d+)?) sq m", t)
        if not m: continue
        cx = (r.x0 + r.x1) / 2
        near = lambda rr, t2: abs((rr.x0 + rr.x1) / 2 - cx) < 12 and 0 < r.y0 - rr.y1 + 1 < 12
        # room number: an NN.NN tag just above the area (within ~2 lines); bare numbers only when none
        num = next(((t2, rr) for t2, rr in lines if abs((rr.x0 + rr.x1) / 2 - cx) < 12 and 0 < r.y0 - rr.y1 + 1 < 26 and re.fullmatch(r"\d\d\.\d\d", t2)), None) \
            or next(((t2, rr) for t2, rr in lines if near(rr, t2) and re.fullmatch(r"\d+", t2)), None)
        name = None
        if num:
            rn = num[1]
            name = next((t2 for t2, rr in lines if abs((rr.x0 + rr.x1) / 2 - cx) < 30 and 0 < rn.y0 - rr.y1 + 1 < 12), None)
        box = r if not num else r | num[1]
        if name: box = box | next(rr for t2, rr in lines if t2 == name and abs((rr.x0 + rr.x1) / 2 - cx) < 30 and 0 < box.y0 - rr.y1 + 1 < 14 or True)
        out.append({"area": float(m.group(1)), "id": num[0] if num else None, "name": name, "seed": ((r.x0 + r.x1) / 2, (r.y0 + (num[1].y0 if num else r.y0)) / 2), "bbox": list(box)})
    return out, lines

def grid(lines):
    cols = {t: (r.x0 + r.x1) / 2 for t, r in lines if re.fullmatch(r"[A-J]", t) and r.y0 > 1400}
    rows = {t: (r.y0 + r.y1) / 2 for t, r in lines if re.fullmatch(r"0[1-8]", t) and r.x0 < 190}
    return cols, rows

def wall_rasters(page, lines):
    tagboxes = [r + (-3, -3, 3, 3) for t, r in lines]
    drs = page.get_drawings()
    W, H = int(page.rect.width * PX) + 1, int(page.rect.height * PX) + 1
    def base(g):
        if g["type"] not in ("s", "fs"): return False
        if tuple(round(x, 2) for x in (g.get("color") or ())) != (0, 0, 0): return False
        if (g.get("dashes") or "[] 0") != "[] 0": return False
        r = g["rect"]
        if r.width > 1450 or r.height > 950: return False                                # grid lines drawn solid
        if r.width < 60 and r.height < 60 and any(tb.contains(r) for tb in tagboxes): return False
        if r.width < 40 and r.height < 40 and abs(r.width - r.height) < 1 and r.width > 8: return False   # door-tag bubbles
        return True
    def draw(img, g, keep_item=lambda it: True):
        w = max(1, int(round((g.get("width") or 0) * PX)))
        for it in g["items"]:
            if not keep_item(it): continue
            for pts in paths({"items": [it]}):
                cv2.polylines(img, [np.round(pts * PX).astype(np.int32)], False, 255, w)
    ortho = lambda it: it[0] != "l" or abs(it[1].x - it[2].x) < 0.3 or abs(it[1].y - it[2].y) < 0.3
    longline = lambda it: it[0] == "c" or (it[0] == "l" and ortho(it) and abs(it[1] - it[2]) > 57)   # arcs, or straight runs > 2 m
    s1, s2, s3, s4, s5 = (np.zeros((H, W), np.uint8) for _ in range(5))
    vlong = lambda it: it[0] == "c" or (it[0] == "l" and ortho(it) and abs(it[1] - it[2]) > 99)
    for g in drs:
        if not base(g): continue
        wd = g.get("width") or 0
        draw(s3, g)
        if wd >= 0.14: draw(s5, g, vlong)
        if wd >= 0.29: draw(s1, g); draw(s2, g); draw(s4, g)
        elif wd >= 0.14: draw(s2, g, ortho); draw(s4, g, longline)
    return [s4, s1, s2, s3, s5]

def disk(rpx):
    return cv2.getStructuringElement(cv2.MORPH_RECT, (2 * rpx + 1, 2 * rpx + 1))

def big_holes(m):
    # holes bigger than 1.5 m^2 (e.g. a core inside the office) stay holes; smaller ones (fixtures) are filled
    h = ndimage.binary_fill_holes(m) & ~m
    lab, n = ndimage.label(h)
    if not n: return np.zeros_like(m)
    sizes = ndimage.sum(h, lab, range(1, n + 1)) * 0.0004
    keep = np.isin(lab, np.nonzero(sizes > 1.5)[0] + 1)
    return keep

_cache = {}
def region_at(walls, seed, rpx):
    key = (id(walls), rpx)
    if key not in _cache:
        blocked = cv2.dilate(walls, disk(rpx)) if rpx else walls
        free = blocked == 0
        _cache[key] = (free, ndimage.label(free)[0])
    free, lab = _cache[key]
    sx, sy = int(seed[0] * PX), int(seed[1] * PX)
    # nearest free pixel to the seed (label text may sit on a line)
    ys, xs = np.nonzero(free[max(0, sy - 25):sy + 26, max(0, sx - 25):sx + 26])
    if not len(xs): return None
    k = np.argmin((xs - min(25, sx)) ** 2 + (ys - min(25, sy)) ** 2)
    L = lab[max(0, sy - 25) + ys[k], max(0, sx - 25) + xs[k]]
    ys_, xs_ = np.nonzero(lab == L)
    if ys_.min() == 0 or xs_.min() == 0 or ys_.max() == lab.shape[0] - 1 or xs_.max() == lab.shape[1] - 1: return None   # leaked outside
    if len(xs_) * 0.0004 > 4000: return None
    Y0, Y1, X0, X1 = max(0, ys_.min() - 40), ys_.max() + 41, max(0, xs_.min() - 40), xs_.max() + 41
    m = np.zeros(lab.shape, bool); m[Y0:Y1, X0:X1] = lab[Y0:Y1, X0:X1] == L
    sub = m[Y0:Y1, X0:X1]
    sub = ndimage.binary_fill_holes(sub) & ~big_holes(sub)
    sub = sub.astype(np.uint8) * 255
    if rpx: sub = cv2.dilate(sub, disk(rpx)) & (255 - walls[Y0:Y1, X0:X1])
    out = np.zeros(lab.shape, np.uint8); out[Y0:Y1, X0:X1] = sub
    return out

def to_polys(mask):
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for i, c in enumerate(cnts):
        if hier[0][i][3] != -1: continue
        if cv2.contourArea(c) < 20: continue
        ring = cv2.approxPolyDP(c, 1.5, True)[:, 0, :] / PX
        holes = []
        j = hier[0][i][2]
        while j != -1:
            if cv2.contourArea(cnts[j]) > 60: holes.append(cv2.approxPolyDP(cnts[j], 1.5, True)[:, 0, :] / PX)
            j = hier[0][j][0]
        polys.append((ring, holes))
    return polys

def wall_segments(page):
    V, Hs = [], []
    for g in page.get_drawings():
        if g["type"] not in ("s", "fs") or (g.get("width") or 0) < 0.29: continue
        if tuple(round(x, 2) for x in (g.get("color") or ())) != (0, 0, 0) or (g.get("dashes") or "[] 0") != "[] 0": continue
        r = g["rect"]
        if r.width > 1450 or r.height > 950: continue
        for it in g["items"]:
            if it[0] != "l": continue
            a, b = it[1], it[2]
            if abs(a.x - b.x) < 0.3 and abs(a.y - b.y) > 20: V.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            elif abs(a.y - b.y) < 0.3 and abs(a.x - b.x) > 20: Hs.append((a.y, min(a.x, b.x), max(a.x, b.x)))
    return V, Hs

def rect_fallback(seed, area, V, Hs, longwalls, occupied):
    # rectangle bounded by thick wall faces around the label, whose area matches the label and
    # whose interior is not crossed by any long wall (stair treads and fixtures are allowed)
    sx, sy = seed
    def cands(segs, c0, c1, pos, side):
        vals = {round(s_[0], 1) for s_ in segs if s_[1] <= c1 + 2 and s_[2] >= c0 - 2 and (s_[0] < pos - 2 if side < 0 else s_[0] > pos + 2)}
        return sorted(vals, key=lambda v: abs(v - pos))[:6]
    best = None
    for i, l in enumerate(cands(V, sy - 30, sy + 30, sx, -1)):
        for j, r in enumerate(cands(V, sy - 30, sy + 30, sx, 1)):
            for k, u in enumerate(cands(Hs, l, r, sy, -1)):
                for m, d in enumerate(cands(Hs, l, r, sy, 1)):
                    a_ = (r - l) * (d - u) * K * K
                    err = abs(a_ - area) / area + 0.003 * (i + j + k + m)
                    if best is not None and err >= best[0]: continue
                    X0, X1, Y0, Y1 = int(l * PX) + 8, int(r * PX) - 8, int(u * PX) + 8, int(d * PX) - 8
                    if X1 <= X0 or Y1 <= Y0 or (longwalls[Y0:Y1, X0:X1] > 0).mean() > 0.004: continue
                    if occupied[Y0:Y1, X0:X1].mean() > 0.03: continue
                    best = (err, (l, r, u, d), a_)
    return best

def extract(pi):
    page = pymupdf.open(PDF)[pi]
    labs, lines = labels(page)
    _cache.clear()
    sets = wall_rasters(page, lines)
    walls = sets[1]
    rooms = [dict(L, err=None, rpx=None, got=None, mask=None) for L in labs]
    # exact wall-face rectangles (page points) for rooms that flood fill cannot isolate on the
    # typical core: the two stairs (treads fragment them) and the lift lobby (open ends are doors)
    OVERRIDE = {"03": (653.6, 738.5, 707.3, 899.3), "22": (1362.3, 1447.2, 707.3, 899.3), "13": (1008.5, 1092.3, 707.3, 966.0)} if pi > 0 else \
               {"18": (653.6, 738.5, 707.3, 882.5), "36": (1362.3, 1447.2, 707.3, 882.5)}
    for r in rooms:
        if r["id"] and r["id"][-2:] in OVERRIDE and "." in r["id"]:
            l, r_, u, d = OVERRIDE[r["id"][-2:]]
            m = np.zeros(walls.shape, bool); m[int(u * PX):int(d * PX), int(l * PX):int(r_ * PX)] = True
            got = (r_ - l) * (d - u) * K * K
            r.update(err=abs(got - r["area"]) / r["area"], rpx="wall-rect", got=got, mask=m)
    for r in rooms:
        if r["mask"] is not None: continue
        best = None
        for si, W_ in enumerate(sets):
          for rpx in (0, 5, 10, 16, 22, 30):          # 0 .. 0.6 m closing radius
            m = region_at(W_, r["seed"], rpx)
            if m is None: continue
            a = (m > 0).sum() * 0.02 * 0.02
            err = abs(a - r["area"]) / r["area"]
            if best is None or err < best[0]: best = (err, (si, rpx), m > 0, a)
            if err < 0.03: break
          if best and best[0] < 0.03: break
        if best: r.update(err=best[0], rpx=best[1], got=best[3], mask=best[2])
    for r in rooms:
        r["polys"] = [] if r["mask"] is None else to_polys(r["mask"].astype(np.uint8) * 255)
    return page, labs, lines, walls, rooms

if __name__ == "__main__":
    pi = int(sys.argv[1])
    page, labs, lines, walls, rooms = extract(pi)
    cols, rows = grid(lines)
    print("cols", {k: round(v, 1) for k, v in sorted(cols.items())}); print("rows", {k: round(v, 1) for k, v in sorted(rows.items())})
    ok = 0
    for r in rooms:
        flag = "OK " if r["err"] is not None and r["err"] < 0.08 else "BAD"
        ok += flag == "OK "
        print(flag, r["id"], r["name"], r["area"], "->", None if r["got"] is None else round(r["got"], 1), "r=", r["rpx"])
    print(ok, "/", len(rooms))
    vis = cv2.cvtColor(255 - walls, cv2.COLOR_GRAY2BGR)
    rng = np.random.default_rng(1)
    for r in rooms:
        col = [int(x) for x in rng.integers(60, 230, 3)]
        for ring, holes in r["polys"]:
            cv2.fillPoly(vis, [np.round(ring * PX).astype(np.int32)] + [np.round(h * PX).astype(np.int32) for h in holes], col)
    cv2.imwrite(f"vis{pi}.png", cv2.resize(vis[500:2600, 400:3300], None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA))
