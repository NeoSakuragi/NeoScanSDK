#!/bin/bash
# Stages tab proof (our emulator's core only, never MAME): stage 1 wave 2 edited IN THE PAGE (headless Chrome: wave 2's
# spawns removed, "Add 3 x YAKUZA from the right"), played in the page (its own wasm core), in Node (core.wasm) and on
# the desktop core (ramtrace.py stage) with the page's pack: tick-keyed traces from the stage start compared; the
# unedited campaign: the page's pack = build_tables.py pack byte for byte, and played by tick = the ROM's own tables.
#   stage_proof.sh SITE_DIR GAME_DIR OUT_DIR        (SITE_DIR: make_site.py output with core.js / core.wasm)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); SITE=$(cd "$1" && pwd); GAME=$(cd "$2" && pwd); OUT=$3; T=$HERE/../ramtrace.py
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SCR=$(python3 -c "import sys; sys.path.insert(0, '$HERE/..'); import ramtrace; print(ramtrace.STAGE_SCRIPT)")
(cd "$SITE" && exec python3 -m http.server 8765 > /dev/null 2>&1) & SRV=$!; trap "kill $SRV" EXIT; sleep 1
cat > "$OUT/steps.json" <<J
[{"wait": 6000},
 {"eval": "Array.from(stagesTab.pack().bytes)", "save": "$OUT/pack_page_today.json"},
 {"eval": "document.getElementById('tabStages').click(); localStorage.clear(); stagesTab.stages = JSON.parse(JSON.stringify(stagesTab.D.stages)); 'tab'"},
 {"wait": 300},
 {"eval": "(() => { const card = () => document.querySelectorAll('#stagecol .wave')[1]; for (let i = 0; i < 3; i++) [...card().querySelectorAll('button')].find(b => b.title === 'remove').click(); const add = card().querySelector('.add'); const [cnt, dly] = add.querySelectorAll('input'); const [en, side] = add.querySelectorAll('select'); cnt.value = 3; en.value = 'YAKUZA'; side.value = 'right'; dly.value = 0; [...add.querySelectorAll('button')].find(b => b.textContent === 'Add').click(); return stagesTab.stages[0].waves[1]; })()"},
 {"eval": "Array.from(stagesTab.pack().bytes)", "save": "$OUT/pack_page_edit.json"},
 {"eval": "(() => { const C = chainlab, L = C.lab, script = '$SCR'; if (!C.paused) C.togglePause(); L.core._wc_reset(); L.setPad(0, ''); L.setPad(1, ''); L.run(400); stagesTab.play(0, 1); if (!C.paused) C.togglePause(); const trace = [L.ramSnap()], ticks = [L.gameTicks()]; const parts = script.split(',').map(p => p.split(':')); while (trace.length < 1500) for (const [n, k] of parts) for (let i = 0; i < Number(n) && trace.length < 1500; i++) { L.setPad(0, k.replace('-', '')); L.run(1); trace.push(L.ramSnap()); ticks.push(L.gameTicks()); } return { trace, ticks, pack_status: L.packStatus() }; })()", "save": "$OUT/page_edit.json"},
 {"eval": "stagesTab.stages = JSON.parse(JSON.stringify(stagesTab.D.stages)); 'reset'"}]
J
node "$HERE/headless.js" http://localhost:8765/index.html "$OUT/steps.json" | grep -v '^eval: \[' || true
for p in today edit; do python3 -c "import json, sys; open(sys.argv[2], 'wb').write(bytes(json.load(open(sys.argv[1]))))" "$OUT/pack_page_$p.json" "$OUT/pack_page_$p.bin"; done
python3 "$HERE/../build_tables.py" pack "$GAME/game.json" "$GAME/build" "$OUT/pack_py.bin"
echo "== unedited: the page's pack vs build_tables.py pack"; cmp "$OUT/pack_page_today.bin" "$OUT/pack_py.bin" && echo "identical ($(stat -c %s "$OUT/pack_py.bin") bytes)"
python3 "$T" "$GAME" stage "$OUT/desk_edit.json" --stage 0 --wave 1 --pack "$OUT/pack_page_edit.bin" --frames 1500 > /dev/null
node "$HERE/stage_proof_node.js" "$SITE" "$OUT/wasm_edit.json" 0 1 0 1500 "$SCR" "$OUT/pack_page_edit.bin"
echo "== edited, page vs desktop core"; python3 "$T" --diff "$OUT/page_edit.json" "$OUT/desk_edit.json" --from-stage
echo "== edited, Node core.wasm vs desktop core"; python3 "$T" --diff "$OUT/wasm_edit.json" "$OUT/desk_edit.json" --from-stage
for w in 1 5; do
  python3 "$T" "$GAME" stage "$OUT/desk_rom_w$w.json" --stage 0 --wave $w --frames 1500 > /dev/null
  python3 "$T" "$GAME" stage "$OUT/desk_today_w$w.json" --stage 0 --wave $w --pack "$OUT/pack_page_today.bin" --replay "$OUT/desk_rom_w$w.json" > /dev/null
  echo "== unedited pack vs the ROM's tables, stage 1 from $([ $w = 5 ] && echo "the boss" || echo "wave $((w + 1))")"
  python3 "$T" --diff "$OUT/desk_today_w$w.json" "$OUT/desk_rom_w$w.json" --from-stage
done
echo "== edited vs unedited (must differ)"; python3 "$T" --diff "$OUT/desk_edit.json" "$OUT/desk_rom_w1.json" --from-stage | head -1 || true
