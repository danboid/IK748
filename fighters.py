import pickle,collections,numpy as np
S=pickle.load(open('run1.pkl','rb'))
def spr(ram,ptr):
    d=ram[0x4000+ptr*64:0x4000+ptr*64+63]
    a=np.zeros((21,12),np.uint8)
    for r in range(21):
        for c in range(3):
            v=d[r*3+c]
            for p in range(4): a[r,c*4+p]=(v>>(6-2*p))&3
    return a
frames=[]
for si,s in enumerate(S):
    b={x['y']:x for x in s['bands']}
    if sorted(b)!=[147,168,189,210,231]: continue
    io=b[168]['io']
    for f in (0,1):
        canvas=np.zeros((105,36),np.uint8)
        for bi,y in enumerate([147,168,189,210,231]):
            for k in range(3):
                sk=f*3+k
                # pointers are written just after each band's Y move, so the value seen
                # at the 168 step is the top band's; bands follow at +3 blocks each
                p=b[168]['ptr'][sk]+3*bi
                canvas[bi*21:bi*21+21,k*12:k*12+12]=spr(s['ram'],p)
        x0=b[168]['x'][f*3]
        cols=(io[0x25]&15,io[0x26]&15,io[0x27+f*3]&15)
        frames.append(dict(si=si,f=f,c=canvas,x=x0,cols=cols))
pickle.dump(frames,open('frames.pkl','wb'))
print('fighter images',len(frames))
