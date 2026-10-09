package com.neoscan.player

import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.io.File

/** The notes waiting to be tested, handed from the list (FeedbackListActivity) to the game screen (MainActivity.onResume). */
object TestQueue {
    @Volatile var pending: List<JSONObject>? = null
}

/** VERIFY mode (Player 0.0.22, docs/feedback.md "Scenarios"): a note's test scenario (tools/brawler/scenario.py: a save
 *  state made on the build he runs, for his system) loaded in place of the game, paused, under a banner with its title,
 *  "Do: ..." and "Expect: ...". Buttons: Play / Pause, Restart (the state again, at once), 👍 Fixed (status verified),
 *  👎 Broken (hold: his voice records while held, the replay of his attempt since the state is captured; released: the
 *  text to correct, then Send = status reopened with the voice and the replay), Next (the next note of the queue), ✕.
 *  Each attempt goes to ../feedback/test (up / down; abandoned only when he leaves a loaded note without a verdict:
 *  Next / Done / ✕ before 👍 or 👎, once per note, never after a verdict or while one is being sent). A verdict takes
 *  the note out of the queue at once (MainActivity.judged; the server's to_test agrees). Leaving the mode soft-resets
 *  the game. */
class TestMode(private val act: MainActivity, private val root: FrameLayout, private val emu: () -> EmuThread?,
               private val feedback: Feedback, private val rom: File, private val onEnd: () -> Unit) {
    private val dp = act.resources.displayMetrics.density
    private var queue: List<JSONObject> = emptyList()
    private var i = 0
    private var state: File? = null
    private var verdict = false                                     // a 👍 / 👎 was sent (or is being sent) for the note on screen
    private var t0 = 0L
    private var banner: LinearLayout? = null
    private lateinit var status: TextView
    private lateinit var playBtn: Button
    private var box: LinearLayout? = null
    var active = false; private set
    private val running get() = RomFetch.installed(act)
    private val sha get() = Feedback.sha(rom)
    private val key get() = Feedback.systemKey(emu()?.hw ?: "mvs")

    companion object { const val SHOW_MS = 3000L }                     // the banner in full when a test loads, then the pill

    fun start(notes: List<JSONObject>) {
        if (notes.isEmpty()) return
        queue = notes; i = 0; active = true
        show()
    }

    private val note get() = queue[i]
    private fun toast(t: String) = android.widget.Toast.makeText(act, t, android.widget.Toast.LENGTH_LONG).show()

    /** the note i: its state downloaded (cached) and loaded paused, its banner up */
    private fun show() {
        val n = note; verdict = false; state = null
        emu()?.paused = true
        banner(n, "Loading the test state...")
        Thread {
            val r = Feedback.scenarioState(act, n.optString("id"), sha, key)
            act.runOnUiThread {
                r.onFailure { status.text = "${it.message} (v$running, ${key}). Press Next or ✕."; expand(true) }
                r.onSuccess { f -> state = f; load(false) }
            }
        }.start()
    }

    /** the state into the core (between frames), one frame shown, then paused unless [play] */
    private fun load(play: Boolean) {
        val f = state ?: return
        val e = emu() ?: return
        e.paused = true
        e.stateReq = f to { code -> e.stepOne = true
            act.runOnUiThread {
                if (code != 0) { status.text = "This state does not load here (code $code): another core build. Press Next."; expand(true); return@runOnUiThread }
                t0 = android.os.SystemClock.uptimeMillis()
                if (play) { e.paused = false; status.text = "Playing: do it, then 👍 or 👎"; playBtn.text = "\u275A\u275A" }
                else { status.text = "Paused: read, then \u25B6"; playBtn.text = "\u25B6" }
                banner?.let { b -> b.removeCallbacks(autoCollapse); if (expanded) b.postDelayed(autoCollapse, SHOW_MS) }
            } }
    }

    /** 0.0.26: the banner over the picture (Bruno: the Do / Expect box took too much room and could not be hidden).
     *  One line always: the pill "ⓘ TEST n/N: title" and the controls (▶ / ❚❚, ⟲ Restart, 👍, 👎 hold to talk, Next,
     *  ✕). Expanded under it: the title in full, Do, Expect, the status; shown for [SHOW_MS] when a test loads, then
     *  collapsed. A tap on the pill = expand / collapse; expanded the box is ~60 % opaque, the game shows through. The
     *  pill drags to the picture's other edge (top / bottom), kept for the session. */
    private var expanded = true
    private var bottomEdge = false
    private lateinit var details: LinearLayout
    private val autoCollapse = Runnable { if (box == null) expand(false) }

    private fun expand(on: Boolean) {
        val b = banner ?: return
        expanded = on; details.visibility = if (on) View.VISIBLE else View.GONE
        b.background = GradientDrawable().apply { setColor(Color.argb(if (on) 153 else 190, 0, 0, 0))
            setStroke((2 * dp).toInt(), Color.WHITE); cornerRadius = 10 * dp }
    }

    /** the banner inside the picture (portrait: the top of the screen; landscape: between the pad's sides), at its edge */
    private fun place() {
        val b = banner ?: return
        if (root.width == 0) { root.post { place() }; return }
        val pic = Screen.picture(root.width, root.height)
        b.layoutParams = FrameLayout.LayoutParams(pic.width(), -2, Gravity.LEFT or if (bottomEdge) Gravity.BOTTOM else Gravity.TOP).apply {
            leftMargin = pic.left; if (bottomEdge) bottomMargin = root.height - pic.bottom else topMargin = pic.top }
        b.translationY = 0f
    }
    private val relayout = View.OnLayoutChangeListener { _, l, t, r, btm, ol, ot, or_, ob ->
        if (r - l != or_ - ol || btm - t != ob - ot) root.post { place() } }      // rotation: the picture moved

    private fun banner(n: JSONObject, st: String) {
        banner?.let { it.removeCallbacks(autoCollapse); root.removeView(it) }
        root.removeOnLayoutChangeListener(relayout); root.addOnLayoutChangeListener(relayout)
        val sc = n.optJSONObject("scenario") ?: JSONObject()
        val title = sc.optString("title", n.optString("title"))
        val b = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; val m = (4 * dp).toInt(); setPadding(m, m, m, m); isClickable = true }
        fun tv(t: String, size: Float, bold: Boolean = false) = TextView(act).apply { text = t; textSize = size; setTextColor(Color.WHITE)
            setShadowLayer(3f, 0f, 0f, Color.BLACK); if (bold) setTypeface(typeface, Typeface.BOLD) }
        fun btn(t: String, what: String, f: () -> Unit) = Button(act).apply { text = t; contentDescription = what; isAllCaps = false; textSize = 15f
            minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = (40 * dp).toInt(); val p = (6 * dp).toInt(); setPadding(p, 0, p, 0)
            setOnClickListener { f() } }
        val row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val pill = tv("ⓘ TEST ${i + 1}/${queue.size}: $title", 14f, true).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END
            val p = (6 * dp).toInt(); setPadding(p, p, p, p) }
        pill.setOnTouchListener(drag(b))
        row.addView(pill, LinearLayout.LayoutParams(0, -2, 1f))
        playBtn = btn("▶", "Play / pause") { val e = emu() ?: return@btn
            if (state == null) return@btn
            if (e.paused) { e.paused = false; playBtn.text = "❚❚"; status.text = "Playing: do it, then 👍 or 👎" }
            else { e.paused = true; playBtn.text = "▶"; status.text = "Paused" } }
        row.addView(playBtn)
        row.addView(btn("⟲", "Restart") { load(true) })
        row.addView(btn("👍", "Fixed") { up() })
        row.addView(broken())
        row.addView(btn(if (i + 1 < queue.size) "Next" else "Done", "Next test") { next() })
        row.addView(btn("✕", "Leave the tests") { end() })
        b.addView(row, LinearLayout.LayoutParams(-1, -2))
        details = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; val p = (6 * dp).toInt(); setPadding(p, 0, p, p) }
        details.addView(tv(title, 16f, true))
        details.addView(tv("Do: " + sc.optString("do"), 14f))
        details.addView(tv("Expect: " + sc.optString("expect"), 14f))
        status = tv(st, 13f)
        details.addView(status)
        details.addView(tv("👍 = fixed, 👎 = still broken (hold it and talk). Tap ⓘ to hide this; drag ⓘ to the other edge.", 12f).apply { alpha = 0.75f })
        b.addView(details, LinearLayout.LayoutParams(-1, -2))
        root.addView(b)
        banner = b
        place(); expand(true)
    }

    /** the pill: a tap = expand / collapse; a drag moves the banner, released = the nearer edge of the picture */
    private fun drag(b: View) = object : View.OnTouchListener {
        var y0 = 0f; var moved = false
        val slop = android.view.ViewConfiguration.get(act).scaledTouchSlop
        override fun onTouch(v: View, e: MotionEvent): Boolean {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { y0 = e.rawY; moved = false }
                MotionEvent.ACTION_MOVE -> { val dy = e.rawY - y0
                    if (Math.abs(dy) > slop) moved = true
                    if (moved) b.translationY = dy }
                MotionEvent.ACTION_UP -> {
                    if (moved) {
                        val pic = Screen.picture(root.width, root.height)
                        bottomEdge = b.top + b.translationY + b.height / 2f > pic.exactCenterY(); place()
                    } else { b.removeCallbacks(autoCollapse); expand(!expanded); v.performClick() }
                }
                MotionEvent.ACTION_CANCEL -> place()
            }
            return true
        }
    }

    private fun base(result: String) = JSONObject().put("id", note.optString("id")).put("result", result).put("rom_sha", sha)
        .put("game_version", running).put("system", key)
        .put("seconds", if (t0 > 0) (android.os.SystemClock.uptimeMillis() - t0) / 1000.0 else JSONObject.NULL)

    /** 👍: the reply (status verified) and the attempt */
    private fun up() {
        if (state == null) { toast("Nothing loaded to judge"); return }
        emu()?.paused = true
        if (verdict) return
        val id = note.optString("id"); val t = base("up")
        verdict = true; status.text = "Sending 👍..."
        Thread {
            val r = Feedback.reply(act, id, "up", "")
            r.onSuccess { t.put("reply_id", latestReply(it)) }
            val p = Feedback.postTest(act, t, null)
            act.runOnUiThread {
                if (r.isSuccess) { act.judged(id, "verified"); toast("Marked verified fixed" + if (p.isFailure) " (attempt not logged: ${p.exceptionOrNull()?.message})" else ""); next() }
                else { verdict = false; status.text = "Not sent: ${r.exceptionOrNull()?.message}"; expand(true) }
            }
        }.start()
    }

    private fun latestReply(row: JSONObject): Any = row.optInt("last_reply_id", -1).let { if (it < 0) JSONObject.NULL else it }

    /** 👎 Broken: hold = the attempt captured (states + inputs since the scenario state) and the voice recorded */
    private fun broken(): Button {
        val b = Button(act).apply { text = "👎"; contentDescription = "Still broken (hold and talk)"; isAllCaps = false; textSize = 15f
            minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = (40 * dp).toInt(); val p = (6 * dp).toInt(); setPadding(p, 0, p, 0) }
        b.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (state == null) return@setOnTouchListener true
                    val granted = act.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
                    emu()?.paused = true
                    feedback.start(granted || Feedback.testAudio(act) != null)
                    b.text = "●"; status.text = "Recording: say what is still wrong, release to finish"
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (feedback.recording) { val voice = feedback.stop() >= Feedback.MIN_MS; b.text = "👎"; status.text = "Paused: correct the text, then Send 👎"; composer(voice) }
                    v.performClick()
                }
            }
            true
        }
        return b
    }

    private fun composer(voice: Boolean) {
        box?.let { banner?.removeView(it) }
        var raw = ""; var tx = ""
        val c = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(28, 28, 34)) }
        val info = TextView(act).apply { textSize = 13f; setTextColor(Color.WHITE); text = if (voice) "Transcribing..." else "Type what is still wrong (optional)" }
        val edit = EditText(act).apply { minLines = 2; maxLines = 4; setTextColor(Color.WHITE); hint = "What is still wrong"; setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.rgb(60, 60, 70)); val m = (6 * dp).toInt(); setPadding(m, m, m, m)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        val row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(info, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(Button(act).apply { text = "Cancel"; setOnClickListener { feedback.cancel(); banner?.removeView(c); box = null; status.text = "Paused" } })
        row.addView(Button(act).apply { text = "Send 👎"; isAllCaps = false; setOnClickListener {
            isEnabled = false; info.text = "Sending..."; verdict = true
            val text = edit.text.toString().trim()
            val dir = feedback.takeAttempt(text, raw)
            val audio = dir?.listFiles()?.firstOrNull { it.name.startsWith("audio.") }
            val id = note.optString("id"); val t = base("down").put("note", text)
            Thread {
                val r = Feedback.reply(act, id, "down", text, raw, tx, audio)
                r.onSuccess { t.put("reply_id", latestReply(it)) }
                val p = Feedback.postTest(act, t, dir)
                dir?.deleteRecursively()
                act.runOnUiThread {
                    if (r.isSuccess) { act.judged(id, "reopened"); banner?.removeView(c); box = null
                        toast("Reopened: still broken" + if (p.isFailure) " (replay not sent: ${p.exceptionOrNull()?.message})" else ", with your attempt's replay"); next() }
                    else { verdict = false; isEnabled = true; info.text = "Not sent: ${r.exceptionOrNull()?.message}" }
                }
            }.start()
        } })
        c.addView(row); c.addView(edit, LinearLayout.LayoutParams(-1, -2))
        banner?.addView(c); box = c
        if (voice) Thread {
            val r = feedback.transcribe()
            act.runOnUiThread { if (r != null) { raw = r.first; edit.setText(r.first); info.text = "Correct it, then Send" } else info.text = "Transcription unavailable: your voice goes along" }
        }.start()
    }

    /** a note left without a verdict once its state was loaded: logged as abandoned (once: [verdict] then blocks it) */
    private fun leaving() {
        if (verdict || state == null) return
        verdict = true
        val t = base("abandoned")
        Thread { Feedback.postTest(act, t, null) }.start()
    }

    /** Next / Done, or the queue moving on after a verdict; the last note ends the mode (end() logs the abandon) */
    private fun next() {
        if (i + 1 < queue.size) { leaving(); i++; show() } else end()
    }

    fun end() {
        if (!active) return
        leaving(); active = false
        if (feedback.recording) feedback.stop()
        feedback.cancel()
        banner?.let { it.removeCallbacks(autoCollapse); root.removeView(it) }; banner = null
        root.removeOnLayoutChangeListener(relayout)
        emu()?.let { it.resetReq = true; it.paused = false }       // back to the game: a soft reset
        onEnd()
    }
}
