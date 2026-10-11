import pickle,numpy as np,collections,math
S=pickle.load(open('run1.pkl','rb'))
F=pickle.load(open('frames.pkl','rb'))
good=F
tops=[];bots=[];ws=[];hs=[];canon={};colsets=collections.Counter()
for fr in good:
    c=fr['c']; ys,xs=np.nonzero(c)
    if len(ys)==0: continue
    y0,y1,x0,x1=ys.min(),ys.max(),xs.min(),xs.max()
    tops.append(147+y0); bots.append(147+y1); ws.append(x1-x0+1); hs.append(y1-y0+1)
    crop=c[y0:y1+1,x0:x1+1]
    a=crop.tobytes()+bytes(crop.shape); bfl=np.fliplr(crop).tobytes()+bytes(crop.shape)
    canon.setdefault(min(a,bfl),crop)
    colsets[fr['cols']]+=1
print('screen raster top min %d, bottom max %d'%(min(tops),max(bots)))
print('width fat px: min %d max %d | height lines: min %d max %d'%(min(ws),max(ws),min(hs),max(hs)))
print('top raster percentiles 0/5/50:',np.percentile(tops,[0,5,50]))
print('distinct fighter images (flip-merged):',len(canon))
print('colour sets (d025,d026,own):',colsets.most_common())
# tile cost per distinct frame on Uzebox (8x8 tiles, 4bpp=32 bytes)
tiles=[math.ceil(v.shape[1]/8)*math.ceil(v.shape[0]/8) for v in canon.values()]
worst=[(math.ceil(v.shape[1]/8)+1)*(math.ceil(v.shape[0]/8)+1) for v in canon.values()]
print('tiles per frame aligned: avg %.1f max %d | worst-case RAM tiles per fighter %d'%(np.mean(tiles),max(tiles),max(worst)))
print('SPI bytes for observed frames: %d'%(sum(tiles)*32))
# how many frames reach above raster 163 (into the bitmap scenery)
print('fighter images reaching above raster 163: %d of %d'%(sum(t<163 for t in tops),len(tops)))
pickle.dump(canon,open('canon.pkl','wb'))
