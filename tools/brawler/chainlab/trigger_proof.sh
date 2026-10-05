#!/bin/bash
# Triggers proof (TODO 56, our emulator's core only, never MAME): a trigger added IN THE PAGE (headless Chrome, the
# Stages tab's "Add a trigger": 120 ticks after wave 1 came, 2 x the first enemy from the right, one every 60 ticks),
# its pack = build_tables.py pack of game.json with the same trigger byte for byte, played from the stage start in the
# page (its wasm core), in Node (core.wasm) and on the desktop core (ramtrace.py stage): tick-keyed traces compared, and
# the ticks at which the trigger's enemies enter (desktop trace).
#   trigger_proof.sh SITE_DIR GAME_DIR OUT_DIR        (SITE_DIR: make_site.py output with core.js / core.wasm)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); SITE=$(cd "$1" && pwd); GAME=$(cd "$2" && pwd); OUT=$3; T=$HERE/../ramtrace.py
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SCR=$(python3 -c "import sys; sys.path.insert(0, '$HERE/..'); import ramtrace; print(ramtrace.STAGE_SCRIPT)")
(cd "$SITE" && exec python3 -m http.server 8766 > /dev/null 2>&1) & SRV=$!; trap "kill $SRV" EXIT; sleep 1
cat > "$OUT/steps.json" <<J
[{"wait": 6000},
 {"eval": "Array.from(stagesTab.pack().bytes)", "save": "$OUT/pack_page_today.json"},
 {"eval": "document.getElementById('tabStages').click(); localStorage.clear(); stagesTab.stages = JSON.parse(JSON.stringify(stagesTab.D.stages)); 'tab'"},
 {"wait": 300},
 {"eval": "(() => { [...document.querySelectorAll('#stagecol button')].find(b => b.textContent === 'Add a trigger').click(); return stagesTab.stages[0].triggers; })()", "save": "$OUT/trigger_page.json"},
 {"eval": "Array.from(stagesTab.pack().bytes)", "save": "$OUT/pack_page_edit.json"},
 {"eval": "(() => { const C = chainlab, L = C.lab, script = '$SCR'; if (!C.paused) C.togglePause(); L.core._wc_reset(); L.setPad(0, ''); L.setPad(1, ''); L.run(400); stagesTab.play(0, 0); if (!C.paused) C.togglePause(); const trace = [L.ramSnap()], ticks = [L.gameTicks()]; const parts = script.split(',').map(p => p.split(':')); while (trace.length < 1500) for (const [n, k] of parts) for (let i = 0; i < Number(n) && trace.length < 1500; i++) { L.setPad(0, k.replace('-', '')); L.run(1); trace.push(L.ramSnap()); ticks.push(L.gameTicks()); } return { trace, ticks, pack_status: L.packStatus() }; })()", "save": "$OUT/page_edit.json"},
 {"eval": "stagesTab.stages = JSON.parse(JSON.stringify(stagesTab.D.stages)); 'reset'"}]
J
node "$HERE/headless.js" http://localhost:8766/index.html "$OUT/steps.json" | grep -v '^eval: \[' || true
for p in today edit; do python3 -c "import json, sys; open(sys.argv[2], 'wb').write(bytes(json.load(open(sys.argv[1]))))" "$OUT/pack_page_$p.json" "$OUT/pack_page_$p.bin"; done
python3 "$HERE/../build_tables.py" pack "$GAME/game.json" "$GAME/build" "$OUT/pack_py.bin"
echo "== unedited: the page's pack vs build_tables.py pack"; cmp "$OUT/pack_page_today.bin" "$OUT/pack_py.bin" && echo "identical ($(stat -c %s "$OUT/pack_py.bin") bytes)"
python3 -c "import json, sys; g = json.load(open(sys.argv[1])); g['stages'][0]['triggers'] = json.load(open(sys.argv[2])); print('trigger:', json.dumps(g['stages'][0]['triggers'])); json.dump(g, open(sys.argv[3], 'w'))" "$GAME/game.json" "$OUT/trigger_page.json" "$OUT/game_trig.json"
python3 "$HERE/../build_tables.py" pack "$OUT/game_trig.json" "$GAME/build" "$OUT/pack_py_trig.bin"
echo "== edited: the page's pack vs build_tables.py pack of game.json + the trigger"; cmp "$OUT/pack_page_edit.bin" "$OUT/pack_py_trig.bin" && echo "identical ($(stat -c %s "$OUT/pack_py_trig.bin") bytes)"
python3 "$T" "$GAME" stage "$OUT/desk_edit.json" --stage 0 --wave 0 --pack "$OUT/pack_page_edit.bin" --frames 1500 > /dev/null
node "$HERE/stage_proof_node.js" "$SITE" "$OUT/wasm_edit.json" 0 0 0 1500 "$SCR" "$OUT/pack_page_edit.bin"
echo "== edited, page vs desktop core"; python3 "$T" --diff "$OUT/page_edit.json" "$OUT/desk_edit.json" --from-stage
echo "== edited, Node core.wasm vs desktop core"; python3 "$T" --diff "$OUT/wasm_edit.json" "$OUT/desk_edit.json" --from-stage
echo "== the trigger's enemies (desktop trace): slot, tick after the stage start, fighter"
python3 - "$OUT/desk_edit.json" <<'P'
import json, sys
d = json.load(open(sys.argv[1])); tr, tk = d['trace'], d['ticks']
t0 = next(t for s, t in zip(tr, tk) if s[1][2] is not None)          # wave 1 on screen (the stage start)
seen = {}
for s, t in zip(tr, tk):
    for i in (4, 5):
        if s[1][i] is not None and i not in seen: seen[i] = (t - t0, s[1][i][-1])
print(' ', {f'slot {i}': f'tick +{v[0]}, fighter {v[1]}' for i, v in sorted(seen.items())})
P
