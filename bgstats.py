import sys,numpy as np,collections,hashlib,pickle
from bg import analyse
anim=set(range(50,64))
def skey(ram):
    return hashlib.md5(b''.join(ram[0x4000+c*8:0x4008+c*8] for c in range(256) if c not in anim)).hexdigest()[:8]
def tiles(fat,r0,r1):
    # fat: 200x160 fat-pixel image; Uzebox tiles 8x8 over char rows r0..r1
    s=set(); cols=set(); maxc=0; ncell=0
    for ty in range(r0,r1+1):
        for tx in range(20):
            t=fat[ty*8:ty*8+8,tx*8:tx*8+8]; s.add(t.tobytes()); u=len(set(t.flatten())); maxc=max(maxc,u)
            cols|=set(t.flatten().tolist())
    return len(s),sorted(cols),maxc
rows=[]
for p in sys.argv[1:]:
    d=pickle.load(open(p,'rb')); k=skey(d['ram'])
    img,kind,st=analyse(p)
    fat=img[:,0::2]
    lost=0; hr=0
    for r in range(14,24):
        for c in range(40):
            if kind[r,c]=='HR':
                hr+=1; blk=img[r*8:r*8+8,c*8:c*8+8]
                if (blk[:,0::2]!=blk[:,1::2]).any(): lost+=1
    bm=tiles(fat,2,13); low=tiles(fat,12,23); top=tiles(fat,2,11); gr=tiles(fat,14,23)
    allc=sorted(set(fat[8:192].flatten().tolist()))
    rows.append((k,bm,top,low,gr,hr,lost,allc))
    print('stage',k)
    print('  colours used rows 1-23:',len(allc),allc)
    print('  scenery bitmap rows 2-13 (96 lines): unique tiles %d, colours %d %s, max colours/tile %d'%(bm[0],len(bm[1]),bm[1],bm[2]))
    print('  rows 2-11 (no fighter ever): tiles %d colours %d'%(top[0],len(top[1])))
    print('  rows 12-23 (fighter zone): tiles %d colours %d max/tile %d'%(low[0],len(low[1]),low[2]))
    print('  ground rows 14-23 text: tiles %d; hires cells %d, with real hires detail %d'%(gr[0],hr,lost))
