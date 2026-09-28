import sys, json
from extract import *
import os
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
os.makedirs(WORK, exist_ok=True)
pi = int(sys.argv[1])
page, labs, lines, walls, rooms = extract(pi)
cols, rows = grid(lines)
title = next((t for t, r in lines if re.fullmatch(r"LV \d\d - GA", t)), None)
out = {"page": pi, "title": title, "cols": cols, "rows": rows, "rooms": []}
for r in rooms:
    out["rooms"].append({k: r[k] for k in ("id", "name", "area", "got", "err", "seed")} | {"method": str(r["rpx"]), "polys": [[ring.tolist(), [h.tolist() for h in holes]] for ring, holes in r["polys"]]})
json.dump(out, open(os.path.join(WORK, f"rooms_{pi}.json"), "w"))
print(pi, title, sum(1 for r in rooms if r["err"] is not None and r["err"] < 0.12), "/", len(rooms))
for r in rooms:
    if not (r["err"] is not None and r["err"] < 0.12): print("  BAD", r["id"], r["name"], r["area"], "->", r["got"] and round(r["got"], 1), r["rpx"])
