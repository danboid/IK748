Here's a full build of ik748 from scratch.

It's quite tricky but it avoids distributing copyrighted game data and allows this code to be distributed legally.

**1. One-time setup**

- **Tools:** VICE 3.x, the AVR toolchain (`gcc-avr`, `avr-libc`, `binutils-avr`) and Python 3 with numpy and py65:
  ```
  pip install --user --break-system-packages numpy py65
  ```
  Or use a virtual environment, as before, and run every script with its `python3`.
- **ROMs:** in `~/.local/share/vice/C64/`, named `kernal-901227-03.bin`, `basic-901226-01.bin` and `chargen-901225-01.bin`.
- **Files:** the latest ik478 sources plus `intkara2.t64`

**2. Start clean**

If you've done a previous build, run:

```
cd ~/src/uzebox/demos/ik748
rm -rf build _bin_ _obj_
cd ik_extract
rm -f tr_*.pkl bonus4.pkl
```

**3. Start VICE (terminal 1)**

```
x64sc -binarymonitor -binarymonitoraddress ip4://127.0.0.1:6502 -autostart intkara2.t64
```

Wait about 15 seconds, until the attract demo is playing. Leave it running through steps 4 and 5.

**4. Capture the four stages (terminal 2, about 6 minutes)**

```
python3 trace_stages.py
```

It prints one key per stage and writes `tr_<key>.pkl` for each, normally `363717b0`, `d2e9b449`, `ee06c810` and `b66c10a8`. If it prints "capture of … failed", it retries automatically when that stage comes round again.

**5. Capture the breaking round (a few minutes)**

```
python3 capture_bonus.py bonus4.pkl
```

It waits for a demo bout to end, forces the breaking round, and saves the stack intact and fully cracked. Wait for `saved bonus4.pkl`, then close VICE.

**6. Convert the graphics and bonus data**

```
python3 convert748.py --out build --stage s1=tr_363717b0.pkl --stage s2=tr_d2e9b449.pkl --stage s3=tr_ee06c810.pkl --stage s4=tr_b66c10a8.pkl --bonus4 bonus4.pkl
```

Use the keys step 4 printed if they differ; the order of the `--stage` options sets the stage order in the game. Check that the output:

- ends with `verify OK` for all four stages and for the fighters;
- lists `SPI_BONUS_TILES` and `SPI_FIGHTER_MASKS`;
- shows an SPI total under 131,072 bytes (about 90 KB).

**7. Export moves, rules and sound samples**

```
python3 export_moves.py tr_363717b0.pkl build/ik_moves.h
```

It should report 35 moves, 199 steps and 20 tables, and also write `../build/ik_sfx.h` with the 6 sampled effects.

**8. Build the game**

```
make clean
make
```

It should end with these two checks:

- `RAM: globals end at 0x0080055d (limit 0x008005A0)`, or any value at or below the limit.
- `fighter_recolor at 0x0000c000 (must be 0x0000c000)`

The game is `_bin_/ik748.hex`. For an `.uze` file as well, add `PACKROM=../../tools/packrom/packrom`, once packrom is built.

**9. Run it**

Copy `_bin_/ik748.uze` and `build/ikspi.bin` to the SD card root. In CUzeBox, put `ikspi.bin` in the same folder as the `.hex`.
