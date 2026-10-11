import pickle,numpy as np,collections,math
S=pickle.load(open('run1.pkl','rb')); F=pickle.load(open('frames.pkl','rb'))
# ---- unique sprite tiles (canvas-grid aligned, flip-X merged), empty tiles skipped
canvases={}
for fr in F:
    c=fr['c']; key=c.tobytes()
    canvases.setdefault(min(key,np.fliplr(c).tobytes()),c)
tiles=set(); per=[]
for c in canvases.values():
    pc=np.zeros((112,40),np.uint8); pc[:105,:36]=c
    n=0
    for ty in range(14):
        for tx in range(5):
            t=pc[ty*8:ty*8+8,tx*8:tx*8+8]
            if t.any():
                n+=1; a=t.tobytes(); b=np.fliplr(t).tobytes(); tiles.add(min(a,b))
    per.append(n)
print('distinct whole-canvas frames:',len(canvases))
print('non-empty tiles per frame avg %.1f max %d'%(np.mean(per),max(per)))
print('unique 8x8 tiles across frames (flip merged):',len(tiles),'=',len(tiles)*32,'bytes 4bpp')
# ---- RAM tile demand: union of 8x8 cells touched by opaque pixels of both fighters
XOFF=16  # C64 160px centred in 192px Uzebox line
dem=[]
by=collections.defaultdict(dict)
for fr in F: by[fr['si']][fr['f']]=fr
for si,d in by.items():
    cells=set()
    for f,fr in d.items():
        ys,xs=np.nonzero(fr['c'])
        fx=(fr['x']-24)//2 + XOFF
        for y,x in zip(ys,xs):
            cells.add(((x+fx)//8,(147+y-51)//8))
    dem.append(len(cells))
dem=np.array(dem)
print('RAM tiles for both fighters: median %d, p95 %d, max %d'%(np.median(dem),np.percentile(dem,95),dem.max()))
