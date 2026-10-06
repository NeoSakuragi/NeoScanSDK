package com.neoscan.player

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import java.io.File

/** Scribbles on the press screenshot (Player 0.0.15, docs/feedback.md): while the mic is held (or the typed-note box
 *  is open), the frozen screenshot is a drawing canvas ([View]). Strokes are kept in the picture's own coordinates
 *  (0..1 of its width / height), so they render exactly at any size. In the bundle ([write]): screen.png stays clean
 *  (the replay checks it), annotation.png = the strokes alone on transparent, screen_marked.png = the screenshot with
 *  the strokes; both [SCALE] times the screenshot (pixels doubled, no smoothing), so the lines stay smooth. */
object Ink {
    const val SCALE = 4
    val RED = Color.rgb(255, 40, 40)
    val GREEN = Color.rgb(40, 230, 70)

    /** [width] = the line width as a fraction of the picture's width; [pts] = x0, y0, x1, y1 ... (fractions) */
    class Stroke(val color: Int, val width: Float) { var pts = FloatArray(64); var n = 0
        fun add(x: Float, y: Float) { if (n + 2 > pts.size) pts = pts.copyOf(pts.size * 2); pts[n++] = x; pts[n++] = y }
    }

    private fun paint(s: Stroke, w: Int) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = s.color; style = Paint.Style.STROKE; strokeWidth = s.width * w
        strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }

    /** the strokes drawn into [c] over the rectangle [r] */
    fun draw(c: Canvas, strokes: List<Stroke>, r: RectF) {
        for (s in strokes) {
            val p = paint(s, r.width().toInt())
            if (s.n == 2) { p.style = Paint.Style.FILL; c.drawCircle(r.left + s.pts[0] * r.width(), r.top + s.pts[1] * r.height(), p.strokeWidth / 2, p); continue }
            val path = Path()
            for (i in 0 until s.n step 2) {
                val x = r.left + s.pts[i] * r.width(); val y = r.top + s.pts[i + 1] * r.height()
                if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            c.drawPath(path, p)
        }
    }

    /** annotation.png + screen_marked.png next to screen.png in [dir]; false when there is no screenshot */
    fun write(dir: File, strokes: List<Stroke>): Boolean {
        val shot = BitmapFactory.decodeFile(File(dir, "screen.png").path) ?: return false
        val w = shot.width * SCALE; val h = shot.height * SCALE
        val ann = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        draw(Canvas(ann), strokes, RectF(0f, 0f, w.toFloat(), h.toFloat()))
        File(dir, "annotation.png").outputStream().use { ann.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val marked = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        Canvas(marked).apply {
            drawBitmap(shot, Rect(0, 0, shot.width, shot.height), Rect(0, 0, w, h), Paint().apply { isFilterBitmap = false })
            drawBitmap(ann, 0f, 0f, null)
        }
        File(dir, "screen_marked.png").outputStream().use { marked.compress(Bitmap.CompressFormat.PNG, 100, it) }
        return true
    }

    /** the canvas: the screenshot fitted (pixel-exact look: no smoothing) and the strokes over it; one finger draws
     *  (a second finger on the mic button belongs to the pad view under it) */
    class View(ctx: Context) : android.view.View(ctx) {
        val strokes = ArrayList<Stroke>()
        var color = RED
        var shot: Bitmap? = null; set(v) { field = v; postInvalidate() }
        private var cur: Stroke? = null
        private var curId = -1
        private val box = RectF()
        private val dp = ctx.resources.displayMetrics.density

        private fun fit() {
            val b = shot; val bw = (b?.width ?: 304).toFloat(); val bh = (b?.height ?: 224).toFloat()
            val k = minOf(width / bw, height / bh)
            box.set((width - bw * k) / 2, (height - bh * k) / 2, (width + bw * k) / 2, (height + bh * k) / 2)
        }

        override fun onDraw(c: Canvas) {
            fit()
            c.drawColor(Color.BLACK)
            shot?.let { c.drawBitmap(it, null, box, Paint().apply { isFilterBitmap = false }) }
            c.save(); c.clipRect(box); draw(c, strokes, box); c.restore()
        }

        override fun onTouchEvent(e: MotionEvent): Boolean {
            fit()
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> if (cur == null) {
                    val i = e.actionIndex; curId = e.getPointerId(i)
                    // thick on a phone: 7 dp on screen, kept as a fraction of the picture's width
                    cur = Stroke(color, 7 * dp / box.width()).also { strokes.add(it); it.add(fx(e.getX(i)), fy(e.getY(i))) }
                    invalidate()
                }
                MotionEvent.ACTION_MOVE -> cur?.let { s ->
                    val i = e.findPointerIndex(curId); if (i < 0) return true
                    for (h in 0 until e.historySize) s.add(fx(e.getHistoricalX(i, h)), fy(e.getHistoricalY(i, h)))
                    s.add(fx(e.getX(i)), fy(e.getY(i))); invalidate()
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { cur = null; curId = -1 }
                MotionEvent.ACTION_POINTER_UP -> if (e.getPointerId(e.actionIndex) == curId) { cur = null; curId = -1 }
            }
            return true
        }
        private fun fx(x: Float) = ((x - box.left) / box.width()).coerceIn(0f, 1f)
        private fun fy(y: Float) = ((y - box.top) / box.height()).coerceIn(0f, 1f)

        fun undo() { if (strokes.isNotEmpty()) strokes.removeAt(strokes.size - 1); cur = null; invalidate() }
        fun clear() { strokes.clear(); cur = null; invalidate() }
    }
}
