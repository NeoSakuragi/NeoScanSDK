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
 *  the Neo Geo arc (red, yellow, green, blue), COIN and START, settings (gear) and download-the-latest-build (blinks when the server has a newer one). Portrait: in the space under the picture, on an opaque
 *  panel. Landscape: transparent, over the sides of the picture, drawn at [opacity]. Every pointer counts (hold a
 *  direction and press buttons); the mask goes to [onMask]; a short haptic tick on each new press. */
class PadView(ctx: Context, private val onSettings: () -> Unit, private val onUpdate: () -> Unit,
              private val onMask: (Int) -> Unit) : View(ctx) {
    private class Btn(val bit: Int, val label: String, val color: Int) { var x = 0f; var y = 0f; var r = 0f }
    private val btns = listOf(Btn(Pad.A, "A", Color.rgb(220, 40, 40)), Btn(Pad.B, "B", Color.rgb(240, 200, 30)),
                              Btn(Pad.C, "C", Color.rgb(40, 180, 70)), Btn(Pad.D, "D", Color.rgb(40, 110, 230)))
    private val coin = Btn(Pad.COIN, "COIN", Color.rgb(90, 90, 100)); private val start = Btn(Pad.START, "START", Color.rgb(90, 90, 100))
    private val gear = Btn(0, "\u2699", Color.rgb(60, 60, 70))         // settings (no pad bit)
    private val upd = Btn(0, "\u2B07", Color.rgb(60, 60, 70))          // download the latest build (blinks when one is ready)
    var updateReady = false                                            // a newer build is on the server: blink
        set(v) { field = v; invalidate() }
    var updateText: String? = null                                    // download progress ("45%") on the button
        set(v) { field = v; invalidate() }
    private var updHit = false
    var size = 1f                                                      // settings: button size factor
        set(v) { field = v; if (width > 0) onSizeChanged(width, height, width, height); invalidate() }
    var vibrate = true
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
        if (portrait) {                                                // the panel under the picture
            val top = Screen.picture(w, h).bottom.toFloat(); val ph = h - top; panelTop = top
            dr = minOf(w * 0.2f, ph * 0.32f) * k; dx = maxOf(w * 0.25f, dr + w * 0.03f); dy = top + ph * 0.66f
            val r = minOf(w * 0.075f, ph * 0.11f) * k
            arc(w - r * 1.25f, top + ph * 0.34f, r)
            coin.x = w * 0.40f; coin.y = top + ph * 0.12f; coin.r = r * 0.7f
            start.x = w * 0.60f; start.y = top + ph * 0.12f; start.r = r * 0.7f
            gear.x = w * 0.92f; gear.y = top + ph * 0.12f; gear.r = r * 0.55f
            upd.x = w * 0.80f; upd.y = gear.y; upd.r = gear.r
        } else {                                                       // over the picture's sides, thumbs' reach
            val side = maxOf(Screen.picture(w, h).left.toFloat(), h * 0.3f)   // the black bar, or at least 30 % of h
            dr = minOf(h * 0.2f, side * 0.62f) * k; dx = maxOf(side * 0.55f + dr * 0.15f, dr + h * 0.03f); dy = h * 0.66f
            val r = minOf(h * 0.085f, side * 0.2f) * k
            arc(w - r * 1.25f, h * 0.48f, r)
            coin.x = side * 0.4f; coin.y = h * 0.12f; coin.r = r * 0.7f
            start.x = w - side * 0.4f; start.y = h * 0.12f; start.r = r * 0.7f
            gear.x = side * 0.4f + r * 1.6f; gear.y = h * 0.12f; gear.r = r * 0.55f
            upd.x = w - side * 0.4f - r * 1.6f; upd.y = gear.y; upd.r = gear.r
        }
    }

    /** the Neo Geo arc, rising rightwards, from D at (dX, dY) back down to A; spacing follows the button size */
    private fun arc(dX: Float, dY: Float, r: Float) {
        val dxs = floatArrayOf(-5.5f, -3.9f, -2.0f, 0f); val dys = floatArrayOf(2.9f, 1.5f, 0.6f, 0f)   // ~2.1 r apart
        btns.forEachIndexed { i, b -> b.x = dX + dxs[i] * r; b.y = dY + dys[i] * r; b.r = r }
    }

    override fun onDraw(c: Canvas) {
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
        for (b in btns + coin + start + gear) {
            val on = mask and b.bit != 0
            paint.color = if (on) Color.WHITE else b.color; c.drawCircle(b.x, b.y, b.r, paint)
            paint.color = if (on) b.color else Color.WHITE; paint.textSize = b.r * (if (b.label.length > 1) 0.5f else 0.9f)
            c.drawText(b.label, b.x, b.y + paint.textSize * 0.35f, paint)
        }
        if (!portrait) c.restore()
        // update button: always opaque so a waiting build is seen; orange / grey blink (2.5 Hz) while one is ready
        val blink = updateReady && (android.os.SystemClock.uptimeMillis() / 200) % 2 == 0L
        paint.alpha = 255; paint.color = if (updateText != null) Color.rgb(230, 130, 20) else if (blink) Color.rgb(255, 150, 0) else upd.color
        c.drawCircle(upd.x, upd.y, upd.r, paint)
        paint.color = Color.WHITE; val t = updateText ?: upd.label
        paint.textSize = upd.r * (if (t.length > 1) 0.55f else 0.9f); c.drawText(t, upd.x, upd.y + paint.textSize * 0.35f, paint)
        if (updateReady && updateText == null) postInvalidateDelayed(200)
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
            val b = (btns + coin + start + gear + upd).minByOrNull { hypot(x - it.x, y - it.y) / it.r }
            if (b != null && hypot(x - b.x, y - b.y) < b.r * 1.35f) {
                val down = e.actionMasked == MotionEvent.ACTION_DOWN || e.actionMasked == MotionEvent.ACTION_POINTER_DOWN
                if (b === gear) { if (down) gearHit = true }
                else if (b === upd) { if (down) updHit = true }
                else m = m or b.bit
            }
        }
        if (gearHit && e.actionMasked == MotionEvent.ACTION_UP) { gearHit = false; onSettings() }
        if (updHit && e.actionMasked == MotionEvent.ACTION_UP) { updHit = false; if (updateText == null) onUpdate() }
        if (vibrate && m and mask.inv() != 0) performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
        if (m != mask) { mask = m; onMask(m); invalidate() }
        return true
    }
}
