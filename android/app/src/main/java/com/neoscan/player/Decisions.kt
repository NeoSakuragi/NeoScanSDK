package com.neoscan.player

import android.app.Dialog
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import android.os.Build
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection

/** Decisions (Player 0.0.24, docs/feedback.md "Decisions"): a visual choice put to him by the developer (before / after
 *  of a fix, a pick between options, one picture), served in /mine's "reviews" (tools/feedback/server.py). Each one:
 *  the question, its images (full width, nearest-neighbour so game screenshots stay pixel-exact; a tap = full screen
 *  with pinch zoom, pan, double tap, and ◀ ▶ through the decision's images at the same zoom), one big button per answer
 *  (its label = the exact outcome, its effect = what changes in the game), a note (typed or hold-to-talk, transcribed
 *  like a reply). The answer goes to POST ../feedback/review; answered ones move to the Answered filter. */
object Decisions {
    fun isOpen(v: JSONObject) = v.optString("status") == "open"

    /** his answer (blocking): -> the decision as the server now has it, or the error */
    fun answer(ctx: Context, id: Int, answer: String, text: String, raw: String, tx: String, audio: File?): Result<JSONObject> {
        val u = Feedback.url(ctx, "review") ?: return Result.failure(Exception("no server"))
        val body = JSONObject().apply {
            put("id", id); put("answer", answer); put("text", text); put("raw_transcript", raw); put("tx_id", tx)
            put("device", "${Build.MANUFACTURER} ${Build.MODEL}"); put("android", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            if (audio != null) { put("audio_name", audio.name); put("audio_b64", android.util.Base64.encodeToString(audio.readBytes(), android.util.Base64.NO_WRAP)) }
        }.toString().toByteArray()
        return try {
            val c = Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
                connectTimeout = 5000; readTimeout = 30000; requestMethod = "POST"; doOutput = true
                setFixedLengthStreamingMode(body.size); setRequestProperty("Content-Type", "application/json")
                setRequestProperty("X-Install-Id", Feedback.installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
                if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
                outputStream.use { it.write(body) }
            } }
            val code = c.responseCode
            val txt = (if (code == 200) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            if (code == 200) Result.success(JSONObject(txt).getJSONObject("review"))
            else Result.failure(Exception(try { JSONObject(txt).optString("error") } catch (x: Exception) { "HTTP $code" }))
        } catch (x: Exception) { Result.failure(Exception("No connection (${x.message})")) }
    }

    /** an image of a decision (GET ../feedback/mine/review/<id>/<file>), decoded in full (blocking); null = failed */
    fun image(ctx: Context, id: Int, file: String): Bitmap? = try {
        val u = Feedback.url(ctx, "mine/review/$id/$file")
        if (u == null) null else Auth.call(ctx) { tok -> (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 5000; readTimeout = 20000
            setRequestProperty("X-Install-Id", Feedback.installId(ctx)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
        } }.takeIf { it.responseCode == 200 }?.inputStream?.use { BitmapFactory.decodeStream(it) }
    } catch (x: Exception) { null }

    private val pixels = Paint().apply { isFilterBitmap = false; isAntiAlias = false; isDither = false }

    /** a picture at the full width of its column (at most [maxH] tall), scaled nearest-neighbour (the game's pixels stay square and sharp) */
    class PixelView(ctx: Context) : View(ctx) {
        var bitmap: Bitmap? = null
            set(b) { field = b; requestLayout(); invalidate() }
        /** never taller than this (0 = no cap): the whole picture stays on screen in landscape */
        var maxH = 0
        override fun onMeasure(w: Int, h: Int) {
            val b = bitmap
            val bw = b?.width ?: 304; val bh = b?.height ?: 224
            var width = MeasureSpec.getSize(w)
            if (maxH > 0 && width * bh / bw > maxH) width = maxH * bw / bh
            setMeasuredDimension(width, width * bh / bw)
        }
        override fun onDraw(c: Canvas) {
            val b = bitmap
            if (b == null) { c.drawColor(Color.rgb(50, 50, 56)); return }
            c.drawBitmap(b, null, Rect(0, 0, width, height), pixels)
        }
    }

    /** full screen: pinch zoom (up to 16x the fit), pan, double tap = fit / 4x; nearest-neighbour throughout */
    class ZoomView(ctx: Context) : View(ctx) {
        var bitmap: Bitmap? = null
            set(b) { val keep = field != null && b != null && field!!.width == b.width && field!!.height == b.height
                     field = b; if (!keep) fitPending = true; invalidate() }
        private val m = Matrix()
        private var fitPending = true
        private var fit = 1f
        private fun scale(): Float { val v = FloatArray(9); m.getValues(v); return v[Matrix.MSCALE_X] }
        private fun fitNow() {
            val b = bitmap ?: return
            if (width == 0) return
            fit = minOf(width.toFloat() / b.width, height.toFloat() / b.height)
            m.reset(); m.postScale(fit, fit); m.postTranslate((width - b.width * fit) / 2, (height - b.height * fit) / 2); fitPending = false
        }
        private fun clamp() {
            val b = bitmap ?: return
            val v = FloatArray(9); m.getValues(v); val s = v[Matrix.MSCALE_X]
            val bw = b.width * s; val bh = b.height * s
            val tx = if (bw <= width) (width - bw) / 2 else v[Matrix.MTRANS_X].coerceIn(width - bw, 0f)
            val ty = if (bh <= height) (height - bh) / 2 else v[Matrix.MTRANS_Y].coerceIn(height - bh, 0f)
            m.postTranslate(tx - v[Matrix.MTRANS_X], ty - v[Matrix.MTRANS_Y])
        }
        private val sg = ScaleGestureDetector(ctx, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(d: ScaleGestureDetector): Boolean {
                val f = (scale() * d.scaleFactor).coerceIn(fit, fit * 16) / scale()
                m.postScale(f, f, d.focusX, d.focusY); clamp(); invalidate(); return true
            }
        })
        private val gd = GestureDetector(ctx, object : GestureDetector.SimpleOnGestureListener() {
            override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean { m.postTranslate(-dx, -dy); clamp(); invalidate(); return true }
            override fun onDoubleTap(e: MotionEvent): Boolean {
                if (scale() > fit * 1.01f) fitNow() else { val f = 4f; m.postScale(f, f, e.x, e.y); clamp() }
                invalidate(); return true
            }
        })
        override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) { fitPending = true }
        override fun onTouchEvent(e: MotionEvent): Boolean { sg.onTouchEvent(e); gd.onTouchEvent(e); return true }
        override fun onDraw(c: Canvas) {
            c.drawColor(Color.BLACK)
            val b = bitmap ?: return
            if (fitPending) fitNow()
            c.save(); c.concat(m); c.drawBitmap(b, 0f, 0f, pixels); c.restore()
        }
    }

    /** the full-screen viewer over a decision's images ([labels], [bitmaps] in order), opened at [start] */
    fun viewer(ctx: Context, labels: List<String>, bitmaps: List<() -> Bitmap?>, start: Int) {
        val dp = ctx.resources.displayMetrics.density
        val d = Dialog(ctx, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val zoom = ZoomView(ctx)
        val cap = TextView(ctx).apply { textSize = 16f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE); setBackgroundColor(Color.BLACK)
            val p = (10 * dp).toInt(); setPadding(p, p, p, p) }
        var i = start
        fun show() { cap.text = "${i + 1} / ${labels.size}   ${labels[i]}"; zoom.bitmap = bitmaps[i]() }
        val bar = LinearLayout(ctx).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(Color.BLACK) }
        fun btn(t: String, f: () -> Unit) = Button(ctx).apply { text = t; textSize = 18f; isAllCaps = false; setOnClickListener { f() } }
        if (labels.size > 1) bar.addView(btn("◀ Previous") { i = (i - 1 + labels.size) % labels.size; show() }, LinearLayout.LayoutParams(0, -2, 1f))
        bar.addView(btn("✕ Close") { d.dismiss() }, LinearLayout.LayoutParams(0, -2, 1f))
        if (labels.size > 1) bar.addView(btn("Next ▶") { i = (i + 1) % labels.size; show() }, LinearLayout.LayoutParams(0, -2, 1f))
        val col = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.BLACK) }
        col.addView(cap, LinearLayout.LayoutParams(-1, -2))
        col.addView(zoom, LinearLayout.LayoutParams(-1, 0, 1f))
        col.addView(TextView(ctx).apply { text = "Pinch to zoom, drag to move, double tap = fit / 4x"; textSize = 12f; setTextColor(Color.WHITE); gravity = Gravity.CENTER })
        col.addView(bar, LinearLayout.LayoutParams(-1, -2))
        d.setContentView(FrameLayout(ctx).apply { addView(col, FrameLayout.LayoutParams(-1, -1)) })
        show(); d.show()
    }
}
