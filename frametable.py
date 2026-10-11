import numpy as np,sys
ram=open(sys.argv[1] if len(sys.argv)>1 else 'ram_now.bin','rb').read()
w=lambda a: ram[a]|ram[a+1]<<8
frames=[];bad=[]
for f in range(64):
    h=w(0x7800+2*f); d=w(0x7880+2*f)
    hdr=ram[h:h+12]; rows=[(b>>4,b&15) for b in hdr]
    ok= 0x0800<=h<0xd000 and 0x0800<=d<0xd000 and all(s+n<=9 for s,n in rows) and sum(n for _,n in rows)>0
    if not ok: bad.append(f); continue
    img=np.zeros((96,36),np.uint8); p=d
    for r,(s,n) in enumerate(rows):
        for c in range(s,s+n):
            for l in range(8):
                v=ram[p+l]
                for q in range(4): img[r*8+l,c*4+q]=(v>>(6-2*q))&3
            p+=8
    frames.append(dict(f=f,h=h,d=d,cells=sum(n for _,n in rows),end=p,img=img,flag=ram[0x7bc0+f]))
print('valid frames',len(frames),'invalid/unused',bad)
cells=sum(x['cells'] for x in frames)
print('total cells %d = %d bytes of 2bpp source'%(cells,cells*8))
print('data range $%04x-$%04x'%(min(x['d'] for x in frames),max(x['end'] for x in frames)))
uniq=set();per=[];dups=0;seen=set()
for x in frames:
    im=x['img']; k=im.tobytes()
    if k in seen: dups+=1; continue
    seen.add(k); n=0
    for ty in range(12):
        for tx in range(5):
            t=np.zeros((8,8),np.uint8); src=im[ty*8:ty*8+8,tx*8:tx*8+8]; t[:,:src.shape[1]]=src
            if t.any(): n+=1; uniq.add(min(t.tobytes(),np.fliplr(t).tobytes()))
    per.append(n)
print('identical frames',dups)
print('Uzebox tiles per frame: avg %.1f max %d, total placed %d'%(np.mean(per),max(per),sum(per)))
print('unique 8x8 tiles (mirror-merged): %d = %d bytes at 4bpp'%(len(uniq),len(uniq)*32))
print('without tile dedupe: %d bytes'%(sum(per)*32))
