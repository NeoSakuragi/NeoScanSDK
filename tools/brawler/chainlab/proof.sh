#!/bin/bash
# Chain Lab proof: the scripted route (labdrive.py SCRIPT: Terry's AABA command route) on the desktop core (harness) and
# on the browser's core (core.wasm under Node), with the fighter's own tree and with an edited one; traces compared.
#   proof.sh SITE_DIR GAME_DIR OUT_DIR [EDITED_TREE.json]
set -e
HERE=$(cd "$(dirname "$0")" && pwd); SITE=$1; GAME=$2; OUT=$3; EDIT=$4
mkdir -p "$OUT"
python3 "$HERE/labdrive.py" "$OUT/desk_own.json" > /dev/null
node "$HERE/proof_node.js" "$SITE" "$GAME" "$OUT/wasm_own.json" | grep -E "encoder|speed"
echo "== own tree: desktop vs browser core"; python3 "$HERE/compare.py" "$OUT/desk_own.json" "$OUT/wasm_own.json"
if [ -n "$EDIT" ]; then
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); json.dump(d['tree'], open(sys.argv[2],'w'))" "$EDIT" "$OUT/edited_tree.json"
  python3 "$HERE/../routes.py" encode "$OUT/edited_tree.json" "$OUT/edited_tree.bin"
  python3 "$HERE/labdrive.py" "$OUT/desk_edit.json" "$OUT/edited_tree.bin" > /dev/null
  node "$HERE/proof_node.js" "$SITE" "$GAME" "$OUT/wasm_edit.json" "$OUT/edited_tree.json" 0 > /dev/null
  echo "== edited tree: desktop vs browser core"; python3 "$HERE/compare.py" "$OUT/desk_edit.json" "$OUT/wasm_edit.json"
  echo "== own tree vs edited tree (expected to differ)"; python3 "$HERE/compare.py" "$OUT/desk_own.json" "$OUT/desk_edit.json" || true
fi
