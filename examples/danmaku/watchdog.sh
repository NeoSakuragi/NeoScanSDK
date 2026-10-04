#!/bin/bash
# Crash monitor for danmaku. Uses peek to watch game-alive sentinel.
LOG=/tmp/emu_diag.log
EMU="../../emu/neogeo_sdl"
ROM="danmaku.neo"

pkill -f neogeo_sdl 2>/dev/null; sleep 1
rm -f "$LOG"

# Script: start game, then peek debug RAM every 60 frames
cat > /tmp/danmaku_monitor.script << 'SCRIPT'
60 key 1
90 key 1
300 peek 10F200
300 peek 10F204
300 peek 10F206
300 peek 10F208
600 peek 10F200
600 peek 10F204
600 peek 10F206
600 peek 10F208
900 peek 10F200
900 peek 10F204
900 peek 10F206
900 peek 10F208
1200 peek 10F200
1200 peek 10F204
1200 peek 10F206
1200 peek 10F208
1500 peek 10F200
1500 peek 10F204
1500 peek 10F206
1800 peek 10F200
1800 peek 10F204
1800 peek 10F206
2100 peek 10F200
2100 peek 10F204
2400 quit
SCRIPT

echo "=== Launching danmaku with frame monitor ==="
$EMU $ROM --script /tmp/danmaku_monitor.script > "$LOG" 2>&1 &
PID=$!
echo "PID: $PID"

# Monitor the log for PEEK results and crashes
tail -f "$LOG" 2>/dev/null | while read -r line; do
    # Show peek results live
    if echo "$line" | grep -q "PEEK"; then
        echo "$line"
    fi
    # Catch exceptions
    if echo "$line" | grep -qE "^EXCEPTION"; then
        echo "!!! $line"
        grep "EXCEPTION\|Selected\|PEEK" "$LOG"
        kill $PID 2>/dev/null
        exit 0
    fi
done

echo ""
echo "=== Final log ==="
grep "PEEK\|Selected\|EXCEPTION\|Watchdog" "$LOG"
