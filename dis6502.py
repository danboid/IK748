import sys
from py65.devices.mpu6502 import MPU
from py65.disassembler import Disassembler
from bm import BM
def dis(ram,start,end):
    mpu=MPU(); mpu.memory=list(ram); d=Disassembler(mpu); pc=start; out=[]
    while pc<end:
        n,t=d.instruction_at(pc); out.append('%04x  %s'%(pc,t)); pc+=n
    return out
if __name__=='__main__':
    m=BM(); m.cmd(0x81); ram=m.mem(0,0xffff,'cpu'); m.resume()
    open('ram_now.bin','wb').write(ram)  # full CPU-view RAM for frametable.py
    for a in sys.argv[1:]:
        s,e=[int(x,16) for x in a.split('-')]
        print('\n'.join(dis(ram,s,e))); print('----')
