import pymupdf, numpy as np, cv2
import os
PDF = os.environ.get("CQ3_PDF", os.path.join(os.path.dirname(os.path.abspath(__file__)), "CQ3_FP.pdf"))
PX = 0.035278/0.02          # pixels per point (2 cm per pixel)
def bez(p0,p1,p2,p3,n=12):
    t=np.linspace(0,1,n)[:,None]; a=np.array
    return ((1-t)**3*a(p0)+3*(1-t)**2*t*a(p1)+3*(1-t)*t**2*a(p2)+t**3*a(p3))
def paths(g):
    out=[]
    for it in g['items']:
        k=it[0]
        if k=='l': out.append(np.array([[it[1].x,it[1].y],[it[2].x,it[2].y]]))
        elif k=='c': out.append(bez(*[(q.x,q.y) for q in it[1:5]]))
        elif k=='re': r=it[1]; out.append(np.array([[r.x0,r.y0],[r.x1,r.y0],[r.x1,r.y1],[r.x0,r.y1],[r.x0,r.y0]]))
        elif k=='qu': q=it[1]; out.append(np.array([[q.ul.x,q.ul.y],[q.ur.x,q.ur.y],[q.lr.x,q.lr.y],[q.ll.x,q.ll.y],[q.ul.x,q.ul.y]]))
    return out
def render(page, pred, minpx=1):
    W,H=int(page.rect.width*PX)+1,int(page.rect.height*PX)+1
    img=np.zeros((H,W),np.uint8)
    for g in page.get_drawings():
        if not pred(g): continue
        w=max(minpx,int(round((g.get('width') or 0)*PX)))
        for pts in paths(g):
            cv2.polylines(img,[np.round(pts*PX).astype(np.int32)],False,255,w)
    return img
