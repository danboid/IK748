/*
 * International Karate port - computer opponent
 *
 * Original logic for the Uzebox. It uses the same strike geometry as the
 * referee (fight_strike_eval) to judge, from where it would be standing at
 * the moment of the strike, which of its attacks would land right now.
 */
#include "ai.h"
#include "fight.h"

static u8  lvl, delay, rng = 0x5AU, rng2 = 0xC3U;
static u8  fwd_move, back_move;
static u8  cur;                   /* move the AI is currently requesting (0 = none) */
static u8  hold;                  /* ticks left to keep requesting it */
static u8  is_atk, seen;

u8 ai_rand(void)
{
	/* small xorshift-style generator */
	rng ^= (u8)(rng << 3); rng ^= (u8)(rng >> 5); rng ^= rng2; rng2 += 0x3DU;
	return rng;
}

void ai_reset(u8 level)
{
	lvl   = (level > 7U) ? 7U : level;
	delay = 8U;
	cur   = 0U; hold = 0U;
	/* which walk goes forward: the one whose steps carry the fighter towards its facing */
	fwd_move  = (fight_move_dx(3U) > 0) ? 3U : 7U;
	back_move = (fwd_move == 3U) ? 7U : 3U;
}

static u8 react_ticks(void) { return (u8)((lvl >= 3U) ? 0U : (3U - lvl)); }   /* 3 .. 0 */
static u8 chance(u8 base, u8 per) { u16 c = (u16)base + (u16)per * lvl; return (c > 240U) ? 240U : (u8)c; }

static u8 pick(u8 m, u8 ticks, u8 attack) { cur = m; hold = ticks; is_atk = attack; seen = 0U; return m; }

u8 ai_think(u8 me)
{
	fighter_t* f = &fgt[me];
	fighter_t* o = &fgt[me ^ 1U];
	u8 dist, code, i, best = 0U, bestv = 0U, nfit = 0U;

	if (f->fallen) { return 0U; }

	/* keep requesting the chosen move for a while: attacks until the strike
	** frame has been shown (then let go so held kicks retract), others for a
	** few ticks */
	if (cur != 0U) {
		if (is_atk) {
			if (seen) { cur = 0U; return 0U; }
			if ((f->move == cur) && fight_is_strike_frame(f->frame)) { seen = 1U; }
		}
		if (hold != 0U) { hold --; return cur; }
		cur = 0U;
	}

	if (delay != 0U) { delay --; return 0U; }
	delay = react_ticks();

	code = fight_rel(me, &dist);

	/* opponent striking close by: block sometimes */
	if (o->atk && (dist < 8U) && (ai_rand() < chance(40U, 22U))) {
		delay = 1U; return pick(MOVE_BLOCK, 3U, 0U);
	}

	/* attacks that would land, judged from where we'd stand and which way we'd
	** face at the moment of the strike (some moves turn on the way) */
	for (i = 0U; i < atk_count; i++) {
		atk_info_t const* a = &atk_list[i];
		u8  face2 = f->face ^ a->turn;
		s16 ax = (s16)f->x;
		u8 r;
		ax += f->face ? -(s16)a->dx : (s16)a->dx;
		ax += face2   ? -(s16)a->dx2 : (s16)a->dx2;
		if ((ax < 0) || (ax > 0xC0)) { continue; }
		r = fight_strike_eval(me, (u8)ax, face2, a->strike, 0);
		if (r != 0U) {
			u8 v = (u8)(r * 64U + (ai_rand() & 63U));   /* prefer full points, random tie-break */
			if (v > bestv) { bestv = v; best = a->move; }
			nfit ++;
		}
	}
	if ((nfit != 0U) && (ai_rand() < chance(110U, 20U))) { return pick(best, 12U, 1U); }

	/* opponent behind us and nothing to throw: turn round */
	if (((code >> 2) & 1U) != f->face) { return pick(MOVE_TURN, 2U, 0U); }

	/* otherwise manoeuvre */
	if (dist > 6U)  { return pick(fwd_move, (u8)((dist > 10U) ? 4U : 1U), 0U); }
	if (dist < 2U)  { return pick(back_move, 2U, 0U); }
	if (ai_rand() < chance(50U, 10U)) {
		/* probe with a random attack now and then */
		if ((atk_count != 0U) && (ai_rand() & 1U)) { return pick(atk_list[ai_rand() % atk_count].move, 12U, 1U); }
		return pick(fwd_move, 2U, 0U);
	}
	return 0U;
}
