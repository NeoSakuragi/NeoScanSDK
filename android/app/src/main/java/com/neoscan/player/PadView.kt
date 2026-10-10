package com.neoscan.player

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import kotlin.math.atan2
import kotlin.math.hypot

/** Touch controls, full screen over the picture: a d-pad (8 directions, dead zone) on the left, A B C D on the right in
 *  the Neo Geo arc (red, yellow, green, blue), COIN and START, settings (gear), soft reset (held 0.7 s), voice feedback (mic,
 *  next to reset: held = recording, [onFeedback] true on press, false on release), my feedback notes (a list, next to the mic in
 *  portrait, under START in landscape: a tap = [onList]; [badge] = the notes of the test queue) and update (blinks
 *  while a newer player or game build is on the server; a tap = [onUpdate], MainActivity's choice of the two). Portrait: in the space under the picture, on an opaque
 *  panel. Landscape: transparent, over the sides of the picture, drawn at [opacity]. Every pointer counts (hold a
 *  direction and press buttons); the mask goes to [onMask]; a short haptic tick on each new press. */
class PadView(ctx: Context, private val onSettings: () -> Unit, private val onUpdate: () -> Unit, private val onReset: () -> Unit,
              private val onFeedback: (Boolean) -> Unit, private val onList: () -> Unit, private val onMask: (Int) -> Unit) : View(ctx) {
    private class Btn(val bit: Int, val label: String, val color: Int) { var x = 0f; var y = 0f; var r = 0f }
    private val btns = listOf(Btn(Pad.A, "A", Color.rgb(220, 40, 40)), Btn(Pad.B, "B", Color.rgb(240, 200, 30)),
                              Btn(Pad.C, "C", Color.rgb(40, 180, 70)), Btn(Pad.D, "D", Color.rgb(40, 110, 230)))
    private val coin = Btn(Pad.COIN, "COIN", Color.rgb(90, 90, 100)); private val start = Btn(Pad.START, "START", Color.rgb(90, 90, 100))
    private val gear = Btn(0, "\u2699", Color.rgb(60, 60, 70))         // settings (no pad bit)
    private val upd = Btn(0, "\u2B07", Color.rgb(60, 60, 70))          // download the latest build (blinks when one is ready)
    private val rst = Btn(0, "\u27F2", Color.rgb(60, 60, 70))          // soft reset: held RESET_MS so a stray touch can't reset
    private var rstSince = 0L                                          // when the press on it began (0 = not pressed)
    private val mic = Btn(0, "", Color.rgb(60, 60, 70))               // voice feedback: held = recording (glyph drawn)
    private var micId = -1                                             // the pointer holding it (-1 = none)
    private var micSince = 0L
    private val fbl = Btn(0, "", Color.rgb(60, 60, 70))               // my feedback notes: the list (glyph drawn)
    private var fblHit = false
    var badge = 0                                                      // the test queue + the open decisions (0.0.24): a count on the list button
        set(v) { field = v; invalidate() }
    var updateReady = false                                            // a newer build is on the server: blink
        set(v) { field = v; invalidate() }
    var updateText: String? = null                                    // download progress ("45%") on the button
        set(v) { field = v; invalidate() }
    private var updHit = false
    /** TESTER MODE (0.0.26, Auth.admin): no list button (notes, test queue, decisions), no badge, no update button (the
     *  updates still come: the launch screen offers a downloaded player, the game build is fetched at launch) */
    var tester = false
        set(v) { field = v; if (width > 0) onSizeChanged(width, height, width, height); invalidate() }
    /** the first launch's tip is up (MainActivity.showTip): a thick white ring pulses around the mic */
    var hint = false
        set(v) { field = v; invalidate() }
    private fun shown(b: Btn) = !tester || (b !== fbl && b !== upd)
    var size = 1f                                                      // settings: button size factor
        set(v) { field = v; if (width > 0) onSizeChanged(width, height, width, height); invalidate() }
    var vibrate = true
    /** 0.0.29: the Character lab's status strip, OFF the picture: [labH] px kept for it right under the picture
     *  (portrait: the panel's buttons start below it) or in the left gutter under the top-left buttons (landscape: the
     *  d-pad moves down to clear it, as far as the screen allows); [labArea] = where it goes. 0 = no strip. */
    var labH = 0
        set(v) { if (field == v) return; field = v; if (width > 0) onSizeChanged(width, height, width, height); invalidate() }
    val labArea = android.graphics.Rect()
    private var dx = 0f; private var dy = 0f; private var dr = 0f
    private var mask = 0
    private var gearHit = false
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private var portrait = true; private var panelTop = 0f
    var opacity = 0.45f                                                // landscape controls (settings: item 19)
        set(v) { field = v; invalidate() }

    override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) {
        portrait = Screen.portrait(w, h)
        var k = size                                                   // big sizes: shrink until the arc clears the d-pad
        while (true) {
            place(w, h, k)
            val a = btns[0]
            if (hypot(a.x - dx, a.y - dy) >= a.r + dr + a.r * 0.15f || k < 0.5f) break
            k *= 0.95f
        }
    }

    private fun place(w: Int, h: Int, k: Float) {
        val dp = resources.displayMetrics.density
        if (portrait) {                                                // the panel under the picture (and the lab's strip)
            val pb = Screen.picture(w, h).bottom
            labArea.set(0, pb, w, pb + labH)
            val top = (pb + labH).toFloat(); val ph = h - top; panelTop = pb.toFloat()
            dr = minOf(w * 0.2f, ph * 0.32f) * k; dx = maxOf(w * 0.25f, dr + w * 0.03f); dy = top + ph * 0.66f
            val r = minOf(w * 0.075f, ph * 0.11f) * k
            arc(w - r * 1.25f, top + ph * 0.34f, r)
            coin.x = w * 0.40f; coin.y = top + ph * 0.12f; coin.r = r * 0.7f
            start.x = w * 0.60f; start.y = top + ph * 0.12f; start.r = r * 0.7f
            val y = top + ph * 0.12f; val g = r * 0.55f                 // the top row, left to right, evenly spaced: no
            val row = listOf(rst to g, mic to g, fbl to g, coin to r * 0.7f, start to r * 0.7f, upd to g, gear to g)   // overlap at any size
                .filter { shown(it.first) }                            // tester: no list, no update button
            val gap = (w - row.sumOf { (it.second * 2).toDouble() }.toFloat()) / (row.size + 1)
            var x = 0f
            for ((b, br) in row) { x += gap + br; b.x = x; b.y = y; b.r = br; x += br }
        } else {                                                       // over the picture's sides, thumbs' reach
            val side = maxOf(Screen.picture(w, h).left.toFloat(), h * 0.3f)   // the black bar, or at least 30 % of h
            dr = minOf(h * 0.2f, side * 0.62f) * k; dx = maxOf(side * 0.55f + dr * 0.15f, dr + h * 0.03f); dy = h * 0.66f
            val r = minOf(h * 0.085f, side * 0.2f) * k
            arc(w - r * 1.25f, h * 0.48f, r)
            coin.x = side * 0.4f; coin.y = h * 0.12f; coin.r = r * 0.7f
            start.x = w - side * 0.4f; start.y = h * 0.12f; start.r = r * 0.7f
            gear.x = side * 0.4f + r * 1.6f; gear.y = h * 0.12f; gear.r = r * 0.55f
            upd.x = w - side * 0.4f - r * 1.6f; upd.y = gear.y; upd.r = gear.r
            rst.x = coin.x; rst.y = coin.y + r * 1.6f; rst.r = gear.r
            mic.x = gear.x; mic.y = rst.y; mic.r = gear.r
            fbl.x = start.x; fbl.y = rst.y; fbl.r = gear.r                 // under START, the mirror of reset (under the left
                                                                           // pair is the d-pad's reach)
            val gut = Screen.picture(w, h).left.toFloat()                 // the lab's strip: the black bar when it is wide
            val lw = if (gut >= 80 * dp) gut else side                     // enough to read, else the controls' side
            val lt = rst.y + rst.r + 8 * dp
            labArea.set((4 * dp).toInt(), lt.toInt(), (lw - 4 * dp).toInt(), (lt + labH).toInt())
            if (labH > 0) dy = maxOf(dy, minOf(labArea.bottom + dr + 6 * dp, h - dr - 4 * dp))
        }
    }

    /** the Neo Geo arc, rising rightwards, from D at (dX, dY) back down to A; spacing follows the button size */
    private fun arc(dX: Float, dY: Float, r: Float) {
        val dxs = floatArrayOf(-5.5f, -3.9f, -2.0f, 0f); val dys = floatArrayOf(2.9f, 1.5f, 0.6f, 0f)   // ~2.1 r apart
        btns.forEachIndexed { i, b -> b.x = dX + dxs[i] * r; b.y = dY + dys[i] * r; b.r = r }
    }

    private val dbg = Paint().apply { color = Color.YELLOW; textSize = 28f; isAntiAlias = true }
    override fun onDraw(c: Canvas) {
        if (FrameStats.show && FrameStats.line.isNotEmpty()) { c.drawText(FrameStats.line, 16f, 40f, dbg); postInvalidateDelayed(500) }
        if (portrait) { paint.alpha = 255; paint.color = Color.rgb(18, 18, 24); c.drawRect(0f, panelTop, width.toFloat(), height.toFloat(), paint) }
        if (!portrait) c.saveLayerAlpha(0f, 0f, width.toFloat(), height.toFloat(), (opacity * 255).toInt())
        paint.style = Paint.Style.FILL; paint.color = Color.rgb(45, 45, 55); c.drawCircle(dx, dy, dr, paint)
        paint.color = Color.rgb(70, 70, 84)
        val arm = dr * 0.3f
        c.drawRect(dx - arm, dy - dr * 0.9f, dx + arm, dy + dr * 0.9f, paint); c.drawRect(dx - dr * 0.9f, dy - arm, dx + dr * 0.9f, dy + arm, paint)
        paint.color = Color.argb(140, 255, 255, 255)
        if (mask and Pad.UP != 0) c.drawRect(dx - arm, dy - dr * 0.9f, dx + arm, dy - arm, paint)
        if (mask and Pad.DOWN != 0) c.drawRect(dx - arm, dy + arm, dx + arm, dy + dr * 0.9f, paint)
        if (mask and Pad.LEFT != 0) c.drawRect(dx - dr * 0.9f, dy - arm, dx - arm, dy + arm, paint)
        if (mask and Pad.RIGHT != 0) c.drawRect(dx + arm, dy - arm, dx + dr * 0.9f, dy + arm, paint)
        val holding = rstSince != 0L
        for (b in btns + coin + start + gear + rst) {
            val on = mask and b.bit != 0 || (b === rst && holding)
            paint.color = if (on) Color.WHITE else b.color; c.drawCircle(b.x, b.y, b.r, paint)
            paint.color = if (on) b.color else Color.WHITE; paint.textSize = b.r * (if (b.label.length > 1) 0.5f else 0.9f)
            c.drawText(b.label, b.x, b.y + paint.textSize * 0.35f, paint)
        }
        val rec = micId >= 0                                           // the mic: a capsule on a stand, red while recording
        paint.color = if (rec) Color.rgb(220, 30, 30) else mic.color; c.drawCircle(mic.x, mic.y, mic.r, paint)
        paint.color = Color.WHITE; val u = mic.r * 0.11f
        c.drawRoundRect(mic.x - 2.2f * u, mic.y - 5.5f * u, mic.x + 2.2f * u, mic.y + 1.5f * u, 2.2f * u, 2.2f * u, paint)
        paint.style = Paint.Style.STROKE; paint.strokeWidth = u * 0.9f
        c.drawArc(mic.x - 3.6f * u, mic.y - 3.6f * u, mic.x + 3.6f * u, mic.y + 3.2f * u, 0f, 180f, false, paint)
        c.drawLine(mic.x, mic.y + 3.2f * u, mic.x, mic.y + 5.6f * u, paint); c.drawLine(mic.x - 2f * u, mic.y + 5.6f * u, mic.x + 2f * u, mic.y + 5.6f * u, paint)
        paint.style = Paint.Style.FILL
        if (shown(fbl)) {
            paint.color = if (fblHit) Color.WHITE else fbl.color; c.drawCircle(fbl.x, fbl.y, fbl.r, paint)   // the list: 3 bullets + lines
            paint.color = if (fblHit) fbl.color else Color.WHITE; val v = fbl.r * 0.11f
            for (i in -1..1) { val ly = fbl.y + i * 2.6f * v
                c.drawCircle(fbl.x - 3.6f * v, ly, 0.8f * v, paint); c.drawRect(fbl.x - 1.9f * v, ly - 0.6f * v, fbl.x + 4.4f * v, ly + 0.6f * v, paint) }
        }
        if (!portrait) c.restore()
        micLabel(c)
        if (badge > 0 && !tester) {                                               // the count, always opaque (like the update button)
            val br = fbl.r * 0.42f; val bx = fbl.x + fbl.r * 0.72f; val by = fbl.y - fbl.r * 0.72f; val t = if (badge > 99) "99+" else "$badge"
            paint.alpha = 255; paint.color = Color.rgb(220, 30, 30); c.drawCircle(bx, by, br, paint)
            paint.style = Paint.Style.STROKE; paint.strokeWidth = br * 0.16f; paint.color = Color.WHITE; c.drawCircle(bx, by, br, paint); paint.style = Paint.Style.FILL
            paint.textSize = br * (if (t.length > 1) 0.95f else 1.25f); c.drawText(t, bx, by + paint.textSize * 0.36f, paint)
        }
        if (rec) {                                                     // recording: a pulsing ring + the seconds held
            val t = android.os.SystemClock.uptimeMillis() - micSince
            paint.alpha = 255; paint.style = Paint.Style.STROKE; paint.strokeWidth = mic.r * 0.15f
            paint.color = Color.argb(if (t / 400 % 2 == 0L) 255 else 120, 255, 60, 60)
            c.drawCircle(mic.x, mic.y, mic.r * 1.25f, paint); paint.style = Paint.Style.FILL
            paint.textSize = mic.r * 0.6f; paint.color = Color.rgb(255, 80, 80); c.drawText("${t / 1000}s", mic.x, mic.y + mic.r * 2.5f, paint)
            postInvalidateDelayed(100)
        }
        if (holding) {                                                 // the hold's progress: a ring filling to RESET_MS
            val f = ((android.os.SystemClock.uptimeMillis() - rstSince).toFloat() / RESET_MS).coerceAtMost(1f)
            paint.alpha = 255; paint.style = Paint.Style.STROKE; paint.strokeWidth = rst.r * 0.18f; paint.color = Color.rgb(255, 150, 0)
            c.drawArc(rst.x - rst.r, rst.y - rst.r, rst.x + rst.r, rst.y + rst.r, -90f, 360f * f, false, paint)
            paint.style = Paint.Style.FILL; postInvalidateDelayed(30)
        }
        // update button (0.0.21: a newer player OR game build): always opaque so a waiting update is seen; a slow pulse
        // that is not colour-only (e-ink safe): a thick white ring around it on / off every 600 ms, the fill orange with
        // it; no ring, grey = up to date
        if (!shown(upd)) return
        val blink = updateReady && updateText == null && (android.os.SystemClock.uptimeMillis() / BLINK_MS) % 2 == 0L
        paint.alpha = 255; paint.color = if (updateText != null) Color.rgb(230, 130, 20) else if (blink) Color.rgb(255, 150, 0) else upd.color
        c.drawCircle(upd.x, upd.y, upd.r, paint)
        if (blink) {
            paint.style = Paint.Style.STROKE; paint.strokeWidth = upd.r * 0.22f; paint.color = Color.WHITE
            c.drawCircle(upd.x, upd.y, upd.r * 1.12f, paint); paint.style = Paint.Style.FILL
        }
        paint.color = Color.WHITE; val t = updateText ?: upd.label
        paint.textSize = upd.r * (if (t.length > 1) 0.55f else 0.9f); c.drawText(t, upd.x, upd.y + paint.textSize * 0.35f, paint)
        if (updateReady && updateText == null) postInvalidateDelayed(BLINK_MS - android.os.SystemClock.uptimeMillis() % BLINK_MS + 5)
    }

    /** 0.0.26: "Feedback" under the mic, always readable (opaque, over a dark outline) so a first-time tester finds it */
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; color = Color.WHITE
        setShadowLayer(4f, 0f, 0f, Color.BLACK); typeface = android.graphics.Typeface.DEFAULT_BOLD }
    private fun micLabel(c: Canvas) {
        if (hint) {
            val on = android.os.SystemClock.uptimeMillis() / BLINK_MS % 2 == 0L
            paint.alpha = 255; paint.style = Paint.Style.STROKE; paint.strokeWidth = mic.r * (if (on) 0.3f else 0.15f); paint.color = Color.WHITE
            c.drawCircle(mic.x, mic.y, mic.r * 1.3f, paint); paint.style = Paint.Style.FILL; postInvalidateDelayed(BLINK_MS / 2)
        }
        label.textSize = maxOf(11f * resources.displayMetrics.scaledDensity, mic.r * 0.42f)
        c.drawText("Feedback", mic.x, mic.y + mic.r * (if (hint) 1.5f else 1f) + label.textSize * 1.05f, label)
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        var m = 0
        for (i in 0 until e.pointerCount) {
            if ((e.actionMasked == MotionEvent.ACTION_UP || e.actionMasked == MotionEvent.ACTION_POINTER_UP) && i == e.actionIndex) continue
            if (e.actionMasked == MotionEvent.ACTION_CANCEL) continue
            val x = e.getX(i); val y = e.getY(i)
            val d = hypot(x - dx, y - dy)
            if (d < dr * 1.5f) {                                        // d-pad: 8 sectors outside a dead zone
                if (d > dr * 0.22f) {
                    val a = Math.toDegrees(atan2((y - dy).toDouble(), (x - dx).toDouble()))   // 0 = right, 90 = down
                    val s = ((a + 360 + 22.5) % 360 / 45).toInt()
                    m = m or when (s) { 0 -> Pad.RIGHT; 1 -> Pad.RIGHT or Pad.DOWN; 2 -> Pad.DOWN; 3 -> Pad.DOWN or Pad.LEFT
                        4 -> Pad.LEFT; 5 -> Pad.LEFT or Pad.UP; 6 -> Pad.UP; else -> Pad.UP or Pad.RIGHT }
                }
                continue
            }
            if (e.getPointerId(i) == micId) continue                  // the finger holding the mic
            val b = (btns + coin + start + gear + upd + rst + mic + fbl).filter { shown(it) }.minByOrNull { hypot(x - it.x, y - it.y) / it.r }
            if (b != null && hypot(x - b.x, y - b.y) < b.r * 1.35f) {
                val down = e.actionMasked == MotionEvent.ACTION_DOWN || e.actionMasked == MotionEvent.ACTION_POINTER_DOWN
                if (b === gear) { if (down) gearHit = true }
                else if (b === upd) { if (down) updHit = true }
                else if (b === fbl) { if (down) { fblHit = true; invalidate() } }
                else if (b === rst) { if (down) { rstSince = android.os.SystemClock.uptimeMillis(); invalidate() } }
                else if (b === mic) { if (down && i == e.actionIndex && micId < 0) {
                    micId = e.getPointerId(i); micSince = android.os.SystemClock.uptimeMillis()
                    performHapticFeedback(HapticFeedbackConstants.LONG_PRESS); onFeedback(true); invalidate() } }
                else m = m or b.bit
            }
        }
        if (gearHit && e.actionMasked == MotionEvent.ACTION_UP) { gearHit = false; onSettings() }
        if (fblHit && (e.actionMasked == MotionEvent.ACTION_UP || e.actionMasked == MotionEvent.ACTION_CANCEL)) {
            fblHit = false; invalidate(); if (e.actionMasked == MotionEvent.ACTION_UP) onList() }
        if (updHit && e.actionMasked == MotionEvent.ACTION_UP) { updHit = false; if (updateText == null) onUpdate() }
        if (rstSince != 0L && (e.actionMasked == MotionEvent.ACTION_UP || e.actionMasked == MotionEvent.ACTION_CANCEL)) {
            val held = android.os.SystemClock.uptimeMillis() - rstSince; rstSince = 0L; invalidate()
            if (held >= RESET_MS && e.actionMasked == MotionEvent.ACTION_UP) { performHapticFeedback(HapticFeedbackConstants.LONG_PRESS); onReset() }
        }
        if (micId >= 0 && (e.actionMasked == MotionEvent.ACTION_CANCEL || e.actionMasked == MotionEvent.ACTION_UP ||
                e.actionMasked == MotionEvent.ACTION_POINTER_UP && e.getPointerId(e.actionIndex) == micId)) {
            micId = -1; onFeedback(false); invalidate() }
        if (vibrate && m and mask.inv() != 0) performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
        if (m != mask) { mask = m; onMask(m); invalidate() }
        return true
    }
    companion object { const val RESET_MS = 700L; const val BLINK_MS = 600L }
}
