#!/usr/bin/env python3
"""
capture_bonus.py - capture the breaking-round screen from your own copy of
International Karate running in VICE (binary monitor on port 6502, as for
trace_stages.py).

Waits for the attract demo to finish a bout, switches the game into the breaking
round for player 1, and saves bonus4.pkl with two snapshots: the brick stack as it
stands, and after a perfect strike (triggered here) has cracked all ten bricks.
Usage:  python3 capture_bonus.py [bonus4.pkl]       (can take a few minutes)
"""
import sys, pickle
from bm import BM

out = sys.argv[1] if len(sys.argv) > 1 else 'bonus4.pkl'
m = BM(); m.cmd(0x81)
for n in range(1, 80):
    try: m.cp_del(n)
    except Exception: pass
cp = m.cp_set(0x1620, 0x1620, 4); m.resume()
print('waiting for the demo to finish a bout...', flush=True)
m.wait_event(0x62, timeout=600)
m.poke(0x68, [4]); m.poke(0x45, [1]); m.cp_del(cp)          # next phase: breaking round, player 1 human
cp = m.cp_set(0x13C0, 0x13C0, 4); m.resume()               # reaction timer about to start: stack is up
m.wait_event(0x62, timeout=120); m.cp_del(cp)
def snap():
    return dict(ram=m.mem(0, 0xFFFF, 'cpu'), col=m.mem(0xD800, 0xDBFF, 'io'),
                io=m.mem(0xD000, 0xD02E, 'io'), dd=m.mem(0xDD00, 0xDD00, 'io')[0])
import time
ready = snap()
m.poke(0xAD1C, [0xFF])          # recorded input now differs: an instant reaction, all ten break
m.resume()
for _ in range(40):              # wait until the game has counted all ten
    time.sleep(0.25); m.cmd(0x81)
    done = m.mem(0xAD18, 0xAD19, 'cpu')
    if done[1] and done[0] >= done[1]: break
    m.resume()
time.sleep(0.0)
broken = snap(); m.resume()
pickle.dump(dict(ready=ready, broken=broken), open(out, 'wb'))
print('saved', out)
