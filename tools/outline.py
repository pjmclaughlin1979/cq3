import numpy as np, cv2, json, sys
from scipy import ndimage
from extract import *
import os
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
os.makedirs(WORK, exist_ok=True)
def outline(pi, rpx=15):
    page = pymupdf.open(PDF)[pi]
    labs, lines = labels(page)
    s = wall_rasters(page, lines)[3]                 # every solid black line
    b = cv2.dilate(s, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * rpx + 1, 2 * rpx + 1)))
    lab, _ = ndimage.label(b == 0)
    outside = lab == lab[5, 5]
    inside = ~outside
    lab2, n = ndimage.label(inside)
    sizes = ndimage.sum(inside, lab2, range(1, n + 1))
    m = (lab2 == (np.argmax(sizes) + 1))
    m = cv2.erode(m.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * rpx + 1, 2 * rpx + 1)))
    m = ndimage.binary_fill_holes(m > 0).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    ring = cv2.approxPolyDP(c, 2, True)[:, 0, :] / PX
    return ring.tolist(), float((m > 0).sum() * 0.0004)
if __name__ == "__main__":
    pi = int(sys.argv[1])
    ring, a = outline(pi)
    print(pi, "outline area", round(a, 1), "vertices", len(ring))
    json.dump(ring, open(os.path.join(WORK, f"outline_{pi}.json"), "w"))
