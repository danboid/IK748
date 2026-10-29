###############################################################################
# International Karate -> Uzebox Mode 748, stage 1: two-player bout
#
#   make KERNEL_DIR=/path/to/uzebox/kernel ASSETS_DIR=/path/to/converter/build
#
# ASSETS_DIR is the --out directory of convert748.py (headers only are used
# here; copy ikspi.bin to the SD card).
###############################################################################
GAME       = ik748
MCU        = atmega644
CC         = avr-gcc
KERNEL_DIR ?= ../../kernel
ASSETS_DIR ?= build
PACKROM    ?= packrom
OUTDIR     = _bin_
OBJDIR     = _obj_

KERNEL_OPTIONS = -DVIDEO_MODE=748 -DINTRO_LOGO=0 -DSOUND_MIXER=MIXER_TYPE_INLINE -DSOUND_CHANNEL_5_ENABLE=1 \
                 -DMUSIC_ENGINE=STREAM -DSTREAM_MUSIC_RAM=1 -DSONG_BUFFER_SIZE=32

COMMON   = -mmcu=$(MCU)
CFLAGS   = $(EXTRA) $(COMMON) -Wall -gdwarf-2 -std=gnu99 -DF_CPU=28636360UL -Os -fsigned-char \
           -ffunction-sections -fno-toplevel-reorder $(KERNEL_OPTIONS) -include m74cfg.h
ASMFLAGS = $(CFLAGS) -x assembler-with-cpp -Wa,-gdwarf2
LDFLAGS  = $(COMMON) -Wl,-Map=$(OUTDIR)/$(GAME).map -Wl,-gc-sections \
           -Wl,--section-start=.tiles=0xC000
INCLUDES = -I"$(KERNEL_DIR)" -I"$(ASSETS_DIR)" -I.

OBJECTS = $(OBJDIR)/uzeboxVideoEngineCore.o $(OBJDIR)/uzeboxCore.o \
          $(OBJDIR)/uzeboxSoundEngine.o $(OBJDIR)/uzeboxSoundEngineCore.o \
          $(OBJDIR)/uzeboxVideoEngine.o $(OBJDIR)/spiram.o $(OBJDIR)/bootlib.o \
          $(OBJDIR)/main.o $(OBJDIR)/fight.o $(OBJDIR)/hud.o $(OBJDIR)/ai.o

all: $(OUTDIR)/$(GAME).hex check
	-$(PACKROM) $(OUTDIR)/$(GAME).hex $(OUTDIR)/$(GAME).uze gameinfo.properties

$(OBJDIR) $(OUTDIR):
	mkdir -p $@

$(OBJDIR)/%.o: $(KERNEL_DIR)/%.s | $(OBJDIR)
	$(CC) $(INCLUDES) $(ASMFLAGS) -c $< -o $@
$(OBJDIR)/%.o: $(KERNEL_DIR)/%.c | $(OBJDIR)
	$(CC) $(INCLUDES) $(CFLAGS) -c $< -o $@
$(OBJDIR)/main.o: main.c m74cfg.h sfx.h ai.h hud.h fight.h $(wildcard $(ASSETS_DIR)/*.h) | $(OBJDIR)
	$(CC) $(INCLUDES) $(CFLAGS) -c $< -o $@

$(OUTDIR)/$(GAME).elf: $(OBJECTS) | $(OUTDIR)
	$(CC) $(LDFLAGS) $(OBJECTS) -o $@

$(OUTDIR)/$(GAME).hex: $(OUTDIR)/$(GAME).elf
	avr-objcopy -O ihex -R .eeprom $< $@
	avr-size $<

# Layout checks: C globals must end below the Mode 4 line buffer (0x05A0, as an
# AVR data address 0x8005A0), which sits just below the sprite RAM tiles, and the recolour table must sit
# exactly at M74_RECTB_OFF.
check: $(OUTDIR)/$(GAME).elf
	@end=$$(avr-nm $< | awk '$$3=="__bss_end"{print $$1}'); \
	 echo "RAM: globals end at 0x$$end (limit 0x008005A0)"; \
	 [ $$((0x$$end)) -le $$((0x008005A0)) ] || { echo "ERROR: globals overlap the Mode 4 buffer / sprite RAM tiles"; exit 1; }
	@rec=$$(avr-nm $< | awk '$$3=="fighter_recolor"{print $$1}'); \
	 echo "fighter_recolor at 0x$$rec (must be 0x0000c000)"; \
	 [ "$$rec" = "0000c000" ] || { echo "ERROR: recolour table not at M74_RECTB_OFF"; exit 1; }

clean:
	rm -rf $(OBJDIR) $(OUTDIR)

.PHONY: all check clean

$(OBJDIR)/fight.o: fight.c fight.h m74cfg.h $(wildcard $(ASSETS_DIR)/*.h) | $(OBJDIR)
	$(CC) $(INCLUDES) $(CFLAGS) -c $< -o $@
$(OBJDIR)/hud.o: hud.c hud.h m74cfg.h | $(OBJDIR)
	$(CC) $(INCLUDES) $(CFLAGS) -c $< -o $@
$(OBJDIR)/ai.o: ai.c ai.h fight.h m74cfg.h | $(OBJDIR)
	$(CC) $(INCLUDES) $(CFLAGS) -c $< -o $@
