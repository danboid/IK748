# sid2uze

Convert C64 SID music to a MIDI file and a Uzebox patch file.

    pip install py65
    python3 sid2uze.py convert tune.sid --out tune             # PSID file
    python3 sid2uze.py convert --ram dump.bin --init AE00,AE09 --play AE0C --out tune
    python3 sid2uze.py analyse ...        # activity / size report only
    python3 sid2uze.py dump ... --out regs.txt

Writes tune.mid, tune_patches.inc and tune_report.txt. Use --seconds to set the capture
length (long enough for the start of the tune to come round again; --loop START,LENGTH
in seconds forces it) and --cache FILE to keep
the captured register log, so reruns skip the slow 6502 emulation.

Then convert the MIDI with the Uzebox midiconv tool:

    midiconv -f 72 -1 -2 -3 tune.mid tune_song.inc

The MIDI file uses 50 ticks per quarter note at 60 BPM (one tick per C64 frame), so -f 72
gives Uzebox 60 Hz frames and the tune plays at the original speed. -1 -2 -3 keep the
note-offs sid2uze writes on the three tonal channels: it only writes one where a voice falls
silent before its next note (--gap, default 4 frames), since back-to-back notes retrigger
the channel anyway. This keeps rests correct at a fraction of the size of full note-offs. Loop markers S/E are written when
a loop is found. Audition tune_patches.inc in UzeSynth or with uzerender.

How it converts
- Notes come from the gate bit (a gate cleared and set again in one frame retriggers);
  base pitch from the SID frequency register (PAL clock).
- Per note, the per-frame semitone offsets are classified: a repeating cycle becomes a
  looping arpeggio patch (PC_LOOP_START/END with NOTE_UP/DOWN steps), a one-way run
  becomes pitch steps (slides, drum drops), anything else plays static.
- Triangle -> wave 2, sawtooth -> wave 1, pulse -> the nearest of the 25/50/75% squares,
  ring-modulated triangle -> wave 6 (approximation), mostly-noise notes -> the noise
  channel as drums (MIDI channel 10; note n = patch n, drum patches come first).
- SID attack/decay/sustain map to the patch's start volume and envelope speeds using
  the SID's timing tables; similar envelopes are merged.
- Not reproduced (reported): filters, vibrato and sub-semitone bends, pulse-width
  sweeps, hard sync, exact ring modulation. RSID tunes and tunes with play address 0
  are not supported yet.

GPL-3.0-or-later.
