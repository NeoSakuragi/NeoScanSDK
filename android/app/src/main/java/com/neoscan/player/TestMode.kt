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
        banner(n, tr(R.string.tm_loading))
        Thread {
            val r = Feedback.scenarioState(act, n.optString("id"), sha, key)
            act.runOnUiThread {
                r.onFailure { status.text = tr(R.string.tm_fail, it.message, running, key); expand(true) }
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
                if (code != 0) { status.text = tr(R.string.tm_bad_state, code); expand(true); return@runOnUiThread }
                t0 = android.os.SystemClock.uptimeMillis()
                if (play) { e.paused = false; status.text = tr(R.string.tm_playing); playBtn.text = tr(R.string.tm_pause); expand(false) }
                else { status.text = tr(R.string.tm_paused_read); playBtn.text = tr(R.string.tm_play) }
            } }
    }

    /** The banner over the picture (0.0.26: collapsible, see-through; 0.0.27, Bruno: "the buttons are way too small:
     *  keep the buttons at the END of the feedback, occupying the full width with evenly proportioned buttons (no risk
     *  of mishap)"; "when collapsed, just keep it as a small [i] in the top-left corner of the Neo Geo canvas").
     *  Expanded (~60 % opaque, the game shows through): [i] + "TEST n/N: title", Do, Expect, the status, then the
     *  buttons as the last rows, full width, equal widths: Play, Restart, Next, Leave (48 dp), a gap, then the verdict
     *  row Fixed | Still broken (64 dp, 24 dp apart). The 👎 note box replaces the buttons while open, its own last row
     *  Cancel | Send. Collapsed: only [i] at the picture's top-left corner (the same spot as the expanded banner's
     *  [i]); a tap expands it and pauses the game. Expanded on each load (paused); Play / Restart collapse it so the
     *  game is free. Errors expand it. No drag (the [i] has one fixed spot). */
    private var expanded = true
    private lateinit var details: LinearLayout
    private lateinit var controls: LinearLayout
    private var dot: TextView? = null
    private val pad get() = (6 * dp).toInt()
    private val iSize get() = (34 * dp).toInt()

    private fun expand(on: Boolean) {
        val b = banner ?: return
        expanded = on
        b.visibility = if (on) View.VISIBLE else View.GONE
        dot?.visibility = if (on) View.GONE else View.VISIBLE
        if (on) emu()?.let { e -> if (!e.paused && state != null) { e.paused = true; playBtn.text = tr(R.string.tm_play); status.text = tr(R.string.tm_paused) } }
    }

    /** the banner inside the picture (portrait: the top of the screen; landscape: between the pad's sides), at its top;
     *  the [i] at the picture's top-left corner, where the banner's own [i] sits */
    private fun place() {
        val b = banner ?: return
        if (root.width == 0) { root.post { place() }; return }
        val pic = Screen.picture(root.width, root.height)
        b.layoutParams = FrameLayout.LayoutParams(pic.width(), -2, Gravity.LEFT or Gravity.TOP).apply { leftMargin = pic.left; topMargin = pic.top }
        dot?.layoutParams = FrameLayout.LayoutParams(iSize, iSize, Gravity.LEFT or Gravity.TOP).apply {
            leftMargin = pic.left + pad; topMargin = pic.top + pad }
    }
    private val relayout = View.OnLayoutChangeListener { _, l, t, r, btm, ol, ot, or_, ob ->
        if (r - l != or_ - ol || btm - t != ob - ot) root.post { place() } }      // rotation: the picture moved

    private fun shape(fill: Int, stroke: Int = Color.WHITE, r: Float = 8f) = GradientDrawable().apply {
        setColor(fill); setStroke((2 * dp).toInt(), stroke); cornerRadius = r * dp }

    /** a button for the full-width rows: white bold label, its own fill (grey while pressed) */
    private fun bigButton(t: String, what: String, fill: Int) = Button(act).apply {
        text = t; contentDescription = what; isAllCaps = false; textSize = 16f; setTextColor(Color.WHITE)
        setTypeface(typeface, Typeface.BOLD); minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = 0
        stateListAnimator = null; setPadding(pad, 0, pad, 0); maxLines = 2
        background = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_pressed), shape(Color.rgb(110, 110, 120)))
            addState(intArrayOf(), shape(fill)) } }

    /** a row of equal buttons spanning the width, [gapDp] apart */
    private fun buttonRow(hDp: Int, gapDp: Int, vararg bs: Button) = LinearLayout(act).apply {
        orientation = LinearLayout.HORIZONTAL; isBaselineAligned = false        // a two-line label must not drop its button
        bs.forEachIndexed { k, v -> addView(v, LinearLayout.LayoutParams(0, (hDp * dp).toInt(), 1f).apply {
            if (k > 0) leftMargin = (gapDp * dp).toInt() }) } }

    /** the [i]: collapsed it is all that shows; expanded it heads the banner (a tap collapses) */
    private fun infoButton() = TextView(act).apply {
        text = "i"; textSize = 18f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
        setTypeface(Typeface.SERIF, Typeface.BOLD); contentDescription = tr(R.string.tm_info_cd)
        background = shape(Color.argb(170, 0, 0, 0), Color.WHITE, 6f); isClickable = true }

    private fun banner(n: JSONObject, st: String) {
        banner?.let { root.removeView(it) }; dot?.let { root.removeView(it) }
        root.removeOnLayoutChangeListener(relayout); root.addOnLayoutChangeListener(relayout)
        val sc = n.optJSONObject("scenario") ?: JSONObject()
        val title = sc.optString("title", n.optString("title"))
        val b = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad); isClickable = true
            background = shape(Color.argb(153, 0, 0, 0), Color.WHITE, 10f) }
        fun tv(t: String, size: Float, bold: Boolean = false) = TextView(act).apply { text = t; textSize = size; setTextColor(Color.WHITE)
            setShadowLayer(3f, 0f, 0f, Color.BLACK); if (bold) setTypeface(typeface, Typeface.BOLD) }
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(infoButton().apply { setOnClickListener { expand(false) } }, LinearLayout.LayoutParams(iSize, iSize))
        head.addView(tv(tr(R.string.tm_head, i + 1, queue.size, title), 16f, true).apply { maxLines = 2; ellipsize = android.text.TextUtils.TruncateAt.END
            setPadding(pad * 2, 0, 0, 0) }, LinearLayout.LayoutParams(0, -2, 1f))
        b.addView(head, LinearLayout.LayoutParams(-1, -2))
        details = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, 0) }
        details.addView(tv(tr(R.string.tm_do, sc.optString("do")), 15f))
        details.addView(tv(tr(R.string.tm_expect, sc.optString("expect")), 15f))
        status = tv(st, 14f, true)
        details.addView(status)
        details.addView(tv(tr(R.string.tm_help), 12f).apply { alpha = 0.8f })
        val scroll = object : android.widget.ScrollView(act) {     // the Do / Expect texts scroll: a long recipe must not
            override fun onMeasure(w: Int, h: Int) {               // push the buttons off the screen (Bruno 2026-10-11)
                val cap = (root.height * 0.38f).toInt().coerceAtLeast((120 * dp).toInt())
                super.onMeasure(w, View.MeasureSpec.makeMeasureSpec(cap, View.MeasureSpec.AT_MOST)) } }
        scroll.isFillViewport = false; scroll.isVerticalScrollBarEnabled = true
        scroll.addView(details, android.widget.FrameLayout.LayoutParams(-1, -2))
        b.addView(scroll, LinearLayout.LayoutParams(-1, -2))
        val nav = Color.argb(210, 40, 40, 48)
        playBtn = bigButton(tr(R.string.tm_play), tr(R.string.tm_play_cd), nav).apply { setOnClickListener { val e = emu() ?: return@setOnClickListener
            if (state == null) return@setOnClickListener
            if (e.paused) { e.paused = false; text = tr(R.string.tm_pause); status.text = tr(R.string.tm_playing); expand(false) }
            else { e.paused = true; text = tr(R.string.tm_play); status.text = tr(R.string.tm_paused) } } }
        val restart = bigButton(tr(R.string.tm_restart), tr(R.string.tm_restart_cd), nav).apply { setOnClickListener { load(true) } }
        val nextB = bigButton(tr(if (i + 1 < queue.size) R.string.tm_next else R.string.tm_done), tr(R.string.tm_next_cd), nav).apply { setOnClickListener { next() } }
        val leave = bigButton(tr(R.string.tm_leave), tr(R.string.tm_leave_cd), nav).apply { setOnClickListener { end() } }
        val fixed = bigButton(tr(R.string.act_fixed), tr(R.string.tm_fixed_cd), Color.rgb(20, 105, 45)).apply { setOnClickListener { up() } }
        controls = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL }
        controls.addView(buttonRow(48, 8, playBtn, restart, nextB, leave), LinearLayout.LayoutParams(-1, -2).apply { topMargin = (10 * dp).toInt() })
        controls.addView(buttonRow(64, 24, fixed, broken()), LinearLayout.LayoutParams(-1, -2).apply { topMargin = (16 * dp).toInt() })
        b.addView(controls, LinearLayout.LayoutParams(-1, -2))
        val d = infoButton().apply { setOnClickListener { expand(true) } }
        root.addView(b); root.addView(d)
        banner = b; dot = d
        place(); expand(true)
    }

    private fun base(result: String) = JSONObject().put("id", note.optString("id")).put("result", result).put("rom_sha", sha)
        .put("game_version", running).put("system", key)
        .put("seconds", if (t0 > 0) (android.os.SystemClock.uptimeMillis() - t0) / 1000.0 else JSONObject.NULL)

    /** 👍: the reply (status verified) and the attempt */
    private fun up() {
        if (state == null) { toast(tr(R.string.tm_nothing)); return }
        emu()?.paused = true
        if (verdict) return
        val id = note.optString("id"); val t = base("up")
        verdict = true; status.text = tr(R.string.tm_sending_up)
        Thread {
            val r = Feedback.reply(act, id, "up", "")
            r.onSuccess { t.put("reply_id", latestReply(it)) }
            val p = Feedback.postTest(act, t, null)
            act.runOnUiThread {
                if (r.isSuccess) { act.judged(id, "verified"); toast(tr(R.string.marked_verified) + if (p.isFailure) " " + tr(R.string.tm_attempt_not_logged, p.exceptionOrNull()?.message) else ""); next() }
                else { verdict = false; status.text = tr(R.string.not_sent, r.exceptionOrNull()?.message); expand(true) }
            }
        }.start()
    }

    private fun latestReply(row: JSONObject): Any = row.optInt("last_reply_id", -1).let { if (it < 0) JSONObject.NULL else it }

    /** 👎 Broken: hold = the attempt captured (states + inputs since the scenario state) and the voice recorded */
    private fun broken(): Button {
        val label = tr(R.string.tm_broken)
        val b = bigButton(label, tr(R.string.tm_broken_cd), Color.rgb(140, 25, 25))
        b.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (state == null) return@setOnTouchListener true
                    val granted = act.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
                    emu()?.paused = true
                    feedback.start(granted || Feedback.testAudio(act) != null)
                    b.text = tr(R.string.tm_recording_btn); status.text = tr(R.string.tm_recording)
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (feedback.recording) { val voice = feedback.stop() >= Feedback.MIN_MS; b.text = label; status.text = tr(R.string.tm_paused_correct); composer(voice) }
                    v.performClick()
                }
            }
            true
        }
        return b
    }

    /** the 👎 note box: it takes the buttons' place at the banner's end (the buttons hidden while it is open: one
     *  thing to tap at a time); its own last row Cancel | Send, full width, equal */
    private fun composer(voice: Boolean) {
        box?.let { banner?.removeView(it) }
        var raw = ""; var tx = ""
        val c = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(0, (10 * dp).toInt(), 0, 0) }
        val info = TextView(act).apply { textSize = 14f; setTextColor(Color.WHITE); setTypeface(typeface, Typeface.BOLD)
            text = tr(if (voice) R.string.transcribing else R.string.tm_type_wrong) }
        val edit = EditText(act).apply { minLines = 2; maxLines = 4; setTextColor(Color.WHITE); hint = tr(R.string.tm_wrong_hint); setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.rgb(60, 60, 70)); val m = (6 * dp).toInt(); setPadding(m, m, m, m)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        fun close() { banner?.removeView(c); box = null; controls.visibility = View.VISIBLE }
        val cancel = bigButton(tr(R.string.cancel), tr(R.string.tm_cancel_cd), Color.argb(210, 40, 40, 48)).apply { setOnClickListener { feedback.cancel(); close(); status.text = tr(R.string.tm_paused) } }
        val send = bigButton("\uD83D\uDC4E " + tr(R.string.send_still_broken), tr(R.string.send_still_broken), Color.rgb(140, 25, 25))
        send.setOnClickListener { send.apply {
            isEnabled = false; info.text = tr(R.string.sending); verdict = true
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
                    if (r.isSuccess) { act.judged(id, "reopened"); close()
                        toast(tr(R.string.reopened_broken) + if (p.isFailure) " " + tr(R.string.tm_replay_not_sent, p.exceptionOrNull()?.message) else tr(R.string.tm_with_replay)); next() }
                    else { verdict = false; isEnabled = true; info.text = tr(R.string.not_sent, r.exceptionOrNull()?.message) }
                }
            }.start()
        } }
        c.addView(info); c.addView(edit, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (4 * dp).toInt() })
        c.addView(buttonRow(56, 24, cancel, send), LinearLayout.LayoutParams(-1, -2).apply { topMargin = (12 * dp).toInt() })
        controls.visibility = View.GONE
        banner?.addView(c); box = c; expand(true)
        if (voice) Thread {
            val r = feedback.transcribe()
            act.runOnUiThread { if (r != null) { raw = r.first; edit.setText(r.first); info.text = tr(R.string.tm_correct_send) } else info.text = tr(R.string.tm_tx_unavail) }
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
        banner?.let { root.removeView(it) }; banner = null; dot?.let { root.removeView(it) }; dot = null
        root.removeOnLayoutChangeListener(relayout)
        emu()?.let { it.resetReq = true; it.paused = false }       // back to the game: a soft reset
        onEnd()
    }
}
