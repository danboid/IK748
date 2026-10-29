Here's a full build of IK748 from scratch.

It's quite tricky, but it avoids distributing copyrighted game data and allows this code to be distributed legally: every asset is extracted from your own copy of the game.

**1. One-time setup**

- **Tools:** VICE 3.x, the AVR toolchain (`gcc-avr`, `avr-libc`, `binutils-avr`) and Python 3 with numpy and py65:
  ```
  pip install --user --break-system-packages numpy py65
  ```
  Or use a virtual environment and run every script with its `python3`.
- **ROMs:** in `~/.local/share/vice/C64/`, named `kernal-901227-03.bin`, `basic-901226-01.bin` and `chargen-901225-01.bin`.
- **Sources:** clone this repository into the Uzebox repo's `demos` folder, so the Makefile finds the kernel at `../../kernel`:
  ```
  cd ~/src/uzebox/demos
  git clone https://github.com/danboid/IK748.git
  ```
  (Elsewhere, add `KERNEL_DIR=/path/to/uzebox/kernel` to the `make` commands.) Copy your `intkara2.t64` into the IK748 folder.

All the commands below are run in the IK748 folder.

**2. Start clean**

If you've done a previous build:

```
rm -rf build _bin_ _obj_
rm -f tr_*.pkl bonus4.pkl ram_music.bin ik_log.pkl ikmusic*
```

(Keep `ik_log.pkl` if you only want to re-run the music conversion quickly; it caches the slow emulation.)

**3. Start VICE (terminal 1)**

```
x64sc -binarymonitor -binarymonitoraddress ip4://127.0.0.1:6502 -autostart intkara2.t64
```

Wait about 15 seconds, until the attract demo is playing. Leave it running through steps 4 to 6.

**4. Capture the four stages (terminal 2, about 6 minutes)**

```
python3 trace_stages.py
```

It prints one key per stage and writes `tr_<key>.pkl` for each, normally `363717b0`, `d2e9b449`, `ee06c810` and `b66c10a8`. If it prints "capture of … failed", it retries automatically when that stage comes round again.

**5. Capture the breaking round (a few minutes)**

```
python3 capture_bonus.py bonus4.pkl
```

It waits for a demo bout to end, forces the breaking round, and saves the stack intact and fully cracked. Wait for `saved bonus4.pkl`.

**6. Dump RAM for the music (optional)**

Skip this step and step 7 to build without music. With the demo still playing:

```
python3 -c "from bm import BM; m=BM(); m.cmd(0x81); open('ram_music.bin','wb').write(m.mem(0,0xffff,'cpu')); m.resume()"
```

You can now close VICE.

**7. Convert the music (optional)**

```
python3 sid2uze.py convert --ram ram_music.bin --init AE00,AE09 --play AE0C --seconds 900 --cache ik_log.pkl --out ikmusic
```

The first run emulates 15 minutes of music and takes several minutes; reruns with the same `--cache` file take seconds. It should report a loop of about 663 s and a stream song of about 25 KB, and write `ikmusic_stream.bin`, `ikmusic_stream.h` and `ikmusic_patches.inc` (plus `ikmusic.mid` and `ikmusic_report.txt`). See `README-sid2uze.md`.

**8. Convert the graphics, bonus data and music**

```
python3 convert748.py --out build --stage s1=tr_363717b0.pkl --stage s2=tr_d2e9b449.pkl --stage s3=tr_ee06c810.pkl --stage s4=tr_b66c10a8.pkl --bonus4 bonus4.pkl --music ikmusic_stream.bin
```

Leave out `--music ikmusic_stream.bin` if you skipped steps 6 and 7. Use the keys step 4 printed if they differ; the order of the `--stage` options sets the stage order in the game. Check that the output:

- ends with `verify OK` for all four stages and for the fighters;
- lists `SPI_BONUS_TILES` and `SPI_FIGHTER_MASKS`, and `SPI_MUSIC` with music;
- shows an SPI total under 131,072 bytes (about 90 KB without music, about 115 KB with it).

If you converted the music, copy its two headers into the build folder (the game builds without music if they're missing):

```
cp ikmusic_patches.inc ikmusic_stream.h build/
```

**9. Export moves, rules and sound samples**

```
python3 export_moves.py tr_363717b0.pkl build/ik_moves.h
```

It should report 35 moves, 199 steps and 20 tables, and also write `build/ik_sfx.h` with the 6 sampled effects.

**10. Build the game**

```
make clean
make
```

It should end with these two checks:

- `RAM: globals end at 0x008005xx (limit 0x008005A0)`: any value at or below the limit (about `0x0080058a` with music).
- `fighter_recolor at 0x0000c000 (must be 0x0000c000)`

The game is `_bin_/ik748.hex`. For an `.uze` file as well, add `PACKROM=../../tools/packrom/packrom`, once packrom is built.

**11. Run it**

Copy `_bin_/ik748.uze` (or the `.hex`) and `build/ikspi.bin` to the SD card root. In CUzeBox, put `ikspi.bin` in the same folder as the `.hex`.
