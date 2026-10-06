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
                r.onFailure { status.text = "${it.message} (v$running, ${key}). Press Next or ✕." }
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
                if (code != 0) { status.text = "This state does not load here (code $code): another core build. Press Next."; return@runOnUiThread }
                t0 = android.os.SystemClock.uptimeMillis()
                if (play) { e.paused = false; status.text = "Playing: do it, then 👍 or 👎"; playBtn.text = "Pause" }
                else { status.text = "Paused: read, then Play"; playBtn.text = "▶ Play" }
            } }
    }

    private fun banner(n: JSONObject, st: String) {
        banner?.let { root.removeView(it) }
        val sc = n.optJSONObject("scenario") ?: JSONObject()
        val b = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; val m = (8 * dp).toInt(); setPadding(m, m, m, m)
            background = GradientDrawable().apply { setColor(Color.argb(235, 0, 0, 0)); setStroke((2 * dp).toInt(), Color.WHITE) }
            isClickable = true }
        fun tv(t: String, size: Float, bold: Boolean = false) = TextView(act).apply { text = t; textSize = size; setTextColor(Color.WHITE)
            if (bold) setTypeface(typeface, Typeface.BOLD) }
        b.addView(tv("TEST ${i + 1} of ${queue.size}: " + sc.optString("title", n.optString("title")), 16f, true))
        b.addView(tv("Do: " + sc.optString("do"), 14f))
        b.addView(tv("Expect: " + sc.optString("expect"), 14f))
        status = tv(st, 13f).apply { alpha = 0.8f }
        b.addView(status)
        val row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL }
        fun btn(t: String, f: () -> Unit) = Button(act).apply { text = t; isAllCaps = false; textSize = 13f; setOnClickListener { f() } }
        playBtn = btn("▶ Play") { val e = emu() ?: return@btn
            if (state == null) return@btn
            if (e.paused) { e.paused = false; playBtn.text = "Pause"; status.text = "Playing: do it, then 👍 or 👎" }
            else { e.paused = true; playBtn.text = "▶ Play"; status.text = "Paused" } }
        row.addView(playBtn, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(btn("Restart") { load(true) }, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(btn("👍 Fixed") { up() }, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(broken(), LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(btn(if (i + 1 < queue.size) "Next" else "Done") { next() }, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(btn("✕") { end() }, LinearLayout.LayoutParams((44 * dp).toInt(), -2))
        b.addView(row)
        root.addView(b, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        banner = b
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
                else { verdict = false; status.text = "Not sent: ${r.exceptionOrNull()?.message}" }
            }
        }.start()
    }

    private fun latestReply(row: JSONObject): Any = row.optInt("last_reply_id", -1).let { if (it < 0) JSONObject.NULL else it }

    /** 👎 Broken: hold = the attempt captured (states + inputs since the scenario state) and the voice recorded */
    private fun broken(): Button {
        val b = Button(act).apply { text = "👎 Broken"; isAllCaps = false; textSize = 13f }
        b.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (state == null) return@setOnTouchListener true
                    val granted = act.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
                    emu()?.paused = true
                    feedback.start(granted || Feedback.testAudio(act) != null)
                    b.text = "● Talk"; status.text = "Recording: say what is still wrong, release to finish"
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (feedback.recording) { val voice = feedback.stop() >= Feedback.MIN_MS; b.text = "👎 Broken"; status.text = "Paused: correct the text, then Send 👎"; composer(voice) }
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
        banner?.let { root.removeView(it) }; banner = null
        emu()?.let { it.resetReq = true; it.paused = false }       // back to the game: a soft reset
        onEnd()
    }
}
