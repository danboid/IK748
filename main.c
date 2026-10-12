/*
 * International Karate -> Uzebox Mode 748
 *
 * New game code for the Uzebox. Stage graphics, fighter frames and the move,
 * control and scoring tables are produced by convert748.py and export_moves.py
 * from your own copy of the game; the rules that use them are in fight.c.
 *
 * One player (pad 1, white, against the computer) or two players (pad 2 red). Eight directions plus fire (any of
 * A/B/X/Y) give the sixteen moves; pulling away while the opponent strikes at
 * close range blocks.
 *
 * Load errors show a full-screen colour (see README).
 */

#include <stdbool.h>
#include <avr/io.h>
#include <avr/pgmspace.h>
#include <uzebox.h>
#include <spiram.h>
#include <bootlib.h>

#include "spi_layout.h"
#include "fighter_frames.h"
#include "stages.h"          /* defines all stage data; recolour table first */
#include "fight.h"
#include "hud.h"
#include "ai.h"
#include "sfx.h"
#include "bonus.h"

#if (BITMAP_LEFT_SHARED == 0)
	#error "This test needs one shared mode 4 left column: run the converter with --xoff 24"
#endif

#define FRAME_Y      96U     /* C64 raster 147 = line 96 = top of the fighter frames */

/* ------------------------------------------------------------------ VRAM */

static u8 rowsel[] = { 0U, 255U };                     /* logical line 0 at the top */

static m74_mode4_vram_t m4row;                          /* shared by all bitmap rows */
static m74_mode0_vram_t m0row[25U - BITMAP_ROWS];       /* fighter zone, ground, credits */
static m74_mode2_vram_t blankrow = { 2U | M74_CFG_PAL_SRC_NONE, 0U, 0U };

#define ROWP(r) ((u16)( ((r) < BITMAP_ROWS) ? (void*)(&m4row) : \
                        ((r) < 25U)         ? (void*)(&m0row[(r) - BITMAP_ROWS]) : \
                                              (void*)(&blankrow) ))

static u16 const row_table[32U] PROGMEM = {
	ROWP( 0), ROWP( 1), ROWP( 2), ROWP( 3), ROWP( 4), ROWP( 5), ROWP( 6), ROWP( 7),
	ROWP( 8), ROWP( 9), ROWP(10), ROWP(11), ROWP(12), ROWP(13), ROWP(14), ROWP(15),
	ROWP(16), ROWP(17), ROWP(18), ROWP(19), ROWP(20), ROWP(21), ROWP(22), ROWP(23),
	ROWP(24), ROWP(25), ROWP(26), ROWP(27), ROWP(28), ROWP(29), ROWP(30), ROWP(31)
};

/* Error screen: every row is a single-colour mode 2 row */
static m74_mode2_vram_t errrow = { 2U | M74_CFG_PAL_SRC_NONE, 0U, 1U };
static u16 const err_table[32U] PROGMEM = {
	[0 ... 31] = (u16)(&errrow)
};
static u8 const err_colours[5U] PROGMEM = { 0x00U, 0x07U, 0x3FU, 0xC7U, 0xC0U };

static void show_error(u8 code)
{
	u8* pal = (u8*)(m74_paddr);
	pal[1]  = pgm_read_byte(&err_colours[code < 5U ? code : 1U]);
	m74_vaddr   = (u16)(&err_table[0]);
	m74_config |= M74_CFG_ENABLE;
	while (1);
}

/* ------------------------------------------------------------- SD -> SPI */

static u8 load_spi_image(void)
{
	sdc_struct_t sds;
	u32 left = SPI_USED;
	u32 clus;
	u16 addr = 0U;
	u16 n;
	u8  bank = 0U;

	sds.bufp = (u8*)(RT_BASE * 32U);   /* RAM tile area is free until sprites run */
	if (FS_Init(&sds) != 0U) { return 1U; }
	if (SpiRamInit() == 0U)  { return 4U; }

	clus = FS_Find(&sds,
	    ((u16)('I') << 8) | (u16)('K'),
	    ((u16)('S') << 8) | (u16)('P'),
	    ((u16)('I') << 8) | (u16)(' '),
	    ((u16)(' ') << 8) | (u16)(' '),
	    ((u16)('B') << 8) | (u16)('I'),
	    ((u16)('N') << 8) | (u16)(0));
	if (clus == 0U) { return 2U; }
	FS_Select_Cluster(&sds, clus);

	while (left != 0U) {
		if (FS_Read_Sector(&sds) != 0U) { return 3U; }
		n = (left > 512U) ? 512U : (u16)(left);
		SpiRamWriteFrom(bank, addr, sds.bufp, n);   /* 512-byte steps never straddle 64K */
		addr += n;
		if (addr == 0U) { bank ++; }
		left -= n;
		if ((left != 0U) && (FS_Next_Sector(&sds) != 0U)) { return 3U; }
	}
	return 0U;
}

/* ----------------------------------------------------------------- stage */

static void set_stage(u8 s)
{
	u8*  pal  = (u8*)(m74_paddr);
	u8 const* srcpal = (u8 const*)pgm_read_word(&stage_pal[s]);
	u16  zone = pgm_read_word(&stage_zone[s]);
	u32  bm   = pgm_read_dword(&stage_bitmap[s]);
	u32  vr   = pgm_read_dword(&stage_vram[s]);
	u8   i;

	for (i = 0U; i < 16U; i++) { pal[i] = pgm_read_byte(&srcpal[i]); }

	m74_m4_bank = (u8)(bm >> 16);
	m74_m4_addr = (u16)(bm);

	for (i = 0U; i < (25U - BITMAP_ROWS); i++) {
		u32 a = vr + (u32)(i) * 25U;               /* converter: 24 tiles + 1 pad per row */
		m0row[i].config    = 0U | ((a >> 16) ? M74_CFG_SPIRAM_A16 : 0U);
		m0row[i].bg_addr   = (u16)(a);
		m0row[i].t0_addr_h = (u8)(zone >> 8);
		m0row[i].t1_addr_h = (u8)((zone + (128U * 32U)) >> 8);
	}
}

/* -------------------------------------------------------------- fighters */

/* Both fighters are blitted row by row, top to bottom, so tiles are finished
** in the order the beam reaches them; within a row the front fighter goes last
** so it stays on top. Sprites are only redrawn when something changed. */
typedef struct {
	FighterTile const* p;
	u8 n, x, left, col;
} drawctx_t;

static void ctx_setup(drawctx_t* c, u8 i)
{
	u8 fr = pgm_read_byte(&c64_frame_map[fgt[i].frame & 63U]);
	if (fr == 0xFFU) { c->n = 0U; return; }
	c->p    = (FighterTile const*)pgm_read_word(&fighter_frame[fr]);
	c->n    = pgm_read_byte(&fighter_frame_len[fr]);
	c->x    = (u8)(XOFF + fgt[i].x - 16U);   /* C64 sprite X = 2x - 7 -> box left = x - 16 */
	c->left = (fgt[i].face != 0U);
	c->col  = (i != 0U) ? RECOLOR_RED : RECOLOR_WHITE;
}

static void ctx_row(drawctx_t* c, u8 dy)
{
	while ((c->n != 0U) && (pgm_read_byte(&c->p->dy) == dy)) {
		u8  dx  = pgm_read_byte(&c->p->dx);
		u32 a   = SPI_FIGHTER_TILES + ((u32)pgm_read_word(&c->p->tile) * 32U);
		u8  flg = pgm_read_byte(&c->p->flags) & M74_SPR_FLIPX;
		u8  px;
		if (c->left) { px = c->x + 28U - dx; flg ^= M74_SPR_FLIPX; }
		else         { px = c->x + dx; }
		if ((a >> 16) != 0U) { flg |= M74_SPR_SPIRAM_A16; }
		if (c->col == 0U) { M74_BlitSprite((u16)(a), px + 8U, FRAME_Y + dy + 8U, flg); }
		else              { M74_BlitSpriteCol((u16)(a), px + 8U, FRAME_Y + dy + 8U, flg, c->col); }
		c->p ++;
		c->n --;
	}
}

/* Extra sprite tiles (bubbles, bricks, projectiles): screen x, zone y, tile */
typedef struct { u8 x, y, tile; } extra_t;
#define MAX_EXTRAS 40U
static extra_t extras[MAX_EXTRAS];
static u8      nextras;
static u8      fgt_vis = 3U;           /* bit i: fighter i is drawn */

#if HAVE_BONUS
static void extras_add(BonusTile const* p, u8 n, s16 x, s16 y)
{
	while ((n != 0U) && (nextras < MAX_EXTRAS)) {
		s16 tx = x + (s8)pgm_read_byte(&p->dx);
		s16 ty = y + (s8)pgm_read_byte(&p->dy);
		if ((tx > -8) && (tx < 192) && (ty >= 0) && (ty < 96)) {
			extras[nextras].x = (u8)(tx + 8);       /* stored with the blitter's +8 */
			extras[nextras].y = (u8)ty;
			extras[nextras].tile = pgm_read_byte(&p->tile);
			nextras ++;
		}
		p ++; n --;
	}
}
#endif

static void extras_row(u8 dy)
{
#if HAVE_BONUS
	u8 i;
	for (i = 0U; i < nextras; i++) {
		if ((extras[i].y & 0xF8U) == dy) {
			u32 a = SPI_BONUS_TILES + (u32)(extras[i].tile) * 32U;
			M74_BlitSprite((u16)(a), extras[i].x, FRAME_Y + extras[i].y + 8U,
			               ((a >> 16) != 0U) ? M74_SPR_SPIRAM_A16 : 0U);
		}
	}
#else
	(void)dy;
#endif
}

#ifdef DEBUG_TIMING
static void check_row(u8 dy);
#endif
static void draw_both(void)
{
	drawctx_t c[2];
	u8 dy;
	ctx_setup(&c[0], fgt_front ^ 1U);
	ctx_setup(&c[1], fgt_front);
	if (!(fgt_vis & (1U << (fgt_front ^ 1U)))) { c[0].n = 0U; }
	if (!(fgt_vis & (1U << fgt_front)))        { c[1].n = 0U; }
	for (dy = 0U; dy < 96U; dy += 8U) {
		ctx_row(&c[0], dy); ctx_row(&c[1], dy); extras_row(dy);
#ifdef DEBUG_TIMING
		check_row(dy);
#endif
	}
}

/* ------------------------------------------------------------------ game */

#define STEP_FRAMES  5U      /* C64: 4 frames per step at 50 Hz */
#define T_READY     14U      /* in steps */
#define T_POINT     30U
#define T_WIN       48U
#define T_OVER      60U

enum { ST_TITLE, ST_READY, ST_FIGHT, ST_POINT, ST_WIN, ST_OVER, ST_BONUS };

static u8   state, timer, stage, tick_alt, winner, players = 1U, level;
static bool hud_dirty, redraw;
static const char* msg;
static u8   msg_colour;
static u8   prev_move[2], prev_atk[2], prev_fallen[2];
static u16  pad_latch[2], pad_prev;
static u8   bubble = 0xFFU;          /* speech bubble beside the referee, 0xFF = none */
static u8   bouts, wins, klevel;      /* running order (C64 rules) */

/* Bout timer (C64 rules): 30 s for one player, 60 s for two; one second per 50 C64
** frames (60 here); it keeps running through point sequences, not in bonus rounds.
** The winner gets 100 points per second left. */
#ifndef BOUT_TIME_1P
#define BOUT_TIME_1P 30U
#endif
#ifndef BOUT_TIME_2P
#define BOUT_TIME_2P 60U
#endif
static u8   tsec, tfr;
static bool time_dirty, bout_won;

static const char s_over[]  PROGMEM = "GAME OVER";
static const char s_p1[]    PROGMEM = "1 PLAYER";
static const char s_p2[]    PROGMEM = "2 PLAYERS";
static const char s_start[] PROGMEM = "PRESS START";

#define COL_WHITE 1U
#define COL_RED   2U
#define COL_MSG   7U

static void sfx(u8 n) { TriggerFx(n, (n < SFX_PCM_COUNT) ? 0xFFU : 0xD0U, true); }

/* The C64's sound rules: when a fighter's animation frame changes and the new
** frame is one of the eleven sound keys, a sample plays - for attack steps
** during a bout, after a point (plus an optional delayed second sample), or
** from the bonus column in the knife round. */
static u8 snd_last_frame[2] = { 0xFFU, 0xFFU };
static u8 snd_delay_left, snd_delay_fx;
#define SND_MODE_BOUT  0U
#define SND_MODE_POINT 1U
#define SND_MODE_BONUS 2U
static void c64_sound(u8 i, u8 mode)
{
	u8 fr = fgt[i].frame, y, v = 0xFFU;
	if (fr == snd_last_frame[i]) { return; }
	snd_last_frame[i] = fr;
	for (y = 0U; y < 11U; y++) { if (pgm_read_byte(&snd_key[y]) == fr) { break; } }
	if (y == 11U) { return; }
	if (mode == SND_MODE_POINT) {
		u8 d = pgm_read_byte(&snd_delay[y]);
		if (d != 0U) { snd_delay_left = (u8)((d * 6U + 4U) / 5U); snd_delay_fx = pgm_read_byte(&snd_delayed[y]); }
		v = pgm_read_byte(&snd_point[y]);
	} else if (mode == SND_MODE_BONUS) {
		v = pgm_read_byte(&snd_bonus[y]);
	} else if (fgt[i].sflags & SND_ATTACK_FLAGS) {
		v = pgm_read_byte(&snd_attack[y]);
	}
	if (v < SFX_PCM_COUNT) { sfx(v); }
}
static void c64_sound_frame(void)          /* per video frame: the delayed sample */
{
	if ((snd_delay_left != 0U) && (--snd_delay_left == 0U) && (snd_delay_fx < SFX_PCM_COUNT)) { sfx(snd_delay_fx); }
}
static void after_bout(void);
static void hud_time(void);
#if HAVE_BONUS
static void bonus_step(void);
static void bonus_begin(u8 kind, u8 next_stage);
#endif

static void fmt_score(char* b, u16 hundreds)
{
	u8 i;
	for (i = 0U; i < 4U; i++) { b[3U - i] = (char)('0' + hundreds % 10U); hundreds /= 10U; }
	for (i = 0U; (i < 3U) && (b[i] == '0'); i++) { b[i] = ' '; }
	b[4] = '0'; b[5] = '0'; b[6] = 0;
	if ((b[3] == '0') && (b[2] == ' ')) { b[3] = ' '; b[4] = ' '; }
}

static void marks(char* b, u8 pts)
{
	u8 k;
	for (k = 0U; k < 3U; k++) {
		b[k] = (pts >= 2U * k + 2U) ? HUD_MARK_FULL : (pts == 2U * k + 1U) ? HUD_MARK_HALF : HUD_MARK_EMPTY;
	}
	b[3] = 0;
}

static void hud_redraw(void)
{
	char b[8];
	u8 len;

	if (state == ST_TITLE) {
		hud_blank(0U, 2U, 40U);
		hud_blank(0U, 9U, 40U);
		hud_text_P(9U,  2U, s_p1, (players == 1U) ? COL_MSG : COL_WHITE);
		hud_text_P(22U, 2U, s_p2, (players == 2U) ? COL_MSG : COL_WHITE);
		hud_text_P((players == 1U) ? 7U : 20U, 2U, PSTR(">"), COL_MSG);
		hud_text_P(14U, 9U, s_start, COL_WHITE);
		hud_dirty = false;
		return;
	}
	fmt_score(b, fgt[0].score); hud_text(1U, 2U, b, COL_WHITE);
	fmt_score(b, fgt[1].score); hud_text(33U, 2U, b, COL_RED);
	hud_blank(0U, 9U, 40U);
	marks(b, fgt[0].points);    hud_text(1U, 9U, b, COL_WHITE);
	marks(b, fgt[1].points);    hud_text(36U, 9U, b, COL_RED);
	hud_time();
	hud_blank(8U, 2U, 24U);
	if (msg != 0) {
		len = (u8)strlen_P(msg);
		hud_text_P((u8)(20U - (len + 1U) / 2U), 2U, msg, msg_colour);
	}
	hud_dirty = false;
}

static void say(const char* m, u8 colour) { msg = m; msg_colour = colour; hud_dirty = true; }

static void hud_time(void)
{
	char b[8];
	b[0]='T'; b[1]='I'; b[2]='M'; b[3]='E'; b[4]=' ';
	b[5] = (char)('0' + tsec / 10U); b[6] = (char)('0' + tsec % 10U); b[7] = 0;
	hud_text(16U, 9U, b, (tsec <= 5U) ? COL_RED : COL_WHITE);
	time_dirty = false;
}
#if HAVE_BONUS
static void bub(u8 b) { bubble = b; }
#else
static void bub(u8 b) { (void)b; }
#define BUB_BEGIN 0
#define BUB_HALF_POINT 0
#define BUB_FULL_POINT 0
#define BUB_WHITE_WINS 0
#define BUB_RED_WINS 0
#endif

static void ready(void)
{
	fight_place();
	ai_reset(level);
	state = ST_READY; timer = T_READY;
	fgt_vis = 3U;
	bub(BUB_BEGIN);
	bout_won = false;
	hud_dirty = true;                /* scores and point markers back on after a reset */
}

static void new_stage(u8 s)
{
	stage = s;
	set_stage(s);
	hud_init(pgm_read_dword(&stage_bitmap[s]));
	fgt[0].points = fgt[1].points = 0U;
	tsec = (players == 1U) ? BOUT_TIME_1P : BOUT_TIME_2P;
	tfr  = 30U;                      /* the C64's first second is half length */
	ready();
}

static void title(void)
{
	stage = 0U;
	set_stage(0U);
	hud_init(pgm_read_dword(&stage_bitmap[0]));
	fight_place();
	state = ST_TITLE;
	hud_dirty = true;
}

static void award(hit_t const* h)
{
	u8 a = h->attacker, v = a ^ 1U;
	bool win = h->full && (fgt[a].points >= 2U);

	fgt[a].points += h->full ? 2U : 1U;
	if (fgt[a].points > 5U) { fgt[a].points = 5U; }
	fgt[a].score += h->score;

	fight_start_move(v, h->react);
	fgt[v].req = h->react;
	hud_dirty = true;                /* show the new score and point markers */
	fgt[a].req = win ? MOVE_VICTORY : MOVE_STAND;

	if (win) { winner = a; bout_won = true; bub(a ? BUB_RED_WINS : BUB_WHITE_WINS); }
	else     { bub(h->full ? BUB_FULL_POINT : BUB_HALF_POINT); }
	state = ST_POINT; timer = T_POINT;
}


static void sounds_after_tick(void)
{
	u8 i, dist;
	for (i = 0U; i < 2U; i++) {
		fighter_t* f = &fgt[i];
		c64_sound(i, ((state == ST_POINT) || (state == ST_WIN)) ? SND_MODE_POINT : SND_MODE_BOUT);
		if ((f->atk != 0U) && (prev_atk[i] == 0U) && (fgt[i ^ 1U].move == MOVE_BLOCK)) {
			(void)fight_rel(i, &dist);
			if (dist < 8U) { sfx(SFX_BLOCK); }
		}
		prev_move[i] = f->move; prev_atk[i] = f->atk; prev_fallen[i] = f->fallen;
	}
}

static void game_step(void)
{
	hit_t h;
	u16 p0 = pad_latch[0], p1 = pad_latch[1];
	u16 hit = p0 & ~pad_prev;

	pad_prev = p0;
	pad_latch[0] = ReadJoypad(0U);
	pad_latch[1] = ReadJoypad(1U);

	if (state == ST_TITLE) {
		if (hit & (BTN_LEFT | BTN_RIGHT)) { players = (players == 1U) ? 2U : 1U; sfx(SFX_BLIP); hud_dirty = true; }
		if (hit & (BTN_START | BTN_A | BTN_B)) {
			fgt[0].score = fgt[1].score = 0U; level = 0U; bouts = 0U; wins = 0U; klevel = 0U;
			hud_init(pgm_read_dword(&stage_bitmap[0]));
			new_stage(0U);
#if defined(START_BONUS) && HAVE_BONUS
			bonus_begin(START_BONUS, 1U);
#endif
		}
		fight_tick(0U); fight_tick(1U);
		return;
	}

#if HAVE_BONUS
	if (state == ST_BONUS) { bonus_step(); return; }
#endif
	if (state == ST_FIGHT) {
		fight_input(0U, p0);
		if (players == 2U) { fight_input(1U, p1); }
		else               { fgt[1].req = ai_think(1U); }
	}
	fight_tick(tick_alt);
	fight_tick(tick_alt ^ 1U);
	tick_alt ^= 1U;
	sounds_after_tick();

	switch (state) {
	case ST_READY:
		if (--timer == 0U) { state = ST_FIGHT; bub(0xFFU); }
		break;
	case ST_FIGHT:
		if (fight_hit_test(&h)) { award(&h); }
		else if (tsec == 0U) {
			/* time up: more points wins, then higher score; a complete tie restarts the bout */
			u8 a = (fgt[0].points != fgt[1].points) ? ((fgt[1].points > fgt[0].points) ? 1U : 0U)
			     : (fgt[0].score  != fgt[1].score)  ? ((fgt[1].score  > fgt[0].score)  ? 1U : 0U) : 0xFFU;
			if (a == 0xFFU) {
				fgt[0].points = fgt[1].points = 0U;
				tsec = (players == 1U) ? BOUT_TIME_1P : BOUT_TIME_2P; tfr = 30U;
				ready();
			} else {
				winner = a; bout_won = true;
				fgt[a].req = MOVE_VICTORY; fgt[a ^ 1U].req = MOVE_STAND;
				bub(a ? BUB_RED_WINS : BUB_WHITE_WINS);
				state = ST_POINT; timer = T_POINT; hud_dirty = true;
			}
		}
		break;
	case ST_POINT:
		if (--timer == 0U) {
			if (bout_won) {
				if ((players == 1U) && (winner == 1U)) {
					state = ST_OVER; timer = T_OVER; say(s_over, COL_RED); sfx(SFX_LOSE);
				} else {
					state = ST_WIN; timer = T_WIN;
				}
			} else {
				ready();
			}
		}
		break;
	case ST_WIN:
		if (tsec != 0U) {                /* time bonus: 100 points per second left */
			tsec --; fgt[winner].score ++; hud_dirty = true; sfx(SFX_BLIP);
			if (timer < 2U) { timer = 2U; }
		}
		if (--timer == 0U) {
			if (players == 1U) { level ++; }
			after_bout();
		}
		break;
	default: /* ST_OVER */
		if (--timer == 0U) { title(); }
		break;
	}
}

/* ------------------------------------------------------------ bonus rounds */
/* New code. Rules follow the original: the breaking round after the 4th bout
** won, the knife round after the 9th (one player), or a fixed order of bouts
** and bonus rounds in two-player mode; each human player takes the round in
** turn. Timings measured in 50 Hz C64 frames are converted to 60 Hz. */
#if HAVE_BONUS
enum { BR_READY, BR_WAIT, BR_CUE, BR_BREAK, BR_DONE, KN_READY, KN_FLY, KN_DONE };

static u8  bkind, bplayer, bstate, bwait, bcount, bdone, bsound;
static u16 bt;                         /* frame counter within the current stage */
static u16 bpad;                       /* pad state at the cue */
static u8  pj_on, pj_dir, pj_type, pj_speed, pj_h, pj_col, pj_anim, pj_left, pj_dodged;
static u16 pj_x;                       /* 8.8 fixed point, C64 multicolour pixels */
static u8  next_after_bonus;

static void bonus_player(void)
{
	u8 p = bplayer;
	fgt_vis = (u8)(1U << p);
	fight_place();
	fgt[p].fallen = 0U;
	bt = 0U;
	if (bkind == 4U) {
		fgt[p].x = 0x54U; fgt[p].face = 0U; fgt[p].frame = 0x34U;   /* poised, behind the bricks */
		bstate = BR_READY; bub(BUB_GET_READY);
	} else {
		fgt[p].x = 0x44U; fgt[p].face = p;
		pj_on = 0U; pj_dodged = 0U;
		pj_left = pgm_read_byte(&bonus_knife_count[klevel]);
		bstate = KN_READY; bub(BUB_GET_READY);
	}
	fgt_front = p;
}

static void bonus_begin(u8 kind, u8 next_stage)
{
	bkind = kind; bplayer = 0U; next_after_bonus = next_stage;
	state = ST_BONUS;
	bonus_player();
}

static void bonus_end_player(void)
{
	hud_dirty = true;
	if ((players == 2U) && (bplayer == 0U)) { bplayer = 1U; bonus_player(); return; }
	bub(0xFFU);
	new_stage(next_after_bonus);
}

/* knife hits: projectile shape mask against the fighter's frame mask (SPI) */
static bool pj_hits(void)
{
	fighter_t* f = &fgt[bplayer];
	ProjEntry const* e = &proj_table[((pj_type * 2U + pj_dir) * 4U + (pj_type ? 0U : pj_anim)) * 8U + pj_h];
	u8 sh = pgm_read_byte(&e->shape);
	u8 mr = pgm_read_byte(&proj_shape[sh][0]), h = pgm_read_byte(&proj_shape[sh][1]);
	u8 w  = pgm_read_byte(&proj_shape[sh][2]);
	u8 y0 = pgm_read_byte(&e->y0);
	s16 px = (s16)(pj_x >> 8) - 16 + pgm_read_byte(&e->x0);   /* left edge, C64 fat pixels */
	s16 fx = (s16)f->x - 16;                                   /* fighter box left */
	s16 d  = px - fx;
	u8 r;
	if ((d >= 40) || (d + w <= 0) || (f->frame >= 54U)) { return false; }
	for (r = 0U; r < h; r++) {
		u8 row = y0 + r, k;
		u32 pm = pgm_read_dword(&proj_mask[mr + r]);
		u32 a  = SPI_FIGHTER_MASKS + (u32)(f->frame) * FIGHTER_MASK_BYTES + (u32)(row) * 5U;
		u8 fb[5];
		if (row >= 96U) { break; }
		for (k = 0U; k < 5U; k++) { fb[k] = SpiRamReadU8((u8)((a + k) >> 16), (u16)(a + k)); }
		/* compare pixel columns c of the projectile with column c + d of the fighter */
		for (k = 0U; k < w; k++) {
			s16 c = d + k;
			if ((c < 0) || (c >= 40)) { continue; }
			if ((pm & (0x80000000UL >> k)) && (fb[c >> 3] & (0x80U >> (c & 7)))) { return true; }
		}
	}
	return false;
}

static void pj_spawn(void)
{
	u8 idx = (u8)(klevel * 4U + (ai_rand() & 3U));
	pj_type  = pgm_read_byte(&bonus_type_by_level[idx]);
	pj_speed = pgm_read_byte(&bonus_speed_by_level[idx]);
	pj_dir   = (pgm_read_byte(&bonus_dir_pattern[pj_dodged % sizeof(bonus_dir_pattern)]) ^ bplayer) & 1U;
	pj_x     = pj_dir ? (0xB0U << 8) : 0U;
	pj_h     = ai_rand() & 7U;
	pj_col   = ai_rand() & 3U;
	pj_anim  = 0U;
	pj_on    = 1U;
}

static void bonus_frame(void)
{
	fighter_t* f = &fgt[bplayer];
	u16 pad = ReadJoypad(bplayer) & (BTN_UP | BTN_DOWN | BTN_LEFT | BTN_RIGHT | BTN_A | BTN_B | BTN_X | BTN_Y);
	bt ++;
	nextras = 0U;

	switch (bstate) {
	/* ---------------- breaking round */
	case BR_READY:
		if (bt >= 150U) { bstate = BR_WAIT; bwait = (u8)(30U + (ai_rand() & 63U)); bt = 0U; bub(0xFFU); }
		break;
	case BR_WAIT:
		if (bt >= bwait) { bstate = BR_CUE; bt = 0U; bpad = pad; bub(BUB_GO); sfx(SFX_BLIP); }
		break;
	case BR_CUE: {
		u16 r50 = (u16)((bt * 5U) / 6U);           /* reaction in C64 frames */
		if (pad != bpad) {
			bcount = (r50 >= 40U) ? 1U : (u8)(10U - r50 / 4U);
			f->frame = 0x35U;                     /* strike */
			bub((u8)(BUB_BRICKS_1 + bcount - 1U));
			fgt[bplayer].score += (bcount == 10U) ? 20U : bcount;
			bdone = 0U; bsound = 0U; bstate = BR_BREAK; bt = 0U;
		} else if (r50 >= 100U) {
			bub(BUB_TOO_SLOW); sfx(SFX_LOSE); bstate = BR_DONE; bt = 0U;
		}
		break; }
	case BR_BREAK:
		if ((bdone < bcount) && (++bsound >= 6U)) { bsound = 0U; bdone ++; sfx(SFX_C64_2); }   /* the C64's break sample */
		if ((bdone == bcount) && (bt > (u16)(bcount * 6U + 50U))) {
			f->frame = 0x34U; if (bcount == 10U) { sfx(SFX_WIN); }
			bstate = BR_DONE; bt = 0U;
		}
		break;
	case BR_DONE:
		if (bt >= 110U) { bonus_end_player(); return; }
		break;

	/* ---------------- knife round */
	case KN_READY:
		if (bt >= 96U) { bstate = KN_FLY; bt = 0U; bub(0xFFU); }
		break;
	case KN_FLY:
		if (!pj_on && (pj_left != 0U)) { pj_spawn(); }
		if (pj_on) {
			u16 step = (u16)(pj_speed) * 213U;   /* speed per C64 frame -> per 60 Hz frame */
			if (pj_dir) { pj_x -= step; } else { pj_x += step; }
			pj_anim = (pj_anim + 1U) & 3U;
			if (pj_hits()) {
				fight_start_move(bplayer, (pj_dir ^ f->face) ? 17U : 18U); f->req = f->move;
				bub(BUB_OUCH);
				pj_on = 0U; f->score += pj_dodged; bstate = KN_DONE; bt = 0U;
			} else if ((pj_dir && ((pj_x >> 8) < 3U)) || (!pj_dir && ((pj_x >> 8) >= 0xD0U))) {
				pj_on = 0U; pj_dodged ++; pj_left --;
				if (pj_left == 0U) {
					f->score += pj_dodged; bub(BUB_WELL_DONE); sfx(SFX_WIN); bstate = KN_DONE; bt = 0U;
				}
			}
		}
		break;
	default: /* KN_DONE */
		if (bt >= 130U) { bonus_end_player(); return; }
		break;
	}

	/* sprites for this frame */
	if (bkind == 4U) {                     /* the crack grows down one brick per break */
		u8 n = (bstate == BR_BREAK || bstate == BR_DONE) ? bdone : 0U;
		extras_add((BonusTile const*)pgm_read_word(&brick_tiles[n]), pgm_read_byte(&brick_len[n]), BRICK_X, BRICK_Y);
	}
	if (pj_on && (bkind == 5U)) {
		ProjEntry const* e = &proj_table[((pj_type * 2U + pj_dir) * 4U + (pj_type ? 0U : pj_anim)) * 8U + pj_h];
		u8 v = pgm_read_byte(&e->var[pj_col]);
		extras_add((BonusTile const*)pgm_read_word(&proj_var[v]), pgm_read_byte(&proj_var_len[v]),
		           (s16)XOFF + (s16)(pj_x >> 8) - 16 + pgm_read_byte(&e->x0), pgm_read_byte(&e->y0));
	}
	if (bubble != 0xFFU) {
		extras_add((BonusTile const*)pgm_read_word(&bub_tiles[bubble]), pgm_read_byte(&bub_len[bubble]),
		           BUBBLE_X, BUBBLE_Y);
	}
	redraw = true;
}

/* knife round: the fighter moves on the normal step clock */
static void bonus_step(void)
{
	if ((bkind == 5U) && (bstate == KN_FLY)) { fight_input(bplayer, pad_latch[bplayer]); }
	if (bkind == 5U) { fight_tick(bplayer); c64_sound(bplayer, SND_MODE_BONUS); }
}
#endif

/* After a bout is decided: the original's running order. */
static void after_bout(void)
{
	u8 next = (u8)((stage + 1U) % STAGE_COUNT), ph = 1U;
	bouts ++;
	if (players == 2U) {
#if HAVE_BONUS
		ph = pgm_read_byte(&bonus_twoplayer_order[bouts % sizeof(bonus_twoplayer_order)]);
#endif
	} else {
		wins ++;
		if (wins == 4U) { ph = 4U; }
		else if (wins > 8U) { wins = 0U; ph = 5U; if ((bouts >= 9U) && (klevel < 2U)) { klevel ++; } }
	}
#if HAVE_BONUS
	if ((ph == 4U) || (ph == 5U)) { bonus_begin(ph, next); return; }
#endif
	new_stage(next);
}

/* --------------------------------------------------------------- timing */

/* The kernel counts hsync lines down from SYNC_HSYNC_PULSES (sync_phase 1);
** the vsync flag only comes when that count runs out, well after the last
** rendered line. Starting the per-frame work as soon as rendering has
** finished gives it the whole blank period. */
extern volatile u8 sync_pulse;
extern volatile u8 sync_phase;

#define FIRST_LINE    32U
#define RENDER_LINES 192U
#define DONE_PULSE   (u8)(SYNC_HSYNC_PULSES - (FIRST_LINE + RENDER_LINES + 2U))

static void wait_render_done(void)
{
	while (!((sync_phase != 0U) && (sync_pulse > (u8)(DONE_PULSE + 40U)))) { }   /* in the next frame */
	while (!((sync_phase != 0U) && (sync_pulse <= DONE_PULSE))) { }             /* past its last line */
}

#ifdef DEBUG_TIMING
/* counts sprite rows finished after the beam reached them */
static u8 late_rows;
static void check_row(u8 dy)
{
	u8 dl = (u8)(SYNC_HSYNC_PULSES - (FIRST_LINE + 96U + dy));   /* pulse value when row dy starts */
	if ((sync_phase != 0U) && (sync_pulse < dl) && (sync_pulse > DONE_PULSE)) { late_rows ++; }
}
#endif

/* ------------------------------------------------------------------ main */

int main(void)
{
	u8 i, err, clk = 0U;

	m74_config = 0U;

	SetRenderingParameters(FIRST_LINE, RENDER_LINES);   /* rows 0-23; the C64 credit row is left out */
	m74_rows   = (u16)(&rowsel[0]);
	m74_vaddr  = (u16)(&row_table[0]);
	m74_rtbase = RT_BASE;
	m74_rtmax  = RT_MAX;

	m4row.config = 4U;
	for (i = 0U; i < 96U; i++) { m4row.data[i] = pgm_read_byte(&bitmap_left[i]); }

	err = load_spi_image();
	if (err != 0U) { show_error(err); }

	InitMusicPlayer(sfx_patches);
	fight_init();
	fgt[0].score = fgt[1].score = 0U;
	title();
	hud_redraw();
	M74_VramRestore();
	draw_both();
	m74_config |= M74_CFG_ENABLE;
	while (1) {
		wait_render_done();
		ClearVsyncFlag();
		/* Only one SPI-heavy job per vblank: HUD text, or a sprite redraw.
		** Sprites keep their RAM tiles on frames without a redraw. */
		if (hud_dirty)        { hud_redraw(); }
		else if (time_dirty)  { hud_time(); }
		else if (redraw) { M74_VramRestore(); draw_both(); redraw = false; }
#ifdef DEBUG_TIMING
		{ static u8 t; if ((++t & 31U) == 0U) { char b[12]; b[0]='L'; b[1]=(char)('0'+(late_rows>9U?9U:late_rows)); b[2]=' '; b[3]='S'; b[4]=(char)('0'+state);
		  b[5]=' '; b[6]=(char)('0'+fgt[0].points); b[7]=(char)('0'+fgt[1].points); b[8]=' '; b[9]=(char)('A'+(fgt[0].move>25U?25U:fgt[0].move)); b[10]=(char)('A'+(fgt[1].move>25U?25U:fgt[1].move)); b[11]=0; hud_text(14U, 9U, b, 7U); } }
#endif
		pad_latch[0] |= ReadJoypad(0U);
		pad_latch[1] |= ReadJoypad(1U);

		c64_sound_frame();
		if (((state == ST_READY) || (state == ST_FIGHT) || (state == ST_POINT)) && (tsec != 0U)) {
			if (--tfr == 0U) { tfr = 60U; tsec --; time_dirty = true; }
		}
		if (++clk >= STEP_FRAMES) { clk = 0U; game_step(); redraw = true; }
#if HAVE_BONUS
		if (state == ST_BONUS) { bonus_frame(); }
		else if (redraw) {
			nextras = 0U;
			if (bubble != 0xFFU) {
				extras_add((BonusTile const*)pgm_read_word(&bub_tiles[bubble]), pgm_read_byte(&bub_len[bubble]),
				           BUBBLE_X, BUBBLE_Y);
			}
		}
#endif
	}
}
