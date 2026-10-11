/*
 * International Karate port - HUD (new code, original 3x5 font)
 */
#include <avr/pgmspace.h>
#include <spiram.h>
#include "hud.h"

#define LINE_BYTES  84U      /* mode 4: 168 SPI pixels per line */
#define HUD_LINES   16U

static u32 hud_base;
static u8  rowbuf[LINE_BYTES];   /* static: the main stack is small in Mode 748 */

/* 3x5 glyphs for ' ' .. 'Z', one byte per row, bit 2 = left pixel */
static const u8 font[59U * 5U] PROGMEM = {
	0,0,0,0,0,  0,0,0,0,0,  0,0,0,0,0,  7,7,7,7,7,  0,0,0,0,7,  0,0,7,7,7,   /* sp ! " # $ % */
	0,0,0,0,0,  0,0,0,0,0,  0,0,0,0,0,  0,0,0,0,0,  0,0,0,0,0,  0,0,0,0,0,   /* & ' ( ) * + */
	0,0,0,0,0,  0,0,7,0,0,  0,0,0,0,2,  1,1,2,4,4,                           /* , - . /     */
	7,5,5,5,7,  2,6,2,2,7,  7,1,7,4,7,  7,1,7,1,7,  5,5,7,1,1,               /* 0 1 2 3 4   */
	7,4,7,1,7,  7,4,7,5,7,  7,1,2,2,2,  7,5,7,5,7,  7,5,7,1,7,               /* 5 6 7 8 9   */
	0,2,0,2,0,  0,0,0,0,0,  0,0,0,0,0,  0,0,0,0,0,  4,2,1,2,4,  0,0,0,0,0,  0,0,0,0,0,  /* : ; < = > ? @ */
	2,5,7,5,5,  6,5,6,5,6,  3,4,4,4,3,  6,5,5,5,6,  7,4,6,4,7,  7,4,6,4,4,   /* A B C D E F */
	3,4,5,5,3,  5,5,7,5,5,  7,2,2,2,7,  1,1,1,5,2,  5,5,6,5,5,  4,4,4,4,7,   /* G H I J K L */
	5,7,7,5,5,  6,5,5,5,5,  2,5,5,5,2,  6,5,6,4,4,  2,5,5,6,3,  6,5,6,5,5,   /* M N O P Q R */
	3,4,2,1,6,  7,2,2,2,2,  5,5,5,5,7,  5,5,5,5,2,  5,5,7,7,5,  5,5,2,5,5,   /* S T U V W X */
	5,5,2,2,2,  7,1,2,4,7                                                    /* Y Z         */
};

static void put_row(u8 col, u8 line, u8 const* buf, u8 len)
{
	u32 a = hud_base + (u32)(line) * LINE_BYTES + (u32)(col) * 2U;
	SpiRamWriteFrom((u8)(a >> 16), (u16)(a), (void*)buf, len);
}

static void draw(u8 col, u8 y, const char* s, u8 colour, u8 flash)
{
	u8* buf = rowbuf;
	u8 r, n, i, ch, bits;

	for (r = 0U; r < 5U; r++) {
		n = 0U;
		for (i = 0U; ; i++) {
			ch = flash ? pgm_read_byte(&s[i]) : (u8)(s[i]);
			if ((ch == 0U) || (col + i >= 40U)) { break; }
			if ((ch < ' ') || (ch > 'Z')) { ch = ' '; }
			bits = pgm_read_byte(&font[(u16)(ch - ' ') * 5U + r]);
			buf[n++] = (u8)(((bits & 4U) ? (colour << 4) : 0U) | ((bits & 2U) ? colour : 0U));
			buf[n++] = (u8)( (bits & 1U) ? (colour << 4) : 0U);
		}
		if (n != 0U) { put_row(col, y + r, buf, n); }
	}
}

void hud_text(u8 col, u8 y, const char* s, u8 colour)   { draw(col, y, s, colour, 0U); }
void hud_text_P(u8 col, u8 y, const char* s, u8 colour) { draw(col, y, s, colour, 1U); }

void hud_blank(u8 col, u8 y, u8 len)
{
	u8* buf = rowbuf;
	u8 r;
	if (len > 40U) { len = 40U; }
	for (r = 0U; r < 2U * len; r++) { buf[r] = 0U; }
	for (r = 0U; r < 5U; r++) { put_row(col, y + r, buf, 2U * len); }
}

void hud_init(u32 bitmap_spi)
{
	u8* buf = rowbuf;
	u8 i;
	hud_base = bitmap_spi;
	for (i = 0U; i < LINE_BYTES; i++) { buf[i] = 0U; }
	for (i = 0U; i < HUD_LINES; i++) {
		u32 a = hud_base + (u32)(i) * LINE_BYTES;
		SpiRamWriteFrom((u8)(a >> 16), (u16)(a), buf, LINE_BYTES);
	}
}
