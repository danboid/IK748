from bm import BM
import collections
m=BM(); m.cmd(0x81)
cp=m.cp_set(0x4190,0x41ff,2); m.resume()
pcs=collections.Counter()
for i in range(150):
    m.wait_event(0x62); pcs[m.regs()[3]]+=1; m.resume()
m.wait_event(0x62); m.cp_del(cp)
ram=m.mem(0,0xffff,'cpu'); col=m.mem(0xd800,0xdbff,'io'); m.resume()
print([(hex(p),n) for p,n in pcs.most_common(8)])
for scr in (0x6000,0x6400):
    pos=[(k//40,k%40,ram[scr+k]) for k in range(1000) if 50<=ram[scr+k]<64]
    print(hex(scr),pos)
open('ram_chars.bin','wb').write(ram)
