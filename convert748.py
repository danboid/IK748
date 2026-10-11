#!/usr/bin/env python3
"""
convert748.py - turn RAM/raster-trace dumps of your own International Karate (C64)
into Uzebox Mode 748 data.

Usage:
  python3 convert748.py --out build \
      --stage egypt=tr_363717b0.pkl --stage london=tr_d2e9b449.pkl ...
  (fighter graphics are read from the first stage's RAM; use --fighter-ram to override)

Outputs (all in --out):
  ikspi.bin      everything that lives in SPI RAM, <= 128 KB (enforced)
  spi_layout.h       offsets into ikspi.bin
  fighter_frames.h   per-frame tile placement lists (PROGMEM)
  palettes.h         one 16-entry Uzebox palette per stage + fighter recolour tables
  zone_<stage>.h     ROM tiles (PROGMEM, 32 B each) for the mode 0 rows of each stage
  bitmap_left.h      left 24-pixel columns for mode 4 rows (deduplicated)

Screen layout produced (tile rows of 8 lines, C64 char row n -> Uzebox tile row n):
  rows 0..BM-1   mode 4: 4bpp SPI bitmap (HUD rows + scenery), 192 px wide
  rows BM..24    mode 0: ROM tiles, VRAM in SPI; sprites can be blitted here
The C64's 160 fat pixels are placed at x = XOFF..XOFF+159 of the 192-pixel line.
"""
import argparse, os, pickle, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bg import analyse

SPI_LIMIT = 128 * 1024

# C64 palette (Pepto-style RGB)
C64_RGB = [(0,0,0),(255,255,255),(136,57,50),(103,182,189),(139,63,150),(85,160,73),
           (64,49,141),(191,206,114),(139,84,41),(87,66,0),(184,105,98),(80,80,80),
           (120,120,120),(148,224,137),(120,105,196),(159,159,159)]

def uzebox_colour(rgb):
    """Nearest Uzebox colour byte (BBGGGRRR)."""
    best = None
    for v in range(256):
        r = (v & 7) * 255 / 7; g = ((v >> 3) & 7) * 255 / 7; b = (v >> 6) * 255 / 3
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if best is None or d < best[0]: best = (d, v)
    return best[1]

def tile_bytes(t):
    """8x8 array of 4-bit indices -> 32 bytes, high nybble = left pixel."""
    t = t.astype(np.uint8)
    return bytes(((t[:, 0::2] << 4) | t[:, 1::2]).flatten())

def tile_from_bytes(b):
    a = np.frombuffer(b, np.uint8).reshape(8, 4)
    out = np.zeros((8, 8), np.uint8); out[:, 0::2] = a >> 4; out[:, 1::2] = a & 15
    return out

# ---------------------------------------------------------------- fighters
def decode_frame(ram, f, patch=None):
    w = lambda a: ram[a] | ram[a + 1] << 8
    h, d = w(0x7800 + 2 * f), w(0x7880 + 2 * f)
    rows = [(b >> 4, b & 15) for b in ram[h:h + 12]]
    if not all(s + n <= 9 for s, n in rows): return None
    ncell = sum(n for _, n in rows)
    data = bytearray(ram[d:d + ncell * 8])
    for off, val in (patch or {}).items(): data[off] = val
    img = np.zeros((96, 36), np.uint8); p = 0
    for r, (s, n) in enumerate(rows):
        for c in range(s, s + n):
            for l in range(8):
                v = data[p + l]
                for q in range(4): img[r * 8 + l, c * 4 + q] = (v >> (6 - 2 * q)) & 3
            p += 8
    return img

def fighter_frames(ram):
    """All drawable frames incl. the runtime-patched variants. -> list of (name, img)."""
    out = []
    for f in range(64):
        img = decode_frame(ram, f)
        if img is None or not img.any(): continue
        if f in (0x2B, 0x2F):
            out.append(('F%02X_V0' % f, decode_frame(ram, f, {i: 0 for i in range(24)})))
            for v, off in enumerate((0x00, 0x18, 0x30, 0x48), 1):
                src = ram[0x3BC6 + off:0x3BC6 + off + 24]
                out.append(('F%02X_V%d' % (f, v), decode_frame(ram, f, dict(enumerate(src)))))
        elif f == 0x33:
            out.append(('F33_A', decode_frame(ram, f, {0x21: 0xD5, 0x26: 0xFF})))
            out.append(('F33_B', decode_frame(ram, f, {0x21: 0xD5, 0x26: 0xF7})))
            out.append(('F33_C', decode_frame(ram, f, {0x21: 0xFF, 0x26: 0xFF})))
        else:
            out.append(('F%02X' % f, img))
    return out

def build_fighters(ram, black_slot):
    # C64 sprite bit pairs: 1 = $D025 (black), 2 = own colour, 3 = $D026 (pink)
    # -> palette indices: own colour uses slot 1 (white); red fighter via recolour table
    cmap = np.array([0, black_slot, 1, 10], np.uint8)
    tiles, index, frames = [], {}, []
    for name, img in fighter_frames(ram):
        img4 = cmap[img]
        pad = np.zeros((96, 40), np.uint8); pad[:, :36] = img4
        place = []
        for ty in range(12):
            for tx in range(5):
                t = pad[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                if not t.any(): continue
                a, b = tile_bytes(t), tile_bytes(np.fliplr(t))
                if a in index: ti, fl = index[a], 0
                elif b in index: ti, fl = index[b], 1
                else: ti, fl = len(tiles), 0; index[a] = ti; tiles.append(a)
                place.append((tx * 8, ty * 8, ti, fl))
        frames.append((name, place, img4))
    return tiles, frames

# ---------------------------------------------------------------- stages
def build_stage(trace, xoff, bm_rows):
    img, kind, _ = analyse(trace)          # 200x320 C64 colour indices
    fat = img[:, 0::2]                      # 160 fat pixels
    scr = np.zeros((200, 192), np.uint8)    # border = colour 0
    scr[:, xoff:xoff + 160] = fat
    split = bm_rows * 8
    # mode 4: left 24 px per line -> RAM (12 B/line), right 168 px -> SPI (84 B/line)
    def pack(a): return bytes(((a[:, 0::2] << 4) | a[:, 1::2]).flatten())
    spi_bm = b''.join(pack(scr[y:y + 1, 24:192]) for y in range(split))
    left = [pack(scr[r * 8:r * 8 + 8, 0:24]) for r in range(bm_rows)]
    # mode 0: unique ROM tiles + 24-byte VRAM rows (+1 pad byte for X scrolling)
    tiles, index, vram = [], {}, b''
    for r in range(bm_rows, 25):
        row = bytearray()
        for c in range(24):
            tb = tile_bytes(scr[r * 8:r * 8 + 8, c * 8:c * 8 + 8])
            if tb not in index: index[tb] = len(tiles); tiles.append(tb)
            row.append(index[tb])
        vram += bytes(row) + b'\x00'
    if len(tiles) > 256: raise SystemExit('stage needs %d ROM tiles (>256)' % len(tiles))
    used = set(np.unique(scr).tolist())
    return dict(scr=scr, spi_bm=spi_bm, left=left, tiles=tiles, vram=vram, used=used)

def verify(st, bm_rows):
    """Rebuild the screen from the emitted data and compare with the source render."""
    split = bm_rows * 8; out = np.zeros((200, 192), np.uint8)
    for y in range(split):
        line = np.frombuffer(st['spi_bm'][y * 84:(y + 1) * 84], np.uint8)
        out[y, 24::2] = line >> 4; out[y, 25::2] = line & 15
        l = np.frombuffer(st['left'][y // 8][(y % 8) * 12:(y % 8) * 12 + 12], np.uint8)
        out[y, 0:24:2] = l >> 4; out[y, 1:24:2] = l & 15
    for i, r in enumerate(range(bm_rows, 25)):
        for c in range(24):
            out[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = tile_from_bytes(st['tiles'][st['vram'][i * 25 + c]])
    return bool((out == st['scr']).all())

def carr(name, data, per=16, aligned=False, section=None):
    attr = ''
    if section: attr = ' __attribute__((section("%s"), aligned(256)))' % section
    elif aligned: attr = ' __attribute__((aligned(256)))'
    s = 'const u8 %s[%d]%s = {\n' % (name, len(data), attr if section else ' PROGMEM' + attr)
    for i in range(0, len(data), per):
        s += '\t' + ', '.join('0x%02X' % b for b in data[i:i + per]) + ',\n'
    return s + '};\n'

def build_bonus(ram, bonus4, xoff, black):
    import bonus_extract as bx
    tiles = []                                  # 32-byte tiles, deduplicated
    tindex = {}
    def add(t):
        if t not in tindex: tindex[t] = len(tiles); tiles.append(t)
        return tindex[t]
    h = ['/* generated by convert748.py from your own International Karate data */',
         '#pragma once', '#define HAVE_BONUS 1',
         'typedef struct { s8 dx, dy; u8 tile; } BonusTile;     /* tile = index into SPI_BONUS_TILES */']
    def plist(name, img):
        # image in C64 colours with 0 = transparent; C64 black (0) can't be expressed, so
        # colour 0 pixels are only ever transparent here; tiles use the sprite black slot
        pl = []
        for dx, dy, t in bx.tiles_from(img):
            pl.append('{%d,%d,%d}' % (dx, dy, add(t)))
        h.append('static const BonusTile %s[] PROGMEM = {%s};' % (name, ','.join(pl) or '{0,0,0}'))
        h.append('#define %s_LEN %d' % (name.upper(), len(pl)))
    # bricks
    br = bx.brick_stages(bonus4, xoff)
    if br is None: raise SystemExit('no brick stack found in ' + bonus4)
    imgs, bx0, by0 = br
    for n, im in enumerate(imgs): plist('brick_tiles_%d' % n, im)
    h.append('static const BonusTile* const brick_tiles[11] PROGMEM = {%s};' % ','.join('brick_tiles_%d' % n for n in range(11)))
    h.append('static const u8 brick_len[11] PROGMEM = {%s};' % ','.join('BRICK_TILES_%d_LEN' % n for n in range(11)))
    h.append('#define BRICK_X %d\n#define BRICK_Y %d' % (bx0, by0))
    # projectiles: shapes x colour variants
    shapes, ptab = bx.projectiles(ram)
    tb = bx.tables(ram)
    variants = {}                               # (shape, colour) -> index
    vnames = []
    def variant(si, colour):
        k = (si, colour)
        if k not in variants:
            variants[k] = len(vnames); n = 'proj_%d' % len(vnames); vnames.append((n, si))
            plist(n, (shapes[si] * colour).astype(np.uint8))
        return variants[k]
    kcol = tb['knife_colours']
    # table [type][dir][anim][height] -> variant per knife colour (type 0) or fixed colour
    entries = []
    for t in range(3):
        for d in range(2):
            for an in range(4):
                for hh in range(8):
                    si, x0, y0, colour = ptab[(t, d, an, hh)]
                    if t == 0: vs = [variant(si, c) for c in kcol]
                    else:      vs = [variant(si, colour)] * 4
                    entries.append('{{%s},%d,%d,%d}' % (','.join(map(str, vs)), x0, y0, si))
    h.append('typedef struct { u8 var[4]; u8 x0, y0, shape; } ProjEntry;   /* var[] per knife colour */')
    h.append('static const ProjEntry proj_table[3*2*4*8] PROGMEM = {%s};' % ','.join(entries))
    h.append('static const BonusTile* const proj_var[] PROGMEM = {%s};' % ','.join(n for n, _ in vnames))
    h.append('static const u8 proj_var_len[] PROGMEM = {%s};' % ','.join('%s_LEN' % n.upper() for n, _ in vnames))
    # shape masks for collisions: rows of 4 bytes (32 px), bit 7 = left
    mrows, moff = [], []
    for sh in shapes:
        moff.append((len(mrows), sh.shape[0], sh.shape[1]))
        for r in range(sh.shape[0]):
            v = 0
            for c in range(sh.shape[1]): v |= int(sh[r, c]) << (31 - c)
            mrows.append(v)
    h.append('static const u32 proj_mask[] PROGMEM = {%s};' % ','.join('0x%08XUL' % v for v in mrows))
    h.append('static const u8 proj_shape[][3] PROGMEM = {%s};   /* first mask row, height, width */'
             % ','.join('{%d,%d,%d}' % m for m in moff))
    for k in ('type_by_level', 'speed_by_level', 'dir_pattern', 'knife_count', 'twoplayer_order'):
        h.append('static const u8 bonus_%s[%d] PROGMEM = {%s};' % (k, len(tb[k]), ','.join(map(str, tb[k]))))
    # speech bubbles (original art), fill white (1), ink = sprite black slot
    names = []
    for n, l1, l2 in bx.BUBBLES:
        plist('bub_' + n.lower(), bx.bubble_image(l1, l2, 1, black)); names.append(n)
    h.append('enum { ' + ', '.join('BUB_' + n for n in names) + ', BUB_NONE };')
    h.append('static const BonusTile* const bub_tiles[] PROGMEM = {%s};' % ','.join('bub_' + n.lower() for n in names))
    h.append('static const u8 bub_len[] PROGMEM = {%s};' % ','.join('BUB_%s_LEN' % n.upper() for n in names))
    h.append('#define BUBBLE_X %d\n#define BUBBLE_Y %d' % (xoff + 112, 16))
    masks = bx.fighter_masks(ram, decode_frame)
    h.append('#define FIGHTER_MASK_BYTES 480U   /* per C64 frame: 96 rows x 5 bytes, at SPI_FIGHTER_MASKS */')
    return dict(tiles=b''.join(tiles), masks=masks, header='\n'.join(h) + '\n')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', action='append', required=True, help='name=trace.pkl')
    ap.add_argument('--fighter-ram', help='raw 64 KB RAM dump (default: first stage trace)')
    ap.add_argument('--out', default='build')
    ap.add_argument('--xoff', type=int, default=24, help='x of C64 image in 192 px line (multiple of 8)')
    ap.add_argument('--section', default='.tiles',
                    help='linker section for 256-byte aligned data (recolour table first, then ROM tiles); '
                         'set M74_RECTB_OFF to its start address')
    ap.add_argument('--bonus4', help='breaking-round capture from capture_bonus.py (enables the bonus rounds)')
    ap.add_argument('--bitmap-rows', type=int, default=12, help='tile rows 0..N-1 shown in mode 4')
    a = ap.parse_args()
    if a.xoff % 8 or not 0 <= a.xoff <= 32: raise SystemExit('--xoff must be 0..32 and a multiple of 8')
    os.makedirs(a.out, exist_ok=True)
    stages = [(n, p) for n, p in (s.split('=', 1) for s in a.stage)]
    ram = open(a.fighter_ram, 'rb').read() if a.fighter_ram else pickle.load(open(stages[0][1], 'rb'))['ram']

    built = {n: build_stage(p, a.xoff, a.bitmap_rows) for n, p in stages}
    # palette slot for sprite black: a C64 index no stage uses (sprite index 0 is transparent)
    allused = set().union(*(s['used'] for s in built.values())) | {0, 1, 2, 10}
    free = [i for i in range(16) if i not in allused]
    if not free: raise SystemExit('no free palette slot for sprite black')
    black = free[0]
    ftiles, frames = build_fighters(ram, black)

    # ---- SPI image
    spi = bytearray(); layout = []
    def put(label, data):
        layout.append((label, len(spi), len(data))); spi.extend(data)
    put('SPI_FIGHTER_TILES', b''.join(ftiles))
    for n, st in built.items():
        put('SPI_%s_BITMAP' % n.upper(), st['spi_bm'])
        put('SPI_%s_VRAM' % n.upper(), st['vram'])
    bonus = None
    if a.bonus4:
        bonus = build_bonus(ram, a.bonus4, a.xoff, black)
        put('SPI_BONUS_TILES', bonus['tiles'])
        put('SPI_FIGHTER_MASKS', bonus['masks'])
    if len(spi) > SPI_LIMIT:
        raise SystemExit('SPI image %d bytes exceeds 128 KB' % len(spi))
    open(os.path.join(a.out, 'ikspi.bin'), 'wb').write(spi)
    with open(os.path.join(a.out, 'spi_layout.h'), 'w') as f:
        f.write('/* generated by convert748.py; offsets into ikspi.bin (load at SPI address 0) */\n#pragma once\n')
        for label, off, ln in layout:
            f.write('#define %-28s 0x%05XUL /* %6d bytes */\n' % (label, off, ln))
        f.write('#define SPI_USED %dUL /* of %d */\n' % (len(spi), SPI_LIMIT))

    # ---- fighter placement lists
    with open(os.path.join(a.out, 'fighter_frames.h'), 'w') as f:
        f.write('/* generated by convert748.py\n'
                ' * Each placement: dx, dy (pixels from the 36x96 frame origin), tile, flags.\n'
                ' * SPI address = SPI_FIGHTER_TILES + tile*32 (set M74_SPR_SPIRAM_A16 if >= 0x10000).\n'
                ' * flags bit0 = M74_SPR_FLIPX. Facing left: blit at x + 28 - dx with FLIPX toggled.\n'
                ' * The frame origin is the top of the C64 sprite area (C64 raster 147). */\n'
                '#pragma once\n#define FIGHTER_TILE_COUNT %d\n#define FIGHTER_FRAME_COUNT %d\n'
                'typedef struct { u8 dx, dy; u16 tile; u8 flags; } FighterTile;\n' % (len(ftiles), len(frames)))
        for name, place, _ in frames:
            f.write('const FighterTile %s[] PROGMEM = {' % name.lower())
            f.write(', '.join('{%d,%d,%d,%d}' % p for p in place) + '};\n')
        f.write('const FighterTile* const fighter_frame[] PROGMEM = {' + ', '.join(n.lower() for n, _, _ in frames) + '};\n')
        f.write('const u8 fighter_frame_len[] PROGMEM = {' + ', '.join(str(len(p)) for _, p, _ in frames) + '};\n')
        f.write('enum { ' + ', '.join('FR_%s' % n for n, _, _ in frames) + ' };\n')
        # C64 frame number -> entry above (runtime-patched frames use their first variant)
        names = [n for n, _, _ in frames]; cmap = []
        for c in range(64):
            for cand in ('F%02X' % c, 'F%02X_V0' % c, 'F%02X_A' % c):
                if cand in names: cmap.append(names.index(cand)); break
            else: cmap.append(0xFF)
        f.write('/* C64 frame number (as used by the move tables) -> fighter_frame[] index, 0xFF = empty */\n')
        f.write('const u8 c64_frame_map[64] PROGMEM = {' + ', '.join(str(v) for v in cmap) + '};\n')

    # ---- palettes and recolour tables
    with open(os.path.join(a.out, 'palettes.h'), 'w') as f:
        f.write('/* generated by convert748.py: index = C64 colour, Uzebox BBGGGRRR */\n#pragma once\n')
        f.write('#define SPRITE_BLACK_SLOT %d\n' % black)
        base = [uzebox_colour(c) for c in C64_RGB]; base[black] = base[0]
        for n in built:
            f.write(carr('pal_%s' % n, base))
        rec = list(range(16)) * 16; rec[16 + 1] = 2   # table 0: identity, table 16: white -> red
        f.write('/* recolour tables, must sit at M74_RECTB_OFF (start of %s): col 0 = white fighter,\n'
                ' * col 16 = red fighter. Include this header before the zone headers. */\n' % a.section)
        f.write('#define RECOLOR_WHITE 0\n#define RECOLOR_RED 16\n')
        f.write(carr('fighter_recolor', rec, section=a.section))

    # ---- per stage ROM tiles + mode 4 left columns
    left_rows, left_idx = [], {}
    for n, st in built.items():
        with open(os.path.join(a.out, 'zone_%s.h' % n), 'w') as f:
            f.write('/* generated by convert748.py: %d ROM tiles for rows %d..24 of %s */\n#pragma once\n'
                    % (len(st['tiles']), a.bitmap_rows, n))
            f.write(carr('zone_%s_tiles' % n, b''.join(st['tiles']), section=a.section))
        st['left_ref'] = []
        for l in st['left']:
            if l not in left_idx: left_idx[l] = len(left_rows); left_rows.append(l)
            st['left_ref'].append(left_idx[l])
    with open(os.path.join(a.out, 'bitmap_left.h'), 'w') as f:
        f.write('/* generated by convert748.py: mode 4 left-column rows (96 B each, copy into the\n'
                ' * VRAM row after the mode byte). Rows with equal content share one entry. */\n#pragma once\n')
        f.write(carr('bitmap_left', b''.join(left_rows)))
        for n, st in built.items():
            f.write('const u8 bitmap_left_%s[] PROGMEM = {%s};\n' % (n, ', '.join(map(str, st['left_ref']))))

    # ---- bonus rounds
    with open(os.path.join(a.out, 'bonus.h'), 'w') as f:
        f.write(bonus['header'] if bonus else '/* generated by convert748.py: no --bonus4 given, bonus rounds disabled */\n#pragma once\n#define HAVE_BONUS 0\n')

    # ---- stage index for programs
    shared = len(left_rows) == 1
    with open(os.path.join(a.out, 'stages.h'), 'w') as f:
        f.write('/* generated by convert748.py; include once, in one C file (it defines the data) */\n#pragma once\n')
        f.write('#include "palettes.h"   /* recolour table first: it must land at M74_RECTB_OFF */\n')
        for n in built: f.write('#include "zone_%s.h"\n' % n)
        f.write('#include "bitmap_left.h"\n')
        f.write('#define STAGE_COUNT %d\n#define BITMAP_ROWS %d\n#define XOFF %d\n#define BITMAP_LEFT_SHARED %d\n'
                % (len(built), a.bitmap_rows, a.xoff, 1 if shared else 0))
        names = list(built)
        f.write('static const u8* const stage_pal[] PROGMEM = {%s};\n' % ', '.join('pal_' + n for n in names))
        f.write('static const u8* const stage_zone[] PROGMEM = {%s};\n' % ', '.join('zone_%s_tiles' % n for n in names))
        f.write('static const u8 stage_zone_count[] PROGMEM = {%s};\n' % ', '.join(str(len(built[n]['tiles'])) for n in names))
        f.write('static const u32 stage_bitmap[] PROGMEM = {%s};\n' % ', '.join('SPI_%s_BITMAP' % n.upper() for n in names))
        f.write('static const u32 stage_vram[] PROGMEM = {%s};\n' % ', '.join('SPI_%s_VRAM' % n.upper() for n in names))
        f.write('static const char stage_name[][9] PROGMEM = {%s};\n' % ', '.join('"%s"' % n[:8] for n in names))

    # ---- report
    print('SPI image: %d of %d bytes (%.1f%%)' % (len(spi), SPI_LIMIT, 100 * len(spi) / SPI_LIMIT))
    for label, off, ln in layout: print('  %-28s @0x%05X %6d' % (label, off, ln))
    print('fighters: %d frames (incl. variants), %d unique tiles, sprite black in palette slot %d'
          % (len(frames), len(ftiles), black))
    print('mode 4 left-column rows: %d distinct (%d bytes SRAM if kept in RAM)' % (len(left_rows), 96 * len(left_rows)))
    ok = True
    for n, st in built.items():
        v = verify(st, a.bitmap_rows); ok &= v
        print('stage %-8s mode0 ROM tiles %3d (%5d B flash)  verify %s'
              % (n, len(st['tiles']), 32 * len(st['tiles']), 'OK' if v else 'FAILED'))
    # fighter round trip
    lookup = [tile_from_bytes(t) for t in ftiles]; fok = True
    for name, place, img4 in frames:
        out = np.zeros((96, 40), np.uint8)
        for dx, dy, ti, fl in place:
            t = lookup[ti]; out[dy:dy + 8, dx:dx + 8] = np.fliplr(t) if fl else t
        fok &= bool((out[:, :36] == img4).all())
    print('fighter verify', 'OK' if fok else 'FAILED')
    if not (ok and fok): sys.exit(1)

if __name__ == '__main__':
    main()
