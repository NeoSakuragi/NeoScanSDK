#!/bin/bash
# Characters tab proof (our emulator's core only, never MAME): Terry's up+D remapped IN THE PAGE (headless Chrome) from
# 214D to 426D, tested in the page (its own wasm core: the pack + lab req 1 against the dummy, then ramtrace.CHAR_SCRIPT:
# up+D, D, forward+D, down+D, up+D) and on the desktop core (ramtrace.py lab) with the page's pack: tick-keyed traces
# compared; the page's roster merged into game.json and packed by build_tables.py = the page's pack; unedited: the page's
# pack = build_tables.py pack byte for byte; the edit must differ from the ROM's mapping. Screenshots of the tab.
#   char_proof.sh SITE_DIR GAME_DIR OUT_DIR        (SITE_DIR: make_site.py output with core.js / core.wasm)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); SITE=$(cd "$1" && pwd); GAME=$(cd "$2" && pwd); OUT=$3; T=$HERE/../ramtrace.py
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SCR=$(python3 -c "import sys; sys.path.insert(0, '$HERE/..'); import ramtrace; print(ramtrace.CHAR_SCRIPT)")
NF=$(python3 -c "print(1 + sum(int(p.split(':')[0]) for p in '$SCR'.split(',')))")
read F D <<< $(python3 -c "import json; n = [r['name'] for r in json.load(open('$GAME/game.json'))['roster']]; print(n.index('terry'), n.index('ryo'))")
(cd "$SITE" && exec python3 -m http.server 8768 > /dev/null 2>&1) & SRV=$!; trap "kill $SRV" EXIT; sleep 1
cat > "$OUT/steps.json" <<J
[{"wait": 6000},
 {"eval": "localStorage.clear(); window.labTab('chars'); charsTab.reset(); enemiesTab.reset(); charsTab.select('terry'); Array.from(stagesTab.pack().bytes)", "save": "$OUT/pack_page_today.json"},
 {"wait": 500},
 {"shot": "$OUT/tab_terry.png", "full": true},
 {"eval": "(() => { const r = charsTab.roster; r[$F].specials.uD = '426D'; charsTab.roster = r; charsTab.dummy = $D; return charsTab.roster[$F]; })()", "save": "$OUT/terry_page.json"},
 {"eval": "Array.from(stagesTab.pack().bytes)", "save": "$OUT/pack_page_edit.json"},
 {"eval": "charsTab.roster", "save": "$OUT/page_roster.json"},
 {"eval": "(() => { const C = chainlab, L = C.lab, script = '$SCR'; if (!C.paused) C.togglePause(); L.core._wc_reset(); L.setPad(0, ''); L.setPad(1, ''); L.run(400); charsTab.test(); if (!C.paused) C.togglePause(); const trace = [L.ramSnap()], ticks = [L.gameTicks()]; for (const [n, k] of script.split(',').map(p => p.split(':'))) for (let i = 0; i < Number(n); i++) { L.setPad(0, k.replace('-', '')); L.run(1); trace.push(L.ramSnap()); ticks.push(L.gameTicks()); } C.draw(); return { trace, ticks, pack_status: L.packStatus() }; })()", "save": "$OUT/page_edit.json"},
 {"wait": 300},
 {"shot": "$OUT/tab_edited.png", "full": true},
 {"eval": "document.querySelectorAll('#charcol button').forEach(b => { if (b.textContent === 'Change…' && !window._o) { window._o = 1; } }); [...document.querySelectorAll('#charcol button')].filter(b => b.textContent === 'Change…')[3].click(); 'opened'"},
 {"wait": 500},
 {"shot": "$OUT/picker_terry_upD.png"},
 {"eval": "document.querySelector('.modal').remove(); charsTab.select('yamazaki'); 'y'"},
 {"wait": 500},
 {"shot": "$OUT/tab_yamazaki.png", "full": true},
 {"eval": "charsTab.select('krauser'); 'k'"},
 {"wait": 500},
 {"shot": "$OUT/tab_krauser.png", "full": true},
 {"width": 400, "height": 900, "mobile": true},
 {"wait": 500},
 {"shot": "$OUT/tab_phone.png"},
 {"eval": "localStorage.clear(); charsTab.reset(); 'reset'"}]
J
node "$HERE/headless.js" http://localhost:8768/game.html "$OUT/steps.json" | grep -v '^eval: \[' || true
for p in today edit; do python3 -c "import json, sys; open(sys.argv[2], 'wb').write(bytes(json.load(open(sys.argv[1]))))" "$OUT/pack_page_$p.json" "$OUT/pack_page_$p.bin"; done
python3 "$HERE/../build_tables.py" pack "$GAME/game.json" "$GAME/build" "$OUT/pack_py.bin"
echo "== unedited: the page's pack vs build_tables.py pack"; cmp "$OUT/pack_page_today.bin" "$OUT/pack_py.bin" && echo "identical ($(stat -c %s "$OUT/pack_py.bin") bytes)"
python3 -c "
import json, sys
sys.path.insert(0, '$HERE/..'); import build_tables as BT
g = json.load(open('$GAME/game.json')); g['roster'] = json.load(open('$OUT/page_roster.json'))
open('$OUT/pack_py_edit.bin', 'wb').write(BT.pack(g, '$GAME/build'))
print('TERRY as edited in the page:', json.dumps(g['roster'][$F]))
"
echo "== edited: the page's roster merged into game.json, build_tables.py pack vs the page's pack"; cmp "$OUT/pack_page_edit.bin" "$OUT/pack_py_edit.bin" && echo "identical ($(stat -c %s "$OUT/pack_py_edit.bin") bytes)"
python3 "$T" "$GAME" lab "$OUT/desk_edit.json" --fighter $F --dummy $D --pack "$OUT/pack_page_edit.bin" --frames $NF > /dev/null
echo "== edited, page vs desktop core (tick-keyed)"; python3 "$T" --diff "$OUT/page_edit.json" "$OUT/desk_edit.json" --from-stage
python3 "$T" "$GAME" lab "$OUT/desk_rom.json" --fighter $F --dummy $D --pack "$OUT/pack_py.bin" --frames $NF > /dev/null
echo "== edited vs the ROM's mapping (must differ)"; python3 "$T" --diff "$OUT/desk_edit.json" "$OUT/desk_rom.json" --from-stage | head -3 || true
python3 -c "import json; print('   pack status in the page:', json.load(open('$OUT/page_edit.json'))['pack_status'])"
