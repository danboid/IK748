import time,hashlib,pickle,subprocess,os
from bm import BM
anim=set(range(50,64))
def key(r):
    return hashlib.md5(b''.join(r[0x4000+c*8:0x4008+c*8] for c in range(256) if c not in anim)).hexdigest()[:8]
done={}
t0=time.time()
while len(done)<4 and time.time()-t0<600:
    m=BM(); m.cmd(0x81); r=m.mem(0x4000,0x47ff,'ram'); m.resume(); m.s.close()
    k=key(bytes(0x4000)+r) if False else hashlib.md5(b''.join(r[c*8:c*8+8] for c in range(256) if c not in anim)).hexdigest()[:8]
    if k not in done:
        time.sleep(3)   # let the scene settle
        r=subprocess.run(['python3','trace.py','tr_%s.pkl'%k],capture_output=True,text=True,timeout=120)
        if r.returncode!=0 or not os.path.exists('tr_%s.pkl'%k):
            print('capture of',k,'failed:',r.stdout[-1500:],r.stderr[-1500:],flush=True)
            time.sleep(10); continue
        done[k]=round(time.time()-t0); print(k,done[k],flush=True)
    time.sleep(10)
print(done)
