import sys,pickle,hashlib
from bm import BM
m=BM()
m.cmd(0x81)
c1=m.cp_set(0xd011,0xd02e,2); c2=m.cp_set(0xdd00,0xdd00,2)
m.resume()
ev=[]; last=None; frames=0
while frames<2:
    m.wait_event(0x62); m.step(1)
    io=m.mem(0xd011,0xd02e,'io'); dd=m.mem(0xdd00,0xdd00,'io')[0]
    ras=io[1]+256*(io[0]>>7)
    if last is not None and ras<last-50: frames+=1
    last=ras
    ev.append((frames,ras,bytes(io),dd))
    m.resume()
m.wait_event(0x62); m.cp_del(c1); m.cp_del(c2)
ram=m.mem(0,0xffff,'ram'); col=m.mem(0xd800,0xdbff,'io')
dw,dh,ow,oh,iw,ih,buf=m.display()
m.resume()
pickle.dump(dict(ev=ev,ram=ram,col=col,disp=(dw,dh,ow,oh,buf)),open(sys.argv[1],'wb'))
# print changes for frame 1
prev=None
for f,r,io,dd in ev:
    if f!=1: continue
    st=(io[0],io[5],io[7],io[0x10],io[0x11],io[0x12],io[0x13],dd&3)
    if st!=prev:
        print('ras %3d d011 %02x d016 %02x d018 %02x d020 %x d021 %x d022 %x d023 %x bank %d'%((r,)+st))
    prev=st
