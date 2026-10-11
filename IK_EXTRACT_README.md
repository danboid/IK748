# International Karate (C64) – measurement tools for a Uzebox Mode 748 port

Run VICE headless with the binary monitor, then run the scripts against it.
The scripts dump RAM from your own copy into local .pkl files; they never leave your machine.

    # ROMs in ~/.local/share/vice/C64/ as kernal-901227-03.bin, basic-901226-01.bin, chargen-901225-01.bin
    setsid xvfb-run -a x64sc -default -binarymonitor -binarymonitoraddress ip4://127.0.0.1:6502 \
        -sound -sounddev dummy -autostart intkara2.t64 &

    python3 cap.py 500 run1.pkl       # ~6 min: sprite bands + full RAM, sampled through the demo
    python3 fighters.py               # rebuild each fighter (3x5 multiplexed sprites) -> frames.pkl
    python3 fighter_stats.py          # bounding boxes, distinct frames, colours
    python3 budget.py                 # unique 8x8 sprite tiles, RAM tiles per frame
    python3 trace_stages.py           # raster-trace one frame per stage -> tr_<key>.pkl
    python3 bgstats.py tr_*.pkl       # per-stage tiles/colours by screen section

bm.py is a small VICE binary-monitor client (memory reads, checkpoints, stepping, display grab).

Notes
- Colour RAM's upper nibble is undefined; always mask with & 15.
- Sprite pointers are written just after each band's Y move: band n of a fighter uses base + 3n.
- Stage identity = hash of charset $4000-$47FF excluding chars 50-63 (rewritten every frame).
- A trace taken within a few seconds of a stage change can catch transition text; re-trace if
  hires cells show up in the ground rows.

## Fighter frame table (found in session 2)

    python3 writers.py                   # PCs writing the sprite buffers -> copy loops at $3E3F / $3F18
    python3 dis6502.py 3d50-3fa1         # disassemble (pip install py65); also saves ram_now.bin
    python3 frametable.py ram_now.bin    # decode + count all frames

Format, per frame F (0-63):
- $7800+2F -> 12-byte header, one byte per 8-line row: high nibble = start cell column, low nibble = cell count
- $7880+2F -> cell data, 8 bytes per 4x8 multicolour cell, in header order
- right-facing only; left-facing is produced by mirroring each byte through a table at $0400
- frames $2B/$2F: first 24 bytes overwritten at runtime (routine $3C2A) with one of four
  variants at $3BC6 (offsets $00/$18/$30/$48) or zeros; frame $33: two bytes poked by $3CAC
- entry 4 is an empty frame; entries 54-63 unused

## Characters 50-63

    python3 charw.py                     # writer PCs and screen positions

They hold the referee's speech bubble (5x2 cells at rows 15-16, cols 29-33) and a 4x1 strip at
row 17, cols 22-25, drawn in software (main writer at $3BA7).

## Converting to Mode 748 data (session 3)

    python3 trace_stages.py                      # one tr_<key>.pkl per stage (re-run if a trace
                                                 # was caught during a stage transition)
    python3 convert748.py --out build \
        --stage s1=tr_363717b0.pkl --stage s2=tr_d2e9b449.pkl \
        --stage s3=tr_ee06c810.pkl --stage s4=tr_b66c10a8.pkl

Stage names are just labels; name them after looking at each one (the keys are charset hashes,
not locations). Characters 50-63 (speech bubble, score popups) are replaced with the row's
usual ground character so they aren't baked into the background.

Options: --xoff (default 24: image at x 24-183, so the mode 4 left column is plain border and
one 96-byte row serves every line), --bitmap-rows (default 12: tile rows 0-11 in mode 4).

The script refuses to write an SPI image over 128 KB, and finishes by rebuilding every stage
and every fighter frame from its own output and comparing pixel for pixel ("verify OK").

Outputs: ikspi.bin + spi_layout.h (SPI RAM contents/offsets), fighter_frames.h (tile
placement lists, FR_* names incl. the $2B/$2F/$33 runtime variants), palettes.h (16-entry
palettes indexed by C64 colour, sprite-black slot, white/red recolour tables), zone_<stage>.h
(mode 0 ROM tiles in section .tiles), bitmap_left.h (mode 4 left columns), stages.h
(stage index; include it in exactly one C file). --section sets the linker section (default .tiles).

## Bonus rounds (session 4)

    python3 capture_bonus.py bonus4.pkl      # VICE running; waits for a demo bout to end
    python3 convert748.py ... --bonus4 bonus4.pkl

capture_bonus.py switches the game into the breaking round and saves the moment the brick
stack is ready. bonus_extract.py (used by convert748.py, needs py65) then:
- decodes the brick stack from the sprite slots in front of the fighter;
- renders every projectile by running the game's own drawing routines ($31DD, $329D,
  $3319) on a 6502 emulator against your RAM dump;
- writes 1-bit fighter collision masks (SPI) and the bonus tables;
- draws the speech bubbles (original art, same 3x5 font as the HUD).
Output: bonus.h, plus SPI_BONUS_TILES and SPI_FIGHTER_MASKS in ikspi.bin.

## Sampled sound effects (session 5)

export_moves.py also writes ik_sfx.h next to ik_moves.h: the six 4-bit sampled effects
($BF00-$CFFF, two per byte; tables at $0DC7/$0DCD/$0DD9) converted to 8-bit signed PCM,
resampled from the C64's ~4054 Hz to 3934 Hz (kernel note 11, one sample per 4 mixer
ticks), with a faded end and a silent tail, plus the trigger tables ($0D36-$0D78).
