#!/bin/bash
# Enemies tab proof (our emulator's core only, never MAME): YAKUZA edited IN THE PAGE (headless Chrome: life 90, grab_plan
# 8, custom colour 3's red to 31), tested in the page (its own wasm core: the pack + lab req 3, then ramtrace.STAGE_SCRIPT)
# and on the desktop core (ramtrace.py enemy) with the page's pack: tick-keyed traces compared, the palette RAM of the
# enemy (slots 32-39) against the page's swatches; the page's edited enemies merged into game.json and packed by
# build_tables.py = the page's pack; unedited: the page's pack = build_tables.py pack byte for byte.
#   enemy_proof.sh SITE_DIR GAME_DIR OUT_DIR        (SITE_DIR: make_site.py output with core.js / core.wasm)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); SITE=$(cd "$1" && pwd); GAME=$(cd "$2" && pwd); OUT=$3; T=$HERE/../ramtrace.py
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SCR=$(python3 -c "import sys; sys.path.insert(0, '$HERE/..'); import ramtrace; print(ramtrace.STAGE_SCRIPT)")
EN=$(python3 -c "import json; print([e['name'] for e in json.load(open('$GAME/game.json'))['enemies']].index('YAKUZA'))")
(cd "$SITE" && exec python3 -m http.server 8767 > /dev/null 2>&1) & SRV=$!; trap "kill $SRV" EXIT; sleep 1
SET="(sel, v) => { const i = document.querySelector(sel); i.value = v; i.dispatchEvent(new Event('change')); }"
cat > "$OUT/steps.json" <<J
[{"wait": 6000},
 {"eval": "localStorage.clear(); window.labTab('enemies'); enemiesTab.reset(); enemiesTab.select('YAKUZA'); Array.from(enemiesTab.pack().bytes)", "save": "$OUT/pack_page_today.json"},
 {"eval": "(() => { const set = $SET; set('#enLife', 90); set('input[type=number][data-k=grab_plan]', 8); document.querySelectorAll('.sw')[3].click(); set('input[type=number][data-c=R]', 31); return enemiesTab.enemies.find(e => e.name === 'YAKUZA'); })()", "save": "$OUT/yakuza_page.json"},
 {"wait": 500},
 {"shot": "$OUT/tab_edited.png", "full": true},
 {"eval": "Array.from(enemiesTab.pack().bytes)", "save": "$OUT/pack_page_edit.json"},
 {"eval": "({ pals: enemiesTab.pals(), enemies: enemiesTab.enemies, files: enemiesTab.files })", "save": "$OUT/page_enemies.json"},
 {"eval": "(() => { const C = chainlab, L = C.lab, script = '$SCR'; if (!C.paused) C.togglePause(); L.core._wc_reset(); L.setPad(0, ''); L.setPad(1, ''); L.run(400); enemiesTab.test(); if (!C.paused) C.togglePause(); const trace = [L.ramSnap()], ticks = [L.gameTicks()]; const parts = script.split(',').map(p => p.split(':')); while (trace.length < 1500) for (const [n, k] of parts) for (let i = 0; i < Number(n) && trace.length < 1500; i++) { L.setPad(0, k.replace('-', '')); L.run(1); trace.push(L.ramSnap()); ticks.push(L.gameTicks()); } C.draw(); return { trace, ticks, pack_status: L.packStatus(), palram: [...Array(8)].map((_, i) => L.palette(32 + i)) }; })()", "save": "$OUT/page_edit.json"},
 {"wait": 300},
 {"shot": "$OUT/page_game_after_test.png"},
 {"eval": "localStorage.clear(); enemiesTab.reset(); 'reset'"}]
J
node "$HERE/headless.js" http://localhost:8767/game.html "$OUT/steps.json" | grep -v '^eval: \[' || true
for p in today edit; do python3 -c "import json, sys; open(sys.argv[2], 'wb').write(bytes(json.load(open(sys.argv[1]))))" "$OUT/pack_page_$p.json" "$OUT/pack_page_$p.bin"; done
python3 "$HERE/../build_tables.py" pack "$GAME/game.json" "$GAME/build" "$OUT/pack_py.bin"
echo "== unedited: the page's pack vs build_tables.py pack"; cmp "$OUT/pack_page_today.bin" "$OUT/pack_py.bin" && echo "identical ($(stat -c %s "$OUT/pack_py.bin") bytes)"
python3 -c "
import json, sys, os, tempfile
sys.path.insert(0, '$HERE/..'); import build_tables as BT
g = json.load(open('$GAME/game.json')); pg = json.load(open('$OUT/page_enemies.json'))
g['enemies'] = pg['enemies']
for p, t in pg['files'].items(): assert os.path.exists(os.path.join(BT.REPO, p)), p   # no new routes file in this edit
open('$OUT/pack_py_edit.bin', 'wb').write(BT.pack(g, '$GAME/build'))
y = next(e for e in g['enemies'] if e['name'] == 'YAKUZA'); print('YAKUZA as edited in the page:', json.dumps(y))
"
echo "== edited: the page's enemies merged into game.json, build_tables.py pack vs the page's pack"; cmp "$OUT/pack_page_edit.bin" "$OUT/pack_py_edit.bin" && echo "identical ($(stat -c %s "$OUT/pack_py_edit.bin") bytes)"
python3 "$T" "$GAME" enemy "$OUT/desk_edit.json" --enemy $EN --pack "$OUT/pack_page_edit.bin" --frames 1500 > /dev/null
echo "== edited, page vs desktop core (tick-keyed)"; python3 "$T" --diff "$OUT/page_edit.json" "$OUT/desk_edit.json" --from-stage
python3 "$T" "$GAME" enemy "$OUT/desk_rom.json" --enemy $EN --frames 1500 > /dev/null
echo "== edited vs the ROM's YAKUZA (must differ)"; python3 "$T" --diff "$OUT/desk_edit.json" "$OUT/desk_rom.json" --from-stage | head -1 || true
python3 -c "
import json
pg, dk, en = json.load(open('$OUT/page_edit.json')), json.load(open('$OUT/desk_edit.json')), json.load(open('$OUT/page_enemies.json'))
n = len(en['pals']); h = lambda p: ' '.join('%04X' % w for w in p)
print('== palette RAM: page core vs desktop core, slots 32-39:', 'identical' if pg['palram'] == dk['palram'] else 'DIFFER')
print('== palette RAM (%d palettes) vs the page swatches:' % n, 'identical' if pg['palram'][:n] == en['pals'] else 'DIFFER')
print('   palette 0 in the game :', h(dk['palram'][0])); print('   palette 0 swatches    :', h(en['pals'][0]))
print('   pack status page / desktop:', pg['pack_status'])
"
