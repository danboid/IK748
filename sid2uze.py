#!/usr/bin/env python3
"""
sid2uze - convert C64 SID music to a MIDI file and a Uzebox patch file.

Input is either a PSID file (.sid) or a raw 64 KB C64 RAM dump with the player's
init and play addresses (for game music that isn't packaged as a .sid).

The player is run frame by frame on a 6502 emulator (py65) and every SID register
write is recorded in order. From that register log sid2uze derives notes, instruments
and effects for the Uzebox sound engine.

Usage:
  sid2uze.py convert tune.sid [--song N] [--seconds S] --out NAME
  sid2uze.py convert --ram dump.bin --init AE00,AE09 --play AE0C --out NAME
      writes NAME.mid, NAME_patches.inc, NAME_report.txt, and NAME_stream.bin +
      NAME_stream.h (the song in the kernel's MUSIC_ENGINE=STREAM format)
  sid2uze.py analyse ...              (activity and size report only)
  sid2uze.py dump    ... --out regs.txt  (frame-by-frame register log)

Then:  midiconv -f 72 [-1 -2 -3] NAME.mid NAME_song.inc
       (sid2uze writes 50 ticks per quarter at 60 BPM, i.e. one tick per C64 frame;
       -f 72 turns that into Uzebox 60 Hz frames, so the tune plays in real time.)

This tool is GPL-3.0-or-later.
"""
import argparse, struct, sys

PAL_HZ = 50
SENTINEL = 0xFFF0

# ------------------------------------------------------------------ inputs
class Tune:
    def __init__(self):
        self.mem = bytearray(65536)
        self.init_calls = []   # [(address, A register)]
        self.play = None       # address called once per frame
        self.name = ''

def load_psid(path, song=None):
    d = open(path, 'rb').read()
    magic = d[0:4]
    if magic not in (b'PSID', b'RSID'):
        raise SystemExit('%s: not a PSID/RSID file' % path)
    if magic == b'RSID':
        raise SystemExit('%s: RSID tunes need a full C64 environment; not supported yet' % path)
    ver, off, load, init, play, songs, start = struct.unpack('>HHHHHHH', d[4:18])
    name = d[0x16:0x36].split(b'\0')[0].decode('latin1')
    data = d[off:]
    if load == 0:
        load = data[0] | data[1] << 8; data = data[2:]
    t = Tune()
    t.mem[load:load + len(data)] = data
    n = (song or start) - 1
    t.init_calls = [(init, n)]
    if play == 0:
        raise SystemExit('%s: the tune installs its own interrupt (play address 0); not supported yet' % path)
    t.play = play
    t.name = name
    return t

def load_ram(path, init, play):
    d = open(path, 'rb').read()
    if len(d) != 65536:
        raise SystemExit('%s: expected a 65536-byte RAM dump' % path)
    t = Tune()
    t.mem[:] = d
    t.init_calls = [(int(a, 16), 0) for a in init.split(',')]
    t.play = int(play, 16)
    t.name = path
    return t

# ------------------------------------------------------------------ 6502 runner
class Runner:
    """Runs routines on py65 and records SID writes ($D400-$D41F) in order."""
    def __init__(self, tune):
        from py65.devices.mpu6502 import MPU
        from py65.memory import ObservableMemory
        self.mem = ObservableMemory(subject=tune.mem)
        self.writes = []
        def on_write(address, value):
            self.writes.append((address - 0xD400, value))
        self.mem.subscribe_to_write(range(0xD400, 0xD420), on_write)
        self.mpu = MPU(memory=self.mem)
        self.tune = tune

    def call(self, address, a=0, max_steps=2_000_000):
        mpu = self.mpu
        ret = SENTINEL - 1
        mpu.sp = 0xFF
        self.mem[0x01FF] = ret >> 8
        self.mem[0x01FE] = ret & 0xFF
        mpu.sp = 0xFD
        mpu.a = a; mpu.pc = address
        for _ in range(max_steps):
            if mpu.pc == SENTINEL: return
            mpu.step()
        raise RuntimeError('routine at $%04X did not return' % address)

def capture(tune, frames):
    """Returns a list, per frame, of the ordered SID writes [(reg, value)]."""
    r = Runner(tune)
    for a, acc in tune.init_calls: r.call(a, acc)
    log = []
    for _ in range(frames):
        r.writes = []
        r.call(tune.play)
        log.append(list(r.writes))
    return log

# ------------------------------------------------------------------ analysis
def states(log):
    """Register file after each frame (32 bytes)."""
    regs = bytearray(32); out = []
    for w in log:
        for reg, v in w: regs[reg] = v
        out.append(bytes(regs))
    return out

def find_loop(st, min_len=PAL_HZ * 4):
    """Smallest period p such that the frame states repeat from some start s
    for at least two periods. Returns (start, period) or None."""
    n = len(st)
    for p in range(min_len, n // 2):
        # look for a start where st[s:s+p] == st[s+p:s+2p]
        for s in range(0, n - 2 * p, PAL_HZ):
            if st[s:s + p] == st[s + p:s + 2 * p]:
                # move the start back as far as it still holds
                while s > 0 and st[s - 1] == st[s - 1 + p]: s -= 1
                return s, p
    return None

WAVES = {0x10: 'tri', 0x20: 'saw', 0x40: 'pulse', 0x80: 'noise'}

def analyse(log, start, length):
    """Per voice: notes (gate on events), frames with a frequency change,
    waveform use, pulse width changes, ring/sync use."""
    rep = []
    regs = bytearray(32)
    for frame in log[:start]:
        for reg, v in frame: regs[reg] = v
    for v in range(3):
        rep.append(dict(notes=0, freq_frames=0, pw_frames=0, waves={}, ring=0, sync=0, adsr=set()))
    filt = set(); vol = set()
    for frame in log[start:start + length]:
        changed = set()
        for reg, val in frame:
            voice, r = divmod(reg, 7) if reg < 21 else (None, None)
            if voice is not None:
                if r == 4:
                    if (val & 1) and not (regs[reg] & 1): rep[voice]['notes'] += 1
                    for bit, name in WAVES.items():
                        if val & bit: rep[voice]['waves'][name] = rep[voice]['waves'].get(name, 0) + 1
                    if val & 4: rep[voice]['ring'] += 1
                    if val & 2: rep[voice]['sync'] += 1
                if r in (0, 1) and regs[reg] != val: changed.add((voice, 'f'))
                if r in (2, 3) and regs[reg] != val: changed.add((voice, 'p'))
                if r in (5, 6): rep[voice]['adsr'].add((reg, val))
            elif reg in (21, 22, 23): filt.add((reg, val))
            elif reg == 24: vol.add(val)
            regs[reg] = val
        for voice, kind in changed:
            rep[voice]['freq_frames' if kind == 'f' else 'pw_frames'] += 1
    return rep, filt, vol

def size_estimate(rep, length):
    """Rough Uzebox stream sizes, in bytes: notes only, and notes plus one pitch
    event per frequency change (the naive worst case)."""
    notes = sum(r['notes'] for r in rep)
    pitch = sum(r['freq_frames'] for r in rep)
    # a note on + note off with delta times is ~5 bytes; a pitch event ~3 bytes
    return notes * 5, notes * 5 + pitch * 3

# ------------------------------------------------------------------ main
# ------------------------------------------------------------------ notes
import math

PAL_CLOCK = 985248.0
def sid_note(freq):
    """SID frequency register -> fractional MIDI note (PAL)."""
    if freq <= 0: return None
    hz = freq * PAL_CLOCK / 16777216.0
    return 69 + 12 * math.log2(hz / 440.0)

def voice_frames(log):
    """Per voice, per frame: (gate, ctrl, freq, pw, ad, sr, retrig) after that frame."""
    regs = bytearray(32); out = [[], [], []]
    for frame in log:
        retrig = [False, False, False]; gate_seen_off = [False, False, False]
        for reg, val in frame:
            if reg < 21:
                v, r = divmod(reg, 7)
                if r == 4:
                    if not (val & 1): gate_seen_off[v] = True
                    elif gate_seen_off[v] or not (regs[reg] & 1): retrig[v] = True
            regs[reg] = val
        for v in range(3):
            b = v * 7
            out[v].append(((regs[b + 4] & 1), regs[b + 4], regs[b] | regs[b + 1] << 8,
                           (regs[b + 2] | regs[b + 3] << 8) & 0xFFF, regs[b + 5], regs[b + 6], retrig[v]))
    return out

def wave_kind(ctrl):
    if ctrl & 0x80: return 'noise'
    if ctrl & 0x40: return 'pulse'
    if ctrl & 0x20: return 'saw'
    if ctrl & 0x10: return 'ring' if ctrl & 0x04 else 'tri'
    return None

def split_notes(frames):
    """-> list of notes: dict(start, end, frames=[(ctrl,freq,pw)], ad, sr)."""
    notes, cur = [], None
    for i, (gate, ctrl, freq, pw, ad, sr, retrig) in enumerate(frames):
        if retrig:
            if cur: cur['end'] = i; notes.append(cur)
            cur = dict(start=i, end=None, frames=[], ad=ad, sr=sr)
        if cur is not None:
            if gate: cur['frames'].append((ctrl, freq, pw))
            elif cur['end'] is None: cur['end'] = i
    if cur:
        if cur['end'] is None: cur['end'] = len(frames)
        notes.append(cur)
    return [n for n in notes if n['frames']]

def pitch_pattern(offsets):
    """Classify a note's per-frame semitone offsets (relative to its base note).
    -> ('static',) | ('arp', prefix, cycle) | ('steps', list)"""
    o = offsets[:64]
    if all(x == o[0] for x in o): return ('static',)
    for p in range(1, 9):
        for s in range(0, 5):
            body = o[s:]
            if len(body) >= 2 * p and all(body[k] == body[k % p] for k in range(len(body))) and len(set(body[:p])) > 1:
                return ('arp', tuple(o[:s]), tuple(body[:p]))
    d = [b - a for a, b in zip(o, o[1:])]
    if d and (all(x >= 0 for x in d) or all(x <= 0 for x in d)):
        st = tuple(max(-24, min(24, x)) for x in o[:6])
        return ('steps', st)
    return ('static',)

ATTACK_MS = [2, 8, 16, 24, 38, 56, 68, 80, 100, 250, 500, 800, 1000, 3000, 5000, 8000]
DECAY_MS = [3 * x for x in ATTACK_MS]

def envelope(ad, sr):
    """SID ADSR -> (start volume, attack speed, attack frames, decay speed, decay frames).
    Uzebox envelopes add a signed step per 60 Hz frame to a 0..255 volume."""
    a, d, s = ad >> 4, ad & 15, sr >> 4
    sus = s * 17
    af = max(1, round(ATTACK_MS[a] * 60 / 1000))
    df = max(1, round(DECAY_MS[d] * 60 / 1000))
    if af <= 1: start, aspd, af = 255, 0, 0
    else:       start, aspd = 0, min(127, max(1, round(255 / af)))
    dspd = 0 if sus >= 240 else -min(128, max(1, round((255 - sus) / df)))
    return start, aspd, af, dspd, (df if dspd else 0), sus

DUTY_WAVES = ((0.25, 3), (0.5, 4), (0.75, 5))
WAVE_NUM = {'saw': 1, 'tri': 2, 'ring': 6}

def describe_notes(vf):
    """Every note of every voice with its base note, kind, wave and pattern."""
    out = []
    for v in range(3):
        for n in split_notes(vf[v]):
            kinds = {}
            for ctrl, freq, pw in n['frames']:
                k = wave_kind(ctrl)
                if k: kinds[k] = kinds.get(k, 0) + 1
            if not kinds: continue
            kind = max(kinds, key=kinds.get)
            freqs = [f for c, f, p in n['frames'] if f]
            if not freqs: continue
            base = sid_note(freqs[0])
            basei = int(round(base))
            offs = [int(round(sid_note(f) - basei)) if f else 0 for c, f, p in n['frames']]
            pws = sorted(p for c, f, p in n['frames'])
            duty = pws[len(pws) // 2] / 4096.0 if pws else 0.5
            out.append(dict(voice=v, start=n['start'], end=n['end'], note=basei, kind=kind,
                            mixed=len(kinds) > 1, duty=duty, ad=n['ad'], sr=n['sr'],
                            pattern=pitch_pattern(offs), noisefreq=freqs[0] >> 8,
                            vib=any(abs(sid_note(f) - basei - o) > 0.25 for (c, f, p), o in zip(n['frames'], offs) if f)))
    return out

def instrument_key(n):
    if n['kind'] == 'noise':
        return ('noise', min(15, n['noisefreq'] >> 4), n['ad'], n['sr'], n['pattern'][0] == 'steps')
    wave = WAVE_NUM.get(n['kind'])
    if wave is None: wave = min(DUTY_WAVES, key=lambda dw: abs(dw[0] - min(n['duty'], 1 - n['duty'] + 0.5) if False else abs(dw[0] - n['duty'])))[1]
    return ('wave', wave, n['ad'], n['sr'], n['pattern'])

def patch_commands(key):
    """Uzebox patch command list [(delta, cmd, param)] for an instrument key."""
    cmds = []
    if key[0] == 'noise':
        _, div, ad, sr, falling = key
        cmds.append((0, 'PC_NOISE_PARAMS', 1 + 2 * (15 - div)))
    else:
        _, wave, ad, sr, pattern = key
        cmds.append((0, 'PC_WAVE', wave))
    start, aspd, af, dspd, df, sus = envelope(ad, sr)
    cmds.append((0, 'PC_ENV_VOL', start))
    if aspd:
        cmds.append((0, 'PC_ENV_SPEED', aspd))
        cmds.append((af, 'PC_ENV_SPEED', dspd))
    else:
        cmds.append((0, 'PC_ENV_SPEED', dspd))
    if key[0] == 'wave':
        pattern = key[4]
        def steps(seq, prev):
            out = []
            for x in seq:
                d = x - prev
                if d > 0: out.append((1, 'PC_NOTE_UP', d))
                elif d < 0: out.append((1, 'PC_NOTE_DOWN', -d))
                else: out.append((1, 'PC_NOTE_HOLD', 0))
                prev = x
            return out, prev
        if pattern[0] == 'arp':
            prefix, cycle = pattern[1], pattern[2]
            pre, last = steps(prefix, 0)
            cmds += pre
            # move to the first cycle value, then loop the cycle (returning to its start)
            body, last2 = steps(cycle[1:] + (cycle[0],), cycle[0])
            if last != cycle[0]:
                d = cycle[0] - last
                cmds.append((0, 'PC_NOTE_UP' if d > 0 else 'PC_NOTE_DOWN', abs(d)))
            cmds.append((0, 'PC_LOOP_START', 255))
            cmds += body
            cmds.append((0, 'PC_LOOP_END', len(body)))
        elif pattern[0] == 'steps':
            st, _ = steps(pattern[1][1:], pattern[1][0])
            cmds += [c for c in st if c[1] != 'PC_NOTE_HOLD']
    return cmds

# ------------------------------------------------------------------ Uzebox stream format
def encode_stream(events, loop_start, loop_end):
    """Uzebox MUSIC_ENGINE=STREAM song bytes from (time_in_60Hz_frames, kind, ...) events:
    ('on', ch, note, vol8) / ('pc', ch, patch). Returns (bytes, loop_start_offset).
    Format (kernel uzeboxSoundEngine.c): note on 0bCCCVVVVV + VNNNNNNN (6-bit volume,
    volume 0 = note off); program change 0b10100CCC + patch; markers 0xC1 loop start,
    0xC0 loop end; tick end 0b110XXX11 (1-7 frames) or 0b11011111 + frames."""
    out = bytearray(); loop_off = 0
    events = sorted(events, key=lambda e: (e[0], 0 if e[1] == 'pc' else 1))
    times = sorted(set([e[0] for e in events] + [loop_start, loop_end]))
    bytime = {}
    for e in events: bytime.setdefault(e[0], []).append(e)
    def tick(dt):
        while dt > 0:
            if dt <= 7: out.append(0b11000011 | ((dt - 1) << 2)); dt = 0
            else:
                n = min(dt, 255); out.extend((0b11011111, n)); dt -= n
    t = 0
    for tm in times:
        if tm > loop_end: break
        tick(tm - t); t = tm
        if tm == loop_start: loop_off = len(out); out.append(0xC1)
        for e in bytime.get(tm, []):
            if e[1] == 'pc':
                out += bytes([0xA0 | e[2], e[3]])
            else:
                ch, note, vol = e[2], e[3], e[4]
                v6 = min(63, vol >> 2)
                out += bytes([(ch << 5) | (v6 & 0x1F), ((v6 & 0x20) << 2) | (note & 0x7F)])
        if tm == loop_end:
            out.append(0xC0)
    return bytes(out), loop_off

# ------------------------------------------------------------------ MIDI
def vlq(n):
    b = [n & 0x7F]; n >>= 7
    while n: b.insert(0, 0x80 | (n & 0x7F)); n >>= 7
    return bytes(b)

def write_midi(path, tracks, loop):
    """tracks: list of [(tick, bytes)] ; loop = (start_tick, end_tick) or None."""
    def chunk(events):
        events = sorted(events, key=lambda e: (e[0], e[1][0] & 0xF0 == 0x80 and 0 or 1))
        out = bytearray(); t = 0
        for tick, data in events:
            out += vlq(tick - t) + data; t = tick
        out += b'\x00\xFF\x2F\x00'
        return b'MTrk' + struct.pack('>I', len(out)) + bytes(out)
    conductor = [(0, b'\xFF\x51\x03' + (1000000).to_bytes(3, 'big'))]   # 60 BPM
    if loop:
        conductor += [(loop[0], b'\xFF\x06\x01S'), (loop[1], b'\xFF\x06\x01E')]
    data = b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks) + 1, 50)
    data += chunk(conductor) + b''.join(chunk(t) for t in tracks)
    open(path, 'wb').write(data)

def find_note_loop(notes, total, min_len=PAL_HZ * 4):
    """Loop on the note sequence: smallest period p with a start s (searched near the
    beginning) where every note event in [s, s+p) recurs exactly p frames later."""
    sig = [None] * total
    for n in notes:
        if n['start'] < total:
            sig[n['start']] = (sig[n['start']] or ()) + ((n['voice'], n['note'], n['kind']),)
    for p in range(min_len, total // 2):
        for s in range(0, min(400, total - 2 * p)):
            k = 0
            while s + p + k < total and sig[s + k] == sig[s + p + k]: k += 1
            if s + p + k >= total: return s, p
    return None

def find_note_loop_tolerant(notes, total, tol=3, min_len=PAL_HZ * 4):
    """Loop on the order of notes, allowing a few frames of drift (players with a
    tempo counter that skips frames don't repeat on the exact same frame).
    Uses the busiest voice to find the period, then checks all voices."""
    seqs = {v: [(n['start'], n['note'], n['kind']) for n in notes if n['voice'] == v] for v in range(3)}
    vbusy = max(seqs, key=lambda v: len(seqs[v]))
    seq = seqs[vbusy]
    sym = [(x[1], x[2]) for x in seq]
    n = len(sym)
    for k in range(8, n // 2):
        for s in range(0, min(64, n - 2 * k)):
            if sym[s:s + k] != sym[s + k:s + 2 * k]: continue
            t0, P = seq[s][0], seq[s + k][0] - seq[s][0]
            if P < min_len or t0 + 2 * P > total: continue
            # the whole rest of the capture must repeat with period P (an intro that
            # happens to play a phrase twice must not count as the loop)
            ok = True
            horizon = total - P - 2 * tol
            for v in range(3):
                a = [x for x in seqs[v] if t0 <= x[0] < horizon]
                b = [x for x in seqs[v] if t0 + P - tol <= x[0] < horizon + P - tol]
                if len(a) != len(b) or any(p[1:] != q[1:] or abs((q[0] - p[0]) - P) > tol for p, q in zip(a, b)):
                    ok = False; break
            if ok: return t0, P
    return None

def find_tail_loop(notes, total, tol=3, min_overlap=PAL_HZ * 60):
    """For tunes too long to capture twice: the smallest period P such that, on every
    voice, the notes from P to the end of the capture repeat the notes from some start
    s (within the first minute), with at least min_overlap frames of overlap."""
    seqs = {v: [(n['start'], n['note'], n['kind']) for n in notes if n['voice'] == v] for v in range(3)}
    vbusy = max(seqs, key=lambda v: len(seqs[v]))
    seq = seqs[vbusy]; sym = [(x[1], x[2]) for x in seq]; N = len(sym)
    for i0 in range(0, min(N, 200)):
        if seq[i0][0] > PAL_HZ * 60: break
        for j in range(i0 + 8, N):
            P = seq[j][0] - seq[i0][0]
            if total - seq[j][0] < min_overlap: break
            if sym[j] != sym[i0]: continue
            ok = True
            for v in range(3):
                a = [x for x in seqs[v] if seq[i0][0] <= x[0] < total - P - 2 * tol]
                b = [x for x in seqs[v] if seq[i0][0] + P - tol <= x[0] < total - 2 * tol]
                if len(a) != len(b) or any(p[1:] != q[1:] or abs((q[0] - p[0]) - P) > tol for p, q in zip(a, b)):
                    ok = False; break
            if ok: return seq[i0][0], P
    return None

def coarse_adsr(ad, sr):
    """Merge envelopes the ear can't tell apart: attack/decay in steps of 3, sustain in 4 levels."""
    a, d, su = ad >> 4, ad & 15, sr >> 4
    a = 0 if a <= 1 else min(15, (a // 3) * 3 + 1)
    d = min(15, (d // 3) * 3 + 1)
    su = min(15, (su // 4) * 4 + 2) if su < 15 else 15
    return (a << 4) | d, (su << 4) | (sr & 15)

GAP_FRAMES = 4

def convert(tune, frames, out, cache=None, forced_loop=None):
    import os, pickle
    if cache and os.path.exists(cache):
        log = pickle.load(open(cache, 'rb'))[:frames]
    else:
        log = capture(tune, frames)
        if cache: pickle.dump(log, open(cache, 'wb'))
    vf = voice_frames(log)
    notes = describe_notes(vf)
    for n in notes: n['ad'], n['sr'] = coarse_adsr(n['ad'], n['sr'])
    if forced_loop: loop = forced_loop
    else: loop = find_note_loop(notes, frames) or find_note_loop_tolerant(notes, frames) or find_tail_loop(notes, frames)
    end = (loop[0] + loop[1]) if loop else frames
    notes = [n for n in notes if n['start'] < end]
    # instruments: drums (noise) first so drum note numbers = patch numbers
    keys = []
    for n in notes:
        k = instrument_key(n)
        if k not in keys: keys.append(k)
    drums = [k for k in keys if k[0] == 'noise']; melodic = [k for k in keys if k[0] == 'wave']
    order = drums + melodic
    if len(order) > 128: raise SystemExit('too many instruments (%d) for MIDI program numbers' % len(order))
    idx = {k: i for i, k in enumerate(order)}
    # MIDI tracks: voices on channels 0-2, drums on channel 9 (-> Uzebox noise channel)
    tracks = [[], [], [], []]
    cur_prog = [None, None, None]
    sev = []                                   # stream events, C64 frame times
    sprog = [None] * 4
    # a note-off is only needed where the voice falls silent before its next note;
    # back-to-back notes retrigger the channel anyway (saves a lot of song space)
    nxt = {}
    by_voice = {}
    for n in notes:
        if instrument_key(n)[0] == 'wave': by_voice.setdefault(n['voice'], []).append(n)
    for v, lst in by_voice.items():
        lst.sort(key=lambda n: n['start'])
        for a, b in zip(lst, lst[1:]): nxt[id(a)] = b['start']
    for n in notes:
        k = instrument_key(n); p = idx[k]
        st, en = n['start'], min(n['end'], end)
        if k[0] == 'noise':
            tracks[3] += [(st, bytes([0x99, p, 100])), (max(st + 1, en), bytes([0x89, p, 0]))]
            if sprog[3] != p: sev.append((st, 'pc', 3, p)); sprog[3] = p
            sev.append((st, 'on', 3, 60, 200))
        else:
            ch = n['voice']; note = max(0, min(127, n['note']))
            if cur_prog[ch] != p:
                tracks[ch].append((st, bytes([0xC0 | ch, p]))); cur_prog[ch] = p
            tracks[ch].append((st, bytes([0x90 | ch, note, 100])))
            if sprog[ch] != p: sev.append((st, 'pc', ch, p)); sprog[ch] = p
            sev.append((st, 'on', ch, note, 200))
            gap = nxt.get(id(n), end) - en
            if gap >= GAP_FRAMES:
                tracks[ch].append((max(st + 1, en), bytes([0x80 | ch, note, 0])))
                sev.append((max(st + 1, en), 'on', ch, note, 0))
    write_midi(out + '.mid', tracks, (loop[0], end) if loop else None)
    # Uzebox stream song: C64 frames -> 60 Hz frames (rounded from the exact time, no drift)
    conv = lambda f: int(round(f * 60 / PAL_HZ))
    # program changes in force at the loop start must be re-sent there, so the loop
    # restarts with the right instruments (the stream engine has no other state to restore)
    ls = loop[0] if loop else 0
    state = {}
    for e in sorted(sev, key=lambda e: e[0]):
        if e[0] >= ls: break
        if e[1] == 'pc': state[e[2]] = e[3]
    sev2 = [(conv(e[0]),) + e[1:] for e in sev if e[0] < end]
    sev2 += [(conv(ls), 'pc', ch, pp) for ch, pp in state.items()]
    stream, loop_off = encode_stream(sev2, conv(ls), conv(end))
    open(out + '_stream.bin', 'wb').write(stream)
    nm = out_name(out)
    with open(out + '_stream.h', 'w') as f:
        f.write('/* %s_stream.h - generated by sid2uze: Uzebox MUSIC_ENGINE=STREAM song */\n#pragma once\n' % nm)
        f.write('#define %s_STREAM_LEN %dUL      /* bytes in %s_stream.bin */\n' % (nm.upper(), len(stream), nm))
        f.write('#define %s_STREAM_LOOP %dUL     /* offset to restart from after the end */\n' % (nm.upper(), loop_off))
        f.write('#define %s_PATCH_COUNT %d\n' % (nm.upper(), len(order)))
        f.write('#define %s_PATCH_ENTRIES ' % nm.upper() + ', '.join('{%d,NULL,%s_p%02d,0,0}' % (1 if k[0] == 'noise' else 0, nm, i) for i, k in enumerate(order)) + '\n')
    # patch file
    lines = ['/* %s_patches.inc - generated by sid2uze from %s */' % (out, tune.name),
             '/* %d drum patches (noise; MIDI note n = patch n), %d melodic patches */' % (len(drums), len(melodic))]
    for i, k in enumerate(order):
        cmds = patch_commands(k)
        body = ', '.join('%d,%s,%d' % c for c in cmds) + ', 0,PATCH_END'
        lines.append('/* patch %d: %s */' % (i, describe_key(k)))
        lines.append('const char %s_p%02d[] PROGMEM = { %s };' % (out_name(out), i, body))
    lines.append('#ifndef %s_NO_TABLE   /* define this to merge the patches into your own table */' % out_name(out).upper())
    lines.append('const struct PatchStruct %s_patches[] PROGMEM = {' % out_name(out))
    for i, k in enumerate(order):
        lines.append('\t{%d,NULL,%s_p%02d,0,0},' % (1 if k[0] == 'noise' else 0, out_name(out), i))
    lines.append('};')
    lines.append('#endif')
    open(out + '_patches.inc', 'w').write('\n'.join(lines) + '\n')
    # report
    rep = []
    rep.append('tune: %s' % tune.name)
    rep.append('loop: %s' % ('starts %.2f s, length %.2f s' % (loop[0] / PAL_HZ, loop[1] / PAL_HZ) if loop else 'none found in %.0f s (whole capture used)' % (frames / PAL_HZ)))
    rep.append('notes: %d (voice 1 %d, voice 2 %d, voice 3 %d; %d drum hits)' % (len(notes),
               *[sum(1 for n in notes if n['voice'] == v and n['kind'] != 'noise') for v in range(3)],
               sum(1 for n in notes if n['kind'] == 'noise')))
    rep.append('instruments: %d (%d drums, %d melodic)' % (len(order), len(drums), len(melodic)))
    pats = {}
    for n in notes: pats[n['pattern'][0]] = pats.get(n['pattern'][0], 0) + 1
    rep.append('pitch patterns: %s' % pats)
    rep.append('approximations:')
    rep.append('  notes mixing waveforms (e.g. a noise attack on a tonal note): %d - played as their main waveform' % sum(1 for n in notes if n['mixed']))
    rep.append('  notes with vibrato or sub-semitone bends: %d - played without it' % sum(1 for n in notes if n['vib']))
    rep.append('  ring-modulated notes: %d - played on a distorted sine (wave 6)' % sum(1 for n in notes if n['kind'] == 'ring'))
    rep.append('  pulse-width sweeps: played at the nearest of 25/50/75%% duty')
    est = sum(1 for _ in notes) * 5 + sum(1 for t in tracks[:3] for e in t if e[1][0] & 0xF0 == 0xC0) * 2
    rep.append('estimated Uzebox song size: ~%d bytes (patches excluded)' % est)
    open(out + '_report.txt', 'w').write('\n'.join(rep) + '\n')
    print('\n'.join(rep))
    print('stream song: %d bytes, loop restarts at offset %d' % (len(stream), loop_off))
    print('wrote %s.mid, %s_patches.inc, %s_report.txt, %s_stream.bin, %s_stream.h' % (out, out, out, out, out))

def out_name(out):
    import os, re
    return re.sub(r'\W', '_', os.path.basename(out))

def describe_key(k):
    if k[0] == 'noise':
        return 'noise, pitch %d, AD %02X SR %02X%s' % (k[1], k[2], k[3], ', falling' if k[4] else '')
    names = {1: 'saw', 2: 'triangle', 3: 'square 25%', 4: 'square 50%', 5: 'square 75%', 6: 'ring (distorted sine)'}
    pat = k[4]
    ptxt = {'static': 'plain', 'arp': 'arpeggio %s' % (pat[2],) if pat[0] == 'arp' else '', 'steps': 'pitch steps'}[pat[0]]
    return '%s, AD %02X SR %02X, %s' % (names[k[1]], k[2], k[3], ptxt)

def get_tune(a):
    if a.ram:
        if not (a.init and a.play): raise SystemExit('--ram needs --init and --play')
        return load_ram(a.ram, a.init, a.play)
    if not a.sid: raise SystemExit('give a .sid file or --ram')
    return load_psid(a.sid, a.song)

def main():
    ap = argparse.ArgumentParser(description='Convert C64 SID music to MIDI + Uzebox patches')
    ap.add_argument('command', choices=['analyse', 'dump', 'convert'])
    ap.add_argument('sid', nargs='?')
    ap.add_argument('--song', type=int)
    ap.add_argument('--ram'); ap.add_argument('--init'); ap.add_argument('--play')
    ap.add_argument('--seconds', type=float, default=300)
    ap.add_argument('--out')
    ap.add_argument('--gap', type=int, default=4, help='write a note-off only before a rest of at least this many frames (default 4)')
    ap.add_argument('--loop', help='force the loop: START,LENGTH in seconds')
    ap.add_argument('--cache', help='save/reuse the captured register log (pickle), to skip the slow emulation on reruns')
    a = ap.parse_args()
    tune = get_tune(a)
    frames = int(a.seconds * PAL_HZ)
    if a.command == 'convert':
        global GAP_FRAMES
        GAP_FRAMES = a.gap
        fl = None
        if a.loop:
            st, ln = [float(x) for x in a.loop.split(',')]
            fl = (int(st * PAL_HZ), int(ln * PAL_HZ))
        convert(tune, frames, a.out or 'tune', a.cache, fl); return
    log = capture(tune, frames)
    if a.command == 'dump':
        with open(a.out or 'regs.txt', 'w') as f:
            for i, w in enumerate(log):
                f.write('%6d %s\n' % (i, ' '.join('%02X=%02X' % rv for rv in w)))
        print('wrote', a.out or 'regs.txt'); return
    st = states(log)
    loop = find_loop(st)
    if loop: start, length = loop; print('tune: %s\nloop: starts at %.2f s, length %.2f s (%d frames)'
                                       % (tune.name, start / PAL_HZ, length / PAL_HZ, length))
    else:    start, length = 0, frames; print('tune: %s\nno loop found in %.0f s; analysing all of it' % (tune.name, a.seconds))
    rep, filt, vol = analyse(log, start, length)
    for v, r in enumerate(rep):
        print('voice %d: %4d notes, frequency changes on %5d frames, pulse width on %5d, waves %s, ring %d, sync %d, ADSR settings %d'
              % (v + 1, r['notes'], r['freq_frames'], r['pw_frames'], r['waves'], r['ring'], r['sync'], len(r['adsr'])))
    print('filter registers written:', 'none' if not filt else sorted(filt)[:8])
    print('volume register values:', sorted(vol))
    lo, hi = size_estimate(rep, length)
    print('estimated Uzebox stream size: notes only ~%d bytes, with every pitch change ~%d bytes (one loop)' % (lo, hi))

if __name__ == '__main__':
    main()
