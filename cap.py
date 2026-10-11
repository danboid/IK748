import time,random,pickle,sys
from bm import BM
m=BM(); samples=[]
N=int(sys.argv[1]); out=sys.argv[2]
t0=time.time()
for i in range(N):
    m.cmd(0x81)  # ping -> paused
    cp=m.cp_set(0xd000,0xd010,2); m.resume()
    bands=[]; seen=set()
    while len(bands)<5:
        m.wait_event(0x62); m.step(1)
        io=m.mem(0xd000,0xd02e,'io')
        ys=[io[2*k+1] for k in range(6)]
        if len(set(ys))==1 and io[0x12]>100 or (len(set(ys))==1 and ys[0]==147):
            if ys[0] not in seen:
                seen.add(ys[0])
                scr=0x4000+(io[0x18]>>4)*0x400
                p=m.mem(scr+0x3f8,scr+0x3ff,'ram')
                xs=[io[2*k]+256*((io[16]>>k)&1) for k in range(8)]
                bands.append(dict(y=ys[0],x=xs,ptr=list(p),io=bytes(io)))
        m.resume()
    m.wait_event(0x62); m.cp_del(cp)
    ram=m.mem(0x0000,0xffff,'ram'); col=m.mem(0xd800,0xdbff,'io')
    io=m.mem(0xd000,0xd02e,'io'); dd=m.mem(0xdd00,0xdd00,'io')[0]
    samples.append(dict(t=time.time()-t0,bands=bands,ram=ram,col=col,io=io,dd=dd))
    m.resume(); time.sleep(random.uniform(0.2,1.2))
    if i%20==0: print(i,round(time.time()-t0),flush=True)
pickle.dump(samples,open(out,'wb'))
