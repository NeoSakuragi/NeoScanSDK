# Krauser review (Bruno, 2026-10-08) — answers from review-krauser on the VPS

- atk_a_far: Drop — "Too weak "
- atk_c_close: Keep — "Could be a good starter or mid "
- atk_d_close: Keep
- throw-back: Keep
- atk_c_far: Keep — "Love this, could be a starter, but almost over powered "
- atk_b_far: Drop — "Too weak feeling "
- sp-623b: Keep
- atk_d_far: Keep
- sp-623d: Keep
- body_toss: Keep
- atk_b_close: Drop
- atk_a_close: Keep — "Too choppy for a heavy hitter "
- atk_c_crouch: Keep — "Perfect "
- atk_d_crouch: Keep — "Good for crumpling "
- sp-41236b: Keep
- atk_b_crouch: Drop — "Not visually appealing "
- sp-236d: Keep — "The "dragon " move "
- atk_a_crouch: Drop
- atk_d_jump: Keep
- atk_b_jump: Drop
- atk_c_jump: Keep
- atk_cd_jump: Keep
- atk_a_jump: Keep
- archetype: Keep
- chain: Drop — "Starter is missing range "
- fin-neutral: None — "Too short, nothing under 3 hits "
- fin-forward: Drop — "Too short "
- fin-up: Drop — "The sequence is good but too short "
- fin-down: Keep — "Nice flow but too short"
- fin-back: Keep
- general: None — "There is a command grab with a jumping motion - would be interesting to see how to integrate this as a custom move / grab later "

Interpretation:
- Starter must have range (my close D starter lacked it): far C ("love this, could be a starter, almost overpowered"), close C (starter or mid).
- Crouch C "perfect"; crouch D good for crumpling (down finisher).
- Dropped: far A, far B ("too weak"), close B, crouch A, crouch B, jump B, my chain, the forward and up finishers.
- Close A kept but "too choppy for a heavy hitter".
- Every finisher clip "too short": nothing under 3 hits (same as Terry) — follow-up krauser2 asks how many hits a heavy chain has.
- 236D is "the dragon move".
- Later: Krauser's command grab with a jumping motion, as a custom move / grab (not a command-grab input).

## Follow-up krauser2 (Bruno, 2026-10-08) — answers in /data/brawler/feedback/decisions/krauser2.json, applied in revamp 3b

- hits: "3 hits in all, the finisher being the 3rd" (the heavy archetype's length stays 3).
- chain: "close C > far D > crouch C".
- neutral finisher: "far D". forward: "far C". up: note "Close D (points up)". down: "crouch D (crumple)". back: his throw.

Applied (game.json roster krauser, written by tools/brawler/chain_save.py `entry`, the chain tool's save path):
`chain.links` [atk_c_close, atk_d_far]; finishers neutral atk_c_crouch (knockdown), forward atk_c_far (push: blowback),
up atk_d_close (the launcher, `launcher: up`), down atk_d_crouch (`down: sweep`: a trip, the engine's instant knockdown;
there is no separate crumple reaction), back = the back throw (the chain core's rule). Damage 7 / 11 / 9 = 27 (the heavy
total), hit-stop 6 / 9 / 12. His routes now hold only close C, far D, crouch C / D, far C, close D, the jump C / D /
C+D, the body toss and the throws: none of the pieces he dropped (far A, far B, close B, crouch A, crouch B, jump B).

**Conflict, to ask Bruno later:** he chose the chain close C > far D > crouch C (crouch C = the 3rd hit = the neutral
finisher) and also answered neutral finisher = far D, which is the chain's 2nd link. Applied: the chain as chosen (the
neutral finisher crouch C); far D as the neutral finisher would mean far D twice in a row. Options for the question:
keep crouch C as the neutral finisher, or swap to close C > crouch C > far D.

Proof (our emulator, /data/tmp/rv3b/out): tools/brawler/rv3b_proof.py `chain krauser` (every finisher, both facings,
chain_krauser.png): every link hits, every finisher plays its move with its reaction (up: the victim to 134 px), 27
damage; back: the throw, P1 untouchable through it, the victim behind. Scenarios rv3b-krauser-* (scenarios.json).
