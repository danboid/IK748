from bm import BM
import collections
m=BM(); m.cmd(0x81)
cp=m.cp_set(0x5200,0x61bf,2); m.resume()
pcs=collections.Counter()
for i in range(400):
    m.wait_event(0x62); r=m.regs(); pcs[r[3]]+=1; m.resume()
m.wait_event(0x62); m.cp_del(cp); m.resume()
for pc,n in pcs.most_common(15): print(hex(pc),n)
