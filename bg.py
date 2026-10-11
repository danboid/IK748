import pickle,sys,numpy as np,collections
def state_per_line(ev):
    st={}; cur=None
    f0=[e for e in ev if e[0]==0]; f1=[e for e in ev if e[0]==1]
    if f0: cur=(f0[-1][2],f0[-1][3])
    i=0
    for L in range(312):
        while i<len(f1) and f1[i][1]<=L: cur=(f1[i][2],f1[i][3]); i+=1
        st[L]=cur
    return st
def row_fill(ram,col,scr,row):
    cnt=collections.Counter((ram[scr+row*40+c],col[row*40+c]) for c in range(40) if not 50<=ram[scr+row*40+c]<64)
    return cnt.most_common(1)[0][0]
def analyse(path, blank_anim=True):
    d=path if isinstance(path,dict) else pickle.load(open(path,'rb')); ram=d['ram']; col=bytes(c&15 for c in d['col'])
    st=state_per_line(d['ev'])
    img=np.zeros((200,320),np.uint8); kind=np.zeros((200,40),'U2'); fill={}
    for L in range(51,251):
        io,dd=st[L]  # io indexes from $d011
        d011,d016,d018=io[0],io[5],io[7]; bg=io[0x10]&15; m1=io[0x11]&15; m2=io[0x12]&15
        bank=(3-(dd&3))*0x4000; scr=bank+(d018>>4)*0x400
        y=L-51; row,line=y//8,y%8
        bmm=bool(d011&0x20); mcm=bool(d016&0x10)
        for c in range(40):
            cr=col[row*40+c]; sv=ram[scr+row*40+c]
            if bmm:
                b=ram[bank+(d018&8)*0x400+row*320+c*8+line]
                cols=[bg,sv>>4,sv&15,cr]; k='BM'
                for p in range(4):
                    v=cols[(b>>(6-2*p))&3]; img[y,c*8+p*2:c*8+p*2+2]=v
            else:
                ch=ram[scr+row*40+c]
                if blank_anim and 50<=ch<64:
                    # runtime-drawn speech bubble / score popup: use the row's most common
                    # static character (with its colour) instead, so it isn't baked in
                    ch,cr=fill.get((scr,row)) or fill.setdefault((scr,row),row_fill(ram,col,scr,row))
                b=ram[bank+((d018>>1)&7)*0x800+ch*8+line]
                if mcm and cr&8:
                    cols=[bg,m1,m2,cr&7]; k='MC'
                    for p in range(4):
                        v=cols[(b>>(6-2*p))&3]; img[y,c*8+p*2:c*8+p*2+2]=v
                else:
                    k='HR'; fg=cr&7 if mcm else cr
                    for p in range(8): img[y,c*8+p]=fg if (b>>(7-p))&1 else bg
            kind[row,c]=k
    return img,kind,st
if __name__=='__main__':
    for path in sys.argv[1:]:
        img,kind,st=analyse(path)
        rows=collections.OrderedDict()
        for r in range(25): rows.setdefault(collections.Counter(kind[r]).most_common(1)[0][0],[]).append(r)
        print(path, {k:(v[0],v[-1]) for k,v in rows.items()})
