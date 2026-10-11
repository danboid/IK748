"""
bonus_extract.py - bonus-round data for the Uzebox port, from your own copy of
International Karate (C64). Used by convert748.py.

 * Projectiles: the game's own drawing routines are run on a 6502 emulator (py65)
   against your RAM dump, for every type, direction, animation frame and height,
   and the result is read back from the sprite buffer.
 * Brick stack: the breaking-round screen (capture_bonus.py) is compared with the
   same stage's normal screen; pixels that differ are the stack, the rest is
   transparent.
 * Fighter masks: 1 bit per pixel per frame, for knife collisions.
 * Speech bubbles: original artwork and font (not taken from the game).
"""
import hashlib, pickle
import numpy as np

# ------------------------------------------------------------------ 6502 runner
SENTINEL = 0xFFF0

def run_routine(ram, pc, pokes, max_steps=200000):
    from py65.devices.mpu6502 import MPU
    mpu = MPU()
    mem = bytearray(ram)
    for a, v in pokes.items(): mem[a] = v
    mpu.memory = mem
    ret = SENTINEL - 1
    mpu.sp = 0xFF
    mem[0x0100 + mpu.sp] = ret >> 8; mpu.sp -= 1
    mem[0x0100 + mpu.sp] = ret & 0xFF; mpu.sp -= 1
    mpu.pc = pc
    for _ in range(max_steps):
        if mpu.pc == SENTINEL: return mem
        mpu.step()
    raise RuntimeError('routine at $%04X did not return' % pc)

# fighter-B sprite buffer: band k, sprite j -> block 72 + 3k + j  ($5200-$55FF)
def decode_hires_canvas(mem):
    img = np.zeros((105, 72), np.uint8)
    for k in range(5):
        for j in range(3):
            blk = 0x4000 + (72 + 3 * k + j) * 64
            for r in range(21):
                for c in range(3):
                    v = mem[blk + r * 3 + c]
                    for b in range(8):
                        img[k * 21 + r, j * 24 + c * 8 + b] = (v >> (7 - b)) & 1
    return img

PROJ_DRAW = (0x31DD, 0x329D, 0x3319)   # draw routine per projectile type

def projectiles(ram):
    """Returns shapes (list of fat-pixel masks) and a table
    [(type, dir, anim, height)] -> (shape, x0_fat, y0, colour_or_None)."""
    shapes, index, table = [], {}, {}
    hp = lambda t, h: ram[0x3131 + t * 16 + 2 * h] | ram[0x3132 + t * 16 + 2 * h] << 8
    for t in range(3):
        for d in range(2):
            for a in range(4):
                for h in range(8):
                    pokes = {0xAD28: d, 0xAD21: (a - 1) & 3, 0x44: 0}
                    p = hp(t, h); pokes[0xAD24] = p & 0xFF; pokes[0xAD25] = p >> 8
                    base = bytearray(ram)
                    for z in range(0x5200, 0x5600): base[z] = 0
                    mem = run_routine(bytes(base), PROJ_DRAW[t], pokes)
                    img = decode_hires_canvas(mem)
                    ys, xs = np.nonzero(img)
                    if len(ys) == 0: continue
                    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
                    fx0 = x0 // 2
                    w = x1 // 2 - fx0 + 1
                    fat = np.zeros((y1 - y0 + 1, w), np.uint8)
                    for y, x in zip(ys, xs): fat[y - y0, x // 2 - fx0] = 1
                    key = fat.tobytes() + bytes(fat.shape)
                    if key not in index: index[key] = len(shapes); shapes.append(fat)
                    colour = None if t == 0 else mem[0xAD2E]
                    table[(t, d, a, h)] = (index[key], int(fx0), int(y0), colour)
    return shapes, table

def tables(ram):
    return dict(
        type_by_level=list(ram[0x3119:0x3125]),
        speed_by_level=list(ram[0x3125:0x3131]),
        dir_pattern=list(ram[0x30FD:0x3119]),
        knife_colours=list(ram[0x321D:0x3221]),
        knife_count=list(ram[0x0FBF:0x0FC2]),
        twoplayer_order=list(ram[0x14BB:0x14C2]),
    )

# ------------------------------------------------------------------ fighter masks
def fighter_masks(ram, decode_frame):
    """54 frames x 96 rows x 5 bytes, bit 7 of byte 0 = leftmost pixel of the 36-px box."""
    out = bytearray()
    for f in range(54):
        img = decode_frame(ram, f)
        m = np.zeros((96, 40), np.uint8)
        if img is not None: m[:, :36] = (img > 0)
        for r in range(96):
            for byte in range(5):
                v = 0
                for b in range(8): v |= int(m[r, byte * 8 + b]) << (7 - b)
                out.append(v)
    return bytes(out)

# ------------------------------------------------------------------ brick stack
def _load_capture(bonus_pkl):
    d = pickle.load(open(bonus_pkl, 'rb'))
    return (d['ready'], d.get('broken')) if 'ready' in d else (d, None)

def brick_sprite(bonus_pkl, xoff):
    """The brick stack is drawn into sprite slots 0-2 (in front of the fighter).
    Decode those slots from the capture: the pointer the displayed screen holds
    at the end of the frame is the bottom band's; the top band is 12 blocks
    lower and each band adds 3 (same layout as the fighters).
    Returns (image in C64 colours, 0 = transparent, screen x, zone y) or None."""
    b = pickle.load(open(bonus_pkl, 'rb')) if isinstance(bonus_pkl, str) else bonus_pkl
    if 'ready' in b: b = b['ready']
    ram, io = b['ram'], b['io']
    scr = 0x4000 + (io[0x18] >> 4) * 0x400
    canvas = np.zeros((105, 2 * 160), np.uint8)          # hires pixels across the C64 screen
    for j in range(3):
        if not (io[0x15] >> j) & 1: continue
        base = ram[scr + 0x3F8 + j] - 12
        x = io[2 * j] + 256 * ((io[0x10] >> j) & 1)       # sprite X (hires, 24 = screen left)
        xexp = (io[0x1D] >> j) & 1
        colour = io[0x27 + j] & 15
        mc = (io[0x1C] >> j) & 1
        for k in range(5):
            blk = 0x4000 + (base + 3 * k) * 64
            for r in range(21):
                for c in range(3):
                    v = ram[blk + r * 3 + c]
                    for q in range(8):
                        if mc: continue                     # (bricks are hires; skip multicolour)
                        if not (v >> (7 - q)) & 1: continue
                        hx = (c * 8 + q) * (2 if xexp else 1)
                        for e in range(2 if xexp else 1):
                            sx = x - 24 + hx + e
                            if 0 <= sx < 320: canvas[k * 21 + r, sx] = colour
    fat = np.maximum(canvas[:, 0::2], canvas[:, 1::2])    # 2 hires pixels -> 1 fat pixel
    ys, xs = np.nonzero(fat)
    if len(ys) == 0: return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    sx0 = ((xoff + x0) // 8) * 8; zy0 = (y0 // 8) * 8
    img = fat[zy0:y1 + 1, (sx0 - xoff):x1 + 1]
    return img, int(sx0), int(zy0)

def brick_stages(bonus_pkl, xoff):
    """Eleven images of the stack: 0..10 bricks cracked. The C64 draws the crack into
    the sprite (cleared pixels down the middle), one brick per break, from the top.
    Returns (list of images, screen x, zone y); without a cracked snapshot all eleven
    are the intact stack."""
    ready, broken = _load_capture(bonus_pkl)
    r = brick_sprite(ready, xoff)
    if r is None: return None
    img0, sx, zy = r
    if broken is None: return [img0] * 11, sx, zy
    rb = brick_sprite(broken, xoff)
    if rb is None or rb[1] != sx or rb[2] != zy: return [img0] * 11, sx, zy
    img1 = np.zeros_like(img0); h = min(img0.shape[0], rb[0].shape[0]); w = min(img0.shape[1], rb[0].shape[1])
    img1[:h, :w] = rb[0][:h, :w]
    # brick layers: runs of opaque rows in the intact stack, top to bottom
    rows = [y for y in range(img0.shape[0]) if img0[y].any()]
    layers, cur = [], []
    for y in rows:
        if cur and y != cur[-1] + 1: layers.append(cur); cur = []
        cur.append(y)
    if cur: layers.append(cur)
    out = []
    for n in range(11):
        im = img0.copy()
        for k in range(min(n, len(layers))):
            for y in layers[k]: im[y] = img1[y]
        out.append(im)
    return out, sx, zy

# ------------------------------------------------------------------ speech bubbles
# original 3x5 font (same as the game's HUD), rows top..bottom, bit 2 = left pixel
FONT = {
 ' ':[0,0,0,0,0],'!':[2,2,2,0,2],'0':[7,5,5,5,7],'1':[2,6,2,2,7],'2':[7,1,7,4,7],'3':[7,1,7,1,7],
 '4':[5,5,7,1,1],'5':[7,4,7,1,7],'6':[7,4,7,5,7],'7':[7,1,2,2,2],'8':[7,5,7,5,7],'9':[7,5,7,1,7],
 'A':[2,5,7,5,5],'B':[6,5,6,5,6],'C':[3,4,4,4,3],'D':[6,5,5,5,6],'E':[7,4,6,4,7],'F':[7,4,6,4,4],
 'G':[3,4,5,5,3],'H':[5,5,7,5,5],'I':[7,2,2,2,7],'J':[1,1,1,5,2],'K':[5,5,6,5,5],'L':[4,4,4,4,7],
 'M':[5,7,7,5,5],'N':[6,5,5,5,5],'O':[2,5,5,5,2],'P':[6,5,6,4,4],'Q':[2,5,5,6,3],'R':[6,5,6,5,5],
 'S':[3,4,2,1,6],'T':[7,2,2,2,2],'U':[5,5,5,5,7],'V':[5,5,5,5,2],'W':[5,5,7,7,5],'X':[5,5,2,5,5],
 'Y':[5,5,2,2,2],'Z':[7,1,2,4,7],
}

BUBBLES = [
    ('GET_READY', 'GET', 'READY'), ('GO', 'GO!', ''), ('TOO_SLOW', 'TOO', 'SLOW'),
    ('HALF_POINT', 'HALF', 'POINT'), ('FULL_POINT', 'FULL', 'POINT'),
    ('WHITE_WINS', 'WHITE', 'WINS'), ('RED_WINS', 'RED', 'WINS'), ('BEGIN', 'BEGIN', ''),
    ('WELL_DONE', 'WELL', 'DONE'), ('OUCH', 'OUCH!', ''),
] + [('BRICKS_%d' % n, '%d' % n, 'BRICK' if n == 1 else 'BRKS') for n in range(1, 11)]

def bubble_image(l1, l2, fill, ink):
    """24 x 24 px bubble (3 x 3 tiles): rounded box with a tail on the right
    (towards the referee); colour 0 = transparent."""
    W, H = 24, 24
    img = np.zeros((H, W), np.uint8)
    for y in range(1, 19):
        for x in range(0, 23):
            edge = (y in (1, 18)) or (x in (0, 22))
            corner = (x in (0, 22)) and (y in (1, 18))
            if corner: continue
            img[y, x] = ink if edge else fill
    for i, (y, x) in enumerate(((18, 16), (19, 17), (20, 18), (21, 19))):   # tail
        img[y, x - 1] = ink; img[y, x] = fill if i < 3 else ink; img[y, x + 1] = ink
    def text(s, y):
        x = 1 + (21 - 4 * len(s) + 1) // 2
        for ch in s:
            g = FONT.get(ch, FONT[' '])
            for r in range(5):
                for c in range(3):
                    if (g[r] >> (2 - c)) & 1: img[y + r, x + c] = ink
            x += 4
    if l2: text(l1, 3); text(l2, 10)
    else:  text(l1, 7)
    return img

# ------------------------------------------------------------------ tiles
def tiles_from(img, transparent_to=0, colour_map=None):
    """Split img (H x W, multiple of 8 not required) into 8x8 4bpp tiles; returns
    [(dx, dy, 32 bytes)] for non-empty tiles."""
    H = (img.shape[0] + 7) // 8 * 8; W = (img.shape[1] + 7) // 8 * 8
    pad = np.zeros((H, W), np.uint8)
    src = img.copy()
    if colour_map is not None: src = colour_map(src)
    pad[:img.shape[0], :img.shape[1]] = src
    out = []
    for ty in range(0, H, 8):
        for tx in range(0, W, 8):
            t = pad[ty:ty + 8, tx:tx + 8]
            if not t.any(): continue
            out.append((tx, ty, bytes(((t[:, 0::2] << 4) | t[:, 1::2]).flatten())))
    return out
