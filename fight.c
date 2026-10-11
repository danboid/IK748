/*
 * International Karate port - fight rules
 *
 * New code for the Uzebox. The data tables come from ik_moves.h, which
 * export_moves.py extracts from your own copy of the game.
 */
#include "fight.h"
#include "ik_moves.h"

#define BOX_W      0x24U        /* fighter box width */
#define ARENA_L    0x10U
#define ARENA_R    0xAEU

fighter_t fgt[2];
u8        fgt_front;

static u8 hit_alt;

/* ------------------------------------------------------------- helpers */

static u8 tb(u8 const* t, u16 i) { return pgm_read_byte(&t[i]); }

/* Relative position code of fighter p against the other one:
** bit 2 = p's centre is right of (or level with) the other's,
** bit 1 = p faces left, bit 0 = other faces left. Also returns the
** distance between centres in units of 4 pixels. */
u8 fight_rel(u8 p, u8* dist)
{
	fighter_t* a = &fgt[p];
	fighter_t* b = &fgt[p ^ 1U];
	u8 ca = a->face ? (u8)(a->x + BOX_W - 13U) : (u8)(a->x + 12U);
	u8 cb = b->face ? (u8)(b->x + BOX_W - 12U) : (u8)(b->x + 12U);
	s8 d  = (s8)(u8)(ca - cb);
	u8 code = (d >= 0) ? 4U : 0U;

	code |= (u8)(a->face << 1) | b->face;
	if (dist != 0) {
		u8 ad = (d < 0) ? (u8)(-d) : (u8)(d);
		*dist = ad >> 2;
	}
	return code;
}

/* Move by this step's distance (dir 0 = right) and keep the fighter's
** visible extent inside the arena. */
static void apply_dx(fighter_t* f, u8 dir)
{
	u8 dx = tb(st_dx, f->step);
	u8 w  = tb(fr_width, (f->frame < 54U) ? f->frame : 0U);
	u8 l, r;

	if (dir != 0U) { f->x -= dx; r = (u8)(f->x + BOX_W); l = (u8)(r - w); }
	else           { f->x += dx; l = f->x;                r = (u8)(l + w); }

	if (l <= ARENA_L) {
		if (f->face == 0U) { f->x = ARENA_L; }
		else {
			u8 t = (u8)(ARENA_L + w);
			f->x = (t >= BOX_W) ? (u8)(t - BOX_W) : 0U;
		}
	} else if (r > ARENA_R) {
		f->x = (f->face == 0U) ? (u8)(ARENA_R - w) : (u8)(ARENA_R - BOX_W);
	}
	if (f->x >= 0xF0U) { f->x = 0U; }
}

static void start_move(fighter_t* f, u8 m)
{
	f->move   = m;
	f->step   = tb(mv_bound, m);
	f->next   = f->step;
	f->held   = 1U;
	f->rev    = 0U;
	f->holdpt = 0U;
	f->hold   = 0U;
	f->turned = 0U;
}

/* ------------------------------------------------------------- public */

void fight_start_move(u8 i, u8 m) { start_move(&fgt[i], m); }

void fight_place(void)
{
	u8 i;
	for (i = 0U; i < 2U; i++) {
		fighter_t* f = &fgt[i];
		f->x      = (i == 0U) ? 0x30U : 0x70U;
		f->face   = i;
		f->fallen = 0U;
		f->req    = MOVE_STAND;
		f->atk    = 0U;
		f->frame  = 0U;
		start_move(f, MOVE_STAND);
	}
	fgt_front = 0U;
}

void fight_input(u8 i, u16 pad)
{
	fighter_t* f = &fgt[i];
	fighter_t* o = &fgt[i ^ 1U];
	u8 idx  = 0x0FU;              /* C64 joystick: bit clear = pressed */
	u8 base = (f->face ^ f->turned) ? 32U : 0U;
	u8 dist;

	if (pad & BTN_UP)    { idx &= (u8)(~1U); }
	if (pad & BTN_DOWN)  { idx &= (u8)(~2U); }
	if (pad & BTN_LEFT)  { idx &= (u8)(~4U); }
	if (pad & BTN_RIGHT) { idx &= (u8)(~8U); }
	if (pad & (BTN_A | BTN_B | BTN_X | BTN_Y)) { idx |= 0x10U; }

	/* Opponent striking at close range: pulling away becomes a block */
	if ((f->hold == 0U) && (o->atk != 0U)) {
		u8 code = fight_rel(i ^ 1U, &dist);
		if ((tb(block_ok, code) != 0U) && (dist < 8U)) {
			base = f->face ? 96U : 64U;
		}
	}
	f->req = tb(joy_map, (u16)(base) + idx);
}

void fight_tick(u8 i)
{
	fighter_t* f = &fgt[i];
	u8 fl;

	if (f->fallen != 0U) { return; }

top:
	if (f->req != f->move) { f->held = 0U; }
	if ((f->held == 0U) && (f->holdpt != 0U)) { f->rev = 1U; }

	if (f->rev != 0U) {
		/* play back towards the start of the move */
		f->step --;
		if (f->step >= tb(mv_bound, f->move)) {
			f->frame = tb(st_frame, f->step);
			apply_dx(f, f->rev ^ f->face);
			return;
		}
		goto reselect;
	}

	f->step = f->next;
	if (f->move == MOVE_STAND) { start_move(f, f->req); }
	goto check;

reselect:
	start_move(f, f->req);
check:
	while (f->step >= tb(mv_bound, f->move + 1U)) { start_move(f, f->req); }

	f->frame = tb(st_frame, f->step);
	if (f->frame >= 0x36U) { f->frame = 0U; }
	fl = tb(st_flags, f->step);
	f->sflags = fl;
	f->holdpt = fl & 0x04U;
	f->atk    = fl & 0x40U;

	if (fl & 0x08U) {                         /* chain / hold point */
		if (f->req == f->move) {
			if (f->hold < 0x80U) {
				if (f->hold == 0U) { apply_dx(f, f->face); }
				f->hold ++;
			}
			return;                           /* stay on this step */
		}
		if (f->hold != 0U) {
			f->hold = 0U; f->rev = 0U; f->holdpt = 0U;
			f->next = (u8)(f->step + 1U);
			goto top;
		}
	}

	if ((fl & 0x10U) && (f->held == 0U)) {    /* interruptible step */
		if (f->move == 3U) { goto reselect; }
		if (f->move == 7U) { f->x += f->face ? 3U : (u8)(-3); goto reselect; }
		if (f->req != 0U)  { goto reselect; }
	}

	if (fl & 0x02U) { f->face ^= 1U; f->turned = 1U; }
	if (fl & 0x01U) { fgt_front = i; }
	if (fl & 0x20U) { f->fallen = 1U; }
	apply_dx(f, f->face);
	f->next = (u8)(f->step + 1U);
}

/* Would strike y by fighter a, standing at ax and facing aface, land on the other fighter as he is now?
** Returns 0 = miss, 1 = half point, 2 = full point; fills h when it lands. */
u8 fight_strike_eval(u8 a, u8 ax, u8 aface, u8 y, hit_t* h)
{
	u8 v, cls, code, outer, inner, sx, z, off, vx, d, rel, ox, of;
	bool full;

	v   = a ^ 1U;
	cls = tb(pose_class, (fgt[v].frame < 54U) ? fgt[v].frame : 0U);
	if (cls & 0x80U) { return 0U; }               /* victim can't be hit now */
	if ((cls == 0x18U) && (y == 3U)) { cls = 0x1AU; }
	ox = fgt[a].x; fgt[a].x = ax;                 /* evaluate from ax / aface */
	of = fgt[a].face; fgt[a].face = aface;
	code = fight_rel(a, 0);
	fgt[a].x = ox; fgt[a].face = of;
	rel  = code & 3U;
	if ((cls == 0x13U) && ((code == 0U) || (code == 7U))) { cls = 0U; }

	outer = tb(sk_outer, y);
	inner = tb(sk_inner, y);
	off   = tb(sk_reach, y);
	sx    = aface ? (u8)(ax + BOX_W - off) : (u8)(ax + off);

	for (z = 0U; z < 6U; z++) {
		if ((tb(zone_bit, z) & tb(sk_height, y)) == 0U) { continue; }
		off = tb(zone_off, (u16)(cls) * 6U + z);
		if (off & 0x80U) { continue; }
		vx = fgt[v].face ? (u8)(fgt[v].x + BOX_W - off) : (u8)(fgt[v].x + off);
		switch (rel) {
			case 1U:  d = (u8)(sx - vx);         break;
			case 0U:  d = (u8)(sx - vx + outer); break;
			case 2U:  d = (u8)(vx - sx);         break;
			default:  d = (u8)(vx - sx + outer); break;
		}
		if ((d & 0x80U) || (d > outer)) { continue; }

		full = (d != outer) && (d < inner);
		if (h != 0) {
			u8 bcd = tb(full ? sk_score_full : sk_score_half, y);
			h->attacker = a;
			h->full     = full;
			h->react    = tb(sk_react, (u8)(y * 4U + rel));
			h->score    = (u8)((bcd >> 4) * 10U + (bcd & 0x0FU));
			h->call     = tb(full ? sk_call_full : sk_call_half, y);
		}
		return full ? 2U : 1U;
	}
	return 0U;
}

bool fight_hit_test(hit_t* h)
{
	u8 k, a;
	s8 y;

	hit_alt ^= 1U;
	for (k = 0U; k < 2U; k++) {
		a = hit_alt ^ k;
		for (y = 8; y >= 0; y--) {
			if (fgt[a].frame == tb(sk_frame, (u8)(y))) { break; }
		}
		if ((y >= 0) && (fgt[a].hold < 2U)) {
			return fight_strike_eval(a, fgt[a].x, fgt[a].face, (u8)(y), h) != 0U;
		}
	}
	return false;
}

/* Attack catalogue for the computer player: for each of the 16 joystick moves
** that contains a strike frame, the strike, how many steps until it and how
** far the fighter travels by then. */
atk_info_t atk_list[16];
u8         atk_count;

void fight_init(void)
{
	u8 m, s, e, k, y, turned;
	s8 dx, dx2;
	atk_count = 0U;
	for (m = 1U; m <= 16U; m++) {
		s = tb(mv_bound, m); e = tb(mv_bound, m + 1U); dx = 0; dx2 = 0; turned = 0U;
		for (k = s; k < e; k++) {
			/* a turn takes effect on its own step, before that step's movement */
			if (tb(st_flags, k) & 0x02U) { turned ^= 1U; }
			if (turned) { dx2 = (s8)(dx2 + (s8)tb(st_dx, k)); }
			else        { dx  = (s8)(dx  + (s8)tb(st_dx, k)); }
			for (y = 0U; y < 8U; y++) {
				if (tb(st_frame, k) == tb(sk_frame, y)) { break; }
			}
			if (y < 8U) {
				atk_info_t* a = &atk_list[atk_count];
				a->move = m; a->strike = y; a->steps = (u8)(k - s);
				a->dx = dx; a->dx2 = dx2; a->turn = turned;
				atk_count ++;
				break;
			}
		}
	}
}

bool fight_is_strike_frame(u8 frame)
{
	u8 y;
	for (y = 0U; y < 8U; y++) { if (frame == tb(sk_frame, y)) { return true; } }
	return false;
}

s8 fight_move_dx(u8 m)
{
	u8 k; s8 dx = 0;
	for (k = tb(mv_bound, m); k < tb(mv_bound, m + 1U); k++) { dx = (s8)(dx + (s8)tb(st_dx, k)); }
	return dx;
}
