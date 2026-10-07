package com.neoscan.player

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.media.MediaPlayer
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/** His feedback notes (Player 0.0.15, from the settings): GET <ROM base>/../feedback/mine with his token
 *  (tools/feedback/server.py: the signed-in account's notes, newest first, each with its status history). Each card:
 *  the date, the versions, the note as sent, category + fighters, the status (shipped with its release, duplicate
 *  with the other note), the developer's notes, the history, the screenshot (the marked one when he drew on it; tap =
 *  full screen) and the voice (play / stop). Pull down (or the Refresh button) to load again. Built in code, no libraries.
 *  0.0.17: the build he runs at the top; filters Open (not shipped / won't do / duplicate / verified), "Shipped: test
 *  it" (shipped in a build at or before the one he runs) and All; per note its reply thread and three actions:
 *  thumbs up (verified fixed: status verified), thumbs down (still broken: status reopened, with an optional reply)
 *  and Reply (hold to talk: recorded, transcribed, editable; or typed), all POSTed to ../feedback/reply. */
class FeedbackListActivity : Activity() {
    private val dp get() = resources.displayMetrics.density
    private lateinit var list: LinearLayout
    private lateinit var head: TextView
    private lateinit var scroll: PullScroll
    private var player: MediaPlayer? = null
    private var playing: Button? = null
    private val images = HashMap<String, Bitmap>()
    private var rows = org.json.JSONArray()
    private var user = ""
    private var filter = "open"                                        // open | ready | all | decisions | answered (0.0.24)
    private var reviews = org.json.JSONArray()                         // 0.0.24: the decisions put to him (Decisions.kt)
    private val decImages = HashMap<String, Bitmap>()
    private lateinit var filters: LinearLayout
    private val running get() = RomFetch.installed(this)
    private var rec: Feedback.VoiceRec? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; val m = (14 * dp).toInt(); setPadding(m, 0, m, m * 2) }
        head = TextView(this).apply { gravity = Gravity.CENTER; textSize = 13f; alpha = 0.7f; height = 0; text = "Release to refresh" }
        col.addView(head, LinearLayout.LayoutParams(-1, -2))
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (12 * dp).toInt(), 0, 0) }
        top.addView(TextView(this).apply { text = "My feedback"; textSize = 24f; setTypeface(typeface, Typeface.BOLD) }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(Button(this).apply { text = "Refresh"; setOnClickListener { load() } })
        col.addView(top)
        col.addView(TextView(this).apply { textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0)
            text = "You run game v$running (build ${RomFetch.loadedBuild(this@FeedbackListActivity).let { if (it == 0L) "local" else "$it" }}), player ${BuildConfig.VERSION_NAME}" })
        filter = intent.getStringExtra("filter") ?: getSharedPreferences("feedback", 0).getString("listFilter", "open") ?: "open"
        filters = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, (6 * dp).toInt(), 0, (6 * dp).toInt()) }
        col.addView(filters)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(list, LinearLayout.LayoutParams(-1, -2))
        scroll = PullScroll().apply { addView(col) }
        setContentView(scroll)
        load()
    }

    override fun onDestroy() { player?.release(); player = null; rec?.clear(); super.onDestroy() }

    /** pull down at the top: the header grows ("Release to refresh"); released far enough = [load] */
    private inner class PullScroll : ScrollView(this@FeedbackListActivity) {
        private var y0 = -1f
        private val need = 70 * dp
        override fun dispatchTouchEvent(e: MotionEvent): Boolean {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> y0 = if (scrollY == 0) e.y else -1f
                MotionEvent.ACTION_MOVE -> if (y0 >= 0 && scrollY == 0) {
                    val d = ((e.y - y0) / 2).coerceIn(0f, need * 1.5f)
                    head.height = d.toInt(); head.text = if (d >= need) "Release to refresh" else "Pull to refresh"
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (head.height >= need && e.actionMasked == MotionEvent.ACTION_UP) load()
                    head.height = 0; y0 = -1f
                }
            }
            return super.dispatchTouchEvent(e)
        }
    }

    private fun msg(t: String) { list.removeAllViews(); list.addView(TextView(this).apply { text = t; textSize = 15f; setPadding(0, (24 * dp).toInt(), 0, 0) }) }

    private fun get(path: String): HttpURLConnection? {
        val u = Feedback.url(this, path) ?: return null
        return Auth.call(this) { tok -> (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 5000; readTimeout = 20000
            setRequestProperty("X-Install-Id", Feedback.installId(this@FeedbackListActivity)); setRequestProperty("X-App-Version", BuildConfig.VERSION_NAME)
            if (tok != null) setRequestProperty("Authorization", "Bearer $tok")
        } }
    }

    private fun load() {
        if (list.childCount == 0) msg("Loading...")
        Thread {
            val r = Feedback.mine(this)
            if (romFile.exists()) romSha = Feedback.sha(romFile)
            runOnUiThread {
                r.onFailure { msg(it.message ?: "?") }
                r.onSuccess { j -> rows = j.getJSONArray("rows"); reviews = j.optJSONArray("reviews") ?: org.json.JSONArray(); user = j.optString("user"); render() }
            }
        }.start()
    }

    private fun matches(r: JSONObject, f: String) = when (f) {
        "open" -> Feedback.isOpen(r); "ready" -> Feedback.wantsTest(r, running); else -> true }
    private val decisions get() = (0 until reviews.length()).map { reviews.getJSONObject(it) }

    /** the filter buttons (with their counts) and the cards they keep; the scroll position stays */
    private fun render() {
        val y = scroll.scrollY
        filters.removeAllViews()
        val nOpen = decisions.count { Decisions.isOpen(it) }
        for (row in listOf(listOf("open" to "Open", "ready" to "Shipped: test it", "all" to "All"),
                           listOf("decisions" to "Decisions to answer", "answered" to "Answered"))) {
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for ((k, t) in row) {
                val n = when (k) { "decisions" -> nOpen; "answered" -> decisions.size - nOpen; else -> (0 until rows.length()).count { matches(rows.getJSONObject(it), k) } }
                line.addView(Button(this).apply {
                    text = (if (filter == k) "● " else "") + "$t ($n)"; isAllCaps = false; setTypeface(typeface, if (filter == k) Typeface.BOLD else Typeface.NORMAL)
                    setOnClickListener { filter = k; getSharedPreferences("feedback", 0).edit().putString("listFilter", k).apply(); render(); scroll.scrollTo(0, 0) }
                }, LinearLayout.LayoutParams(0, -2, 1f))
            }
            filters.addView(line, LinearLayout.LayoutParams(-1, -2))
        }
        list.removeAllViews()
        if (filter == "decisions" || filter == "answered") {
            val shown = decisions.filter { Decisions.isOpen(it) == (filter == "decisions") }
            list.addView(TextView(this).apply { textSize = 13f; alpha = 0.7f; setPadding(0, (4 * dp).toInt(), 0, (8 * dp).toInt())
                text = if (filter == "decisions") "$user: ${shown.size} decision" + (if (shown.size == 1) "" else "s") + " waiting for your answer"
                       else "$user: ${shown.size} answered, newest first (you can change an answer)" })
            if (shown.isEmpty()) list.addView(TextView(this).apply { textSize = 15f; setPadding(0, (16 * dp).toInt(), 0, 0)
                text = if (filter == "decisions") "Nothing to decide right now." else "No answered decisions yet." })
            for (v in shown) list.addView(decisionCard(v))
            scroll.post { scroll.scrollTo(0, y) }
            return
        }
        val shown = (0 until rows.length()).map { rows.getJSONObject(it) }.filter { matches(it, filter) }
        list.addView(TextView(this).apply { text = "$user: ${shown.size} of ${rows.length()} note" + (if (rows.length() == 1) "" else "s") + ", newest first"
            textSize = 13f; alpha = 0.7f; setPadding(0, (4 * dp).toInt(), 0, (8 * dp).toInt()) })
        val q = (0 until rows.length()).map { rows.getJSONObject(it) }.filter { Feedback.wantsTest(it, running) && testable(it) }.reversed()
        if (q.isNotEmpty()) list.addView(Button(this).apply { text = "▶ Test queue (${q.size}): test each fixed note in turn"; isAllCaps = false
            setOnClickListener { verify(q) } }, LinearLayout.LayoutParams(-1, -2))
        if (rows.length() == 0) msg("No notes yet: hold the mic button in the game and talk, or tap it to type.")
        else if (shown.isEmpty()) list.addView(TextView(this).apply { textSize = 15f; setPadding(0, (16 * dp).toInt(), 0, 0)
            text = if (filter == "ready") "Nothing shipped to test in v$running." else "No open notes." })
        for (r in shown) list.addView(card(r))
        scroll.post { scroll.scrollTo(0, y) }
    }

    /** a decision (0.0.24): title / "asked 3 h ago" + status / the question / what each answer changes / the images
     *  (full width, pixel-exact; tap = full screen with zoom) / the answer buttons, the note (typed or hold to talk);
     *  answered: his answer, note and voice, with "Change my answer" */
    private fun decisionCard(v: JSONObject): View {
        val id = v.optInt("id")
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; val m = (12 * dp).toInt(); setPadding(m, m, m, m)
            background = GradientDrawable().apply { setColor(Color.rgb(30, 30, 36)); setStroke(maxOf(2, (2 * dp).toInt()), Color.WHITE); cornerRadius = 8 * dp }
        }
        c.addView(TextView(this).apply { text = "DECISION #$id: " + v.optString("title"); textSize = 15f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE) })
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (2 * dp).toInt(), 0, (6 * dp).toInt()) }
        top.addView(TextView(this).apply { text = "asked ${Feedback.ago(v.optString("created"))}" + v.optString("todo").let { if (it.isEmpty()) "" else ", TODO #$it" }; textSize = 13f; alpha = 0.8f },
            LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(TextView(this).apply {
            text = if (Decisions.isOpen(v)) "WAITING FOR YOU" else "ANSWERED"; textSize = 12f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
            val m = (5 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
            background = GradientDrawable().apply { setStroke(maxOf(2, (1.5f * dp).toInt()), Color.WHITE); cornerRadius = 4 * dp }
        })
        c.addView(top)
        c.addView(TextView(this).apply { text = v.optString("question"); textSize = 21f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE); setPadding(0, 0, 0, (6 * dp).toInt()) })
        val opts = v.optJSONArray("options") ?: org.json.JSONArray()
        val labels = (0 until opts.length()).map { opts.getJSONObject(it).optString("label") }
        c.addView(small("What each answer does:").apply { setTypeface(typeface, Typeface.BOLD) })
        for (k in 0 until opts.length()) { val o = opts.getJSONObject(k)
            c.addView(TextView(this).apply { text = "• ${o.optString("label")}: ${o.optString("effect")}"; textSize = 14f; setPadding(0, (2 * dp).toInt(), 0, 0) }) }
        // the images: full width, each under its label
        val imgs = v.optJSONArray("images") ?: org.json.JSONArray()
        val names = (0 until imgs.length()).map { imgs.getJSONObject(it).optString("file") }
        val caps = (0 until imgs.length()).map { imgs.getJSONObject(it).optString("label") }
        // landscape: a before / after decision shows each pair side by side; every picture stays within the screen's height
        val dm = resources.displayMetrics
        val perRow = if (v.optString("kind") == "before_after" && dm.widthPixels > dm.heightPixels) 2 else 1
        for (k0 in names.indices step perRow) {
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, ((if (perRow == 2 || k0 % 2 == 0) 14 else 8) * dp).toInt(), 0, 0) }
            for (k in k0 until minOf(k0 + perRow, names.size)) {
                val cell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; if (k > k0) setPadding((8 * dp).toInt(), 0, 0, 0) }
                cell.addView(TextView(this).apply { text = caps[k]; textSize = 15f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE); setPadding(0, 0, 0, (3 * dp).toInt()) })
                val pv = Decisions.PixelView(this).apply { contentDescription = caps[k]; maxH = (dm.heightPixels * 0.72f).toInt(); setOnClickListener {
                    Decisions.viewer(this@FeedbackListActivity, caps, names.map { n -> { decImages["$id/$n"] } }, k) } }
                cell.addView(pv, LinearLayout.LayoutParams(-1, -2))
                decImage(id, names[k], pv)
                line.addView(cell, LinearLayout.LayoutParams(0, -2, 1f))
            }
            if (perRow == 2 && k0 + 1 >= names.size) line.addView(View(this), LinearLayout.LayoutParams(0, 0, 1f))
            c.addView(line, LinearLayout.LayoutParams(-1, -2))
        }
        c.addView(small("Tap a picture: full screen, pinch to zoom, ◀ ▶ to flip between them").apply { setPadding(0, (4 * dp).toInt(), 0, 0) })
        val answerBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (!Decisions.isOpen(v)) {
            c.addView(TextView(this).apply { text = "Your answer: ${v.optString("answer")}"; textSize = 18f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
                setPadding(0, (12 * dp).toInt(), 0, 0) })
            c.addView(small("${Feedback.ago(v.optString("answered_at"))} (${Feedback.local(v.optString("answered_at"))}), from the ${v.optString("answer_source")}"))
            v.optString("answer_text").takeIf { it.isNotEmpty() }?.let { c.addView(TextView(this).apply { text = "Your note: $it"; textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0) }) }
            v.optString("answer_audio").takeIf { it.isNotEmpty() }?.let { a -> c.addView(Button(this).apply { text = "▶ Voice"; setOnClickListener { play(this, "mine/review/$id/$a") } }, LinearLayout.LayoutParams(-2, -2)) }
            c.addView(Button(this).apply { text = "Change my answer"; isAllCaps = false; setOnClickListener { visibility = View.GONE; answerer(answerBox, id, labels, opts) } },
                LinearLayout.LayoutParams(-1, -2).apply { topMargin = (8 * dp).toInt() })
        } else answerer(answerBox, id, labels, opts)
        c.addView(answerBox)
        return LinearLayout(this).apply { setPadding(0, 0, 0, (14 * dp).toInt()); addView(c, LinearLayout.LayoutParams(-1, -2)) }
    }

    /** the answer: the note first (optional, required for a "Needs work" answer), then one big button per answer */
    private fun answerer(box: LinearLayout, id: Int, labels: List<String>, opts: org.json.JSONArray) {
        box.removeAllViews()
        var raw = ""; var tx = ""
        val r = Feedback.VoiceRec(this)
        val info = small("Your note (optional; needed for \"Needs work\"): hold to talk or type").apply { setPadding(0, (12 * dp).toInt(), 0, 0) }
        val edit = android.widget.EditText(this).apply { minLines = 2; maxLines = 6; gravity = Gravity.TOP or Gravity.START; hint = "Your note"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        val mic = Button(this).apply { text = "🎤 Hold to talk"; isAllCaps = false }
        mic.setOnTouchListener { vv, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED && Feedback.testAudio(this) == null) {
                        requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 2); return@setOnTouchListener true }
                    rec?.clear(); rec = r
                    if (r.start()) { mic.text = "● Recording: release to stop"; info.text = "Recording..." } else info.text = "The microphone is unavailable"
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    mic.text = "🎤 Hold to talk"
                    val f = r.stop()
                    if (f == null) info.text = "Too short: hold the button while you talk"
                    else { info.text = "Transcribing..."
                        Thread { val t = Feedback.transcribeFile(this, f)
                            runOnUiThread {
                                if (t == null) info.text = "Transcription unavailable: your voice goes with the answer"
                                else { raw = t.first; tx = t.third; info.text = "Correct or add to it, then pick your answer"
                                    edit.setText((edit.text.toString().trim() + " " + t.first).trim()); edit.setSelection(edit.text.length) }
                            } }.start() }
                    vv.performClick()
                }
            }
            true
        }
        box.addView(info); box.addView(mic, LinearLayout.LayoutParams(-1, -2)); box.addView(edit, LinearLayout.LayoutParams(-1, -2))
        box.addView(small("Your answer:").apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (8 * dp).toInt(), 0, 0) })
        for (k in labels.indices) {
            val label = labels[k]; val effect = opts.getJSONObject(k).optString("effect")
            box.addView(Button(this).apply {
                text = label; textSize = 17f; isAllCaps = false; minHeight = (64 * dp).toInt(); setTypeface(typeface, Typeface.BOLD)
                setOnClickListener {
                    val note = edit.text.toString().trim(); val a = r.file
                    if (label.lowercase().startsWith("needs work") && note.isEmpty()) { info.text = "\"$label\" needs your note: say or type what to change"; toast(info.text.toString()); return@setOnClickListener }
                    android.app.AlertDialog.Builder(this@FeedbackListActivity).setTitle(label)
                        .setMessage("$effect" + (if (note.isNotEmpty()) "\n\nYour note: $note" else "") + (if (a != null) "\n\n(with your voice)" else ""))
                        .setPositiveButton("Send this answer") { _, _ ->
                            info.text = "Sending..."
                            Thread { val res = Decisions.answer(this@FeedbackListActivity, id, label, note, raw, tx, a)
                                runOnUiThread {
                                    res.onSuccess { r.clear(); toast("Answer sent: $label"); load() }
                                    res.onFailure { info.text = "Not sent: ${it.message}"; toast("Not sent: ${it.message}") }
                                } }.start()
                        }.setNegativeButton("Back", null).show()
                }
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = (6 * dp).toInt() })
        }
    }

    /** a decision's image, decoded in full (game screenshots are small; nearest-neighbour scaling needs every pixel) */
    private fun decImage(id: Int, name: String, pv: Decisions.PixelView) {
        val k = "$id/$name"
        decImages[k]?.let { pv.bitmap = it; return }
        Thread { val b = Decisions.image(this, id, name); if (b != null) runOnUiThread { decImages[k] = b; pv.bitmap = b } }.start()
    }

    private fun when_(iso: String) = Feedback.local(iso)

    private fun statusText(r: JSONObject): String = when (val s = r.optString("status")) {
        "shipped" -> "SHIPPED " + r.optString("release")
        "duplicate" -> "DUPLICATE of " + r.optString("duplicate_of")
        "wont_do" -> "WON'T DO"
        "in_progress" -> "IN PROGRESS"
        "verified" -> "VERIFIED FIXED"
        "reopened" -> "REOPENED"
        else -> s.uppercase()
    }

    /** the build he runs (its sha) and his system: which notes have a test state for him (0.0.22) */
    private val romFile by lazy { java.io.File(getExternalFilesDir(null), "brawler.neo") }
    private var romSha = ""
    private val sysKey get() = Feedback.systemKey(if (Prefs(this).system == "console") "aes" else "mvs")
    private fun testable(r: JSONObject) = romSha.isNotEmpty() && Feedback.testable(r, romSha, sysKey)
    /** VERIFY mode on these notes: back to the game, which loads the first one's state under the banner */
    private fun verify(notes: List<JSONObject>) { TestQueue.pending = notes; finish() }

    /** Bruno's card (0.0.22): title / "44 min ago on 0.0.17" / the screenshot (tap = verify it; "no test yet" = full
     *  screen) / [FIX 0.0.78] / the fix and its root cause / More (collapsed: his latest reply, the note, the voice, the
     *  timeline, the origin) / Fixed - Broken - Reply */
    private fun card(r: JSONObject): View {
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; val m = (12 * dp).toInt(); setPadding(m, m, m, m)
            background = GradientDrawable().apply { setColor(Color.rgb(30, 30, 36)); setStroke(maxOf(1, dp.toInt()), Color.rgb(90, 90, 100)); cornerRadius = 8 * dp }
        }
        val id = r.optString("id")
        val text = r.optString("final_text").ifEmpty { r.optString("raw_transcript") }
        val title = r.optString("title").takeIf { it.isNotEmpty() && it != "null" } ?: text.take(70).ifEmpty { "(no text)" }
        c.addView(TextView(this).apply { this.text = title; textSize = 18f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE) })
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (2 * dp).toInt(), 0, (6 * dp).toInt()) }
        top.addView(TextView(this).apply { this.text = "${Feedback.ago(r.optString("created"))} on ${r.optString("game_version")}"; textSize = 14f; alpha = 0.8f
            setOnLongClickListener { toast(when_(r.optString("created")) + "  (game v${r.optString("game_version")}, player ${r.optString("apk_version")})"); true } },
            LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(TextView(this).apply {                          // the status: a bordered label, the word itself carries it
            this.text = statusText(r); textSize = 12f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
            val m = (5 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
            background = GradientDrawable().apply { setStroke(maxOf(2, (1.5f * dp).toInt()), Color.WHITE); cornerRadius = 4 * dp }
        })
        c.addView(top)
        val shot = r.optString("screen")
        val can = testable(r)
        if (shot.isNotEmpty()) {
            val frame = android.widget.FrameLayout(this)
            val iv = ImageView(this).apply { adjustViewBounds = true; scaleType = ImageView.ScaleType.FIT_START; maxWidth = (420 * dp).toInt()
                contentDescription = if (can) "verify this note" else "screenshot" }
            frame.addView(iv, android.widget.FrameLayout.LayoutParams(minOf((420 * dp).toInt(), resources.displayMetrics.widthPixels - (60 * dp).toInt()), -2))
            frame.addView(TextView(this).apply { this.text = if (can) "▶ TEST IT" else "no test yet"; textSize = if (can) 15f else 11f
                setTypeface(typeface, Typeface.BOLD); setTextColor(if (can) Color.BLACK else Color.WHITE)
                val m = (6 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
                background = GradientDrawable().apply { setColor(if (can) Color.WHITE else Color.argb(200, 0, 0, 0)); setStroke((1.5f * dp).toInt(), if (can) Color.BLACK else Color.WHITE); cornerRadius = 4 * dp }
            }, android.widget.FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.START).apply { val m = (6 * dp).toInt(); setMargins(m, m, m, m) })
            image(id, shot, iv)
            frame.setOnClickListener { if (can) verify(listOf(r)) else full(id, shot) }
            c.addView(frame, LinearLayout.LayoutParams(-2, -2))
        } else if (can) c.addView(Button(this).apply { this.text = "▶ TEST IT"; setOnClickListener { verify(listOf(r)) } })
        val rel = r.optString("release")
        if (rel.isNotEmpty() && r.optString("status") in setOf("shipped", "verified", "reopened")) c.addView(TextView(this).apply {
            this.text = "[FIX $rel]"; textSize = 14f; setTypeface(Typeface.MONOSPACE, Typeface.BOLD); setTextColor(Color.WHITE); setPadding(0, (8 * dp).toInt(), 0, 0) })
        r.optString("fix").takeIf { it.isNotEmpty() && it != "null" }?.let { c.addView(TextView(this).apply { this.text = "Fix: $it"; textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0) }) }
        r.optString("rca").takeIf { it.isNotEmpty() && it != "null" }?.let { c.addView(TextView(this).apply { this.text = "Cause: $it"; textSize = 14f; alpha = 0.85f; setPadding(0, (2 * dp).toInt(), 0, 0) }) }
        // More (collapsed): his latest reply, the note as sent, the voice, the timeline, the origin
        val more = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        val open = expanded.contains(id)
        if (open) more.visibility = View.VISIBLE
        c.addView(Button(this).apply { this.text = if (open) "▲ Less" else "▼ More"; isAllCaps = false; setOnClickListener {
            if (more.visibility == View.GONE) { more.visibility = View.VISIBLE; this.text = "▲ Less"; expanded.add(id) }
            else { more.visibility = View.GONE; this.text = "▼ More"; expanded.remove(id) } } },
            LinearLayout.LayoutParams(-2, -2).apply { topMargin = (6 * dp).toInt() })
        val rep = r.optJSONArray("replies")
        val last = rep?.let { a -> (a.length() - 1 downTo 0).map { a.getJSONObject(it) }.firstOrNull { it.optString("text").isNotEmpty() } }
        if (last != null) more.addView(TextView(this).apply { this.text = "Your latest reply (${Feedback.ago(last.optString("at"))}): ${last.optString("text")}"; textSize = 14f })
        more.addView(TextView(this).apply { this.text = "Your note: " + text.ifEmpty { "(no text)" }; textSize = 14f; setPadding(0, (6 * dp).toInt(), 0, 0) })
        val tags = listOfNotNull(r.optString("category").ifEmpty { null }?.let { "category: $it" }, r.optString("fighters").ifEmpty { null }?.let { "fighters: $it" })
        if (tags.isNotEmpty()) more.addView(small(tags.joinToString("   ")))
        if (r.optString("notes").isNotEmpty()) more.addView(small("Developer's notes: " + r.optString("notes")))
        val audio = r.optString("audio_path")
        if (audio.isNotEmpty()) more.addView(Button(this).apply { this.text = "▶ Voice"; setOnClickListener { play(this, id, audio) } }, LinearLayout.LayoutParams(-2, -2))
        if (rep != null) for (k in 0 until rep.length()) { val x = rep.getJSONObject(k); val a = x.optString("audio_path")
            if (a.isNotEmpty()) more.addView(Button(this).apply { this.text = "▶ Reply voice ${Feedback.ago(x.optString("at"))}"; isAllCaps = false; setOnClickListener { play(this, id, a) } }, LinearLayout.LayoutParams(-2, -2)) }
        val tl = r.optJSONArray("timeline")
        if (tl != null && tl.length() > 0) {
            more.addView(small("Timeline").apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (8 * dp).toInt(), 0, 0) })
            for (k in 0 until tl.length()) { val e = tl.getJSONObject(k)
                more.addView(small("${when_(e.optString("at"))}  ${e.optString("kind").replace('_', ' ').uppercase()}  ${e.optString("text")}  (${e.optString("by")})")) }
        }
        more.addView(small("sent from ${r.optString("device").ifEmpty { "?" }}" + r.optString("android").let { if (it.isEmpty() || it == "null") "" else ", Android $it" } +
                           ", IP ${r.optString("ip").ifEmpty { "?" }.replace("null", "?")}, player ${r.optString("apk_version")}, install ${r.optString("install_id").take(8)}").apply { setPadding(0, (8 * dp).toInt(), 0, 0) })
        c.addView(more)
        thread(c, r)
        return LinearLayout(this).apply { setPadding(0, 0, 0, (12 * dp).toInt()); addView(c, LinearLayout.LayoutParams(-1, -2)) }
    }
    private val expanded = HashSet<String>()

    /** the note's actions: Fixed / Broken / Reply */
    private fun thread(c: LinearLayout, r: JSONObject) {
        val id = r.optString("id")
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val acts = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, (8 * dp).toInt(), 0, 0) }
        fun act(t: String, f: () -> Unit) = Button(this).apply { text = t; isAllCaps = false; setOnClickListener { f() } }
        acts.addView(act("👍 Fixed") {
            android.app.AlertDialog.Builder(this).setMessage("Verified fixed in v$running?")
                .setPositiveButton("Yes, fixed") { _, _ -> send(id, "up", "", "", "", null) }.setNegativeButton("No", null).show()
        }, LinearLayout.LayoutParams(0, -2, 1f))
        acts.addView(act("👎 Broken") { composer(box, id, true) }, LinearLayout.LayoutParams(0, -2, 1f))
        acts.addView(act("Reply") { composer(box, id, false) }, LinearLayout.LayoutParams(0, -2, 1f))
        c.addView(acts); c.addView(box)
    }

    /** the reply box under a note: hold to talk (recorded, transcribed, the text editable) or type; [down] = the thumbs
     *  down with an optional reply */
    private fun composer(box: LinearLayout, id: String, down: Boolean) {
        rec?.clear(); box.removeAllViews()
        var raw = ""; var tx = ""
        val r = Feedback.VoiceRec(this).also { rec = it }
        val info = small(if (down) "Still broken: say or type what you see (optional), then Send" else "Hold to talk, or type, then Send")
        val edit = android.widget.EditText(this).apply { minLines = 2; maxLines = 6; gravity = Gravity.TOP or Gravity.START
            hint = if (down) "What is still wrong (optional)" else "Your reply"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        val mic = Button(this).apply { text = "🎤 Hold to talk"; isAllCaps = false }
        mic.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED && Feedback.testAudio(this) == null) {
                        requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 2); return@setOnTouchListener true }
                    if (r.start()) { mic.text = "● Recording: release to stop"; info.text = "Recording..." } else info.text = "The microphone is unavailable"
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    mic.text = "🎤 Hold to talk"
                    val f = r.stop()
                    if (f == null) info.text = "Too short: hold the button while you talk"
                    else {
                        info.text = "Transcribing..."
                        Thread {
                            val t = Feedback.transcribeFile(this, f)
                            runOnUiThread {
                                if (t == null) info.text = "Transcription unavailable: your voice goes with the reply"
                                else { raw = t.first; tx = t.third; info.text = "Correct or add to it, then Send"
                                    edit.setText((edit.text.toString().trim() + " " + t.first).trim()); edit.setSelection(edit.text.length) }
                            }
                        }.start()
                    }
                    v.performClick()
                }
            }
            true
        }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(mic, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(Button(this).apply { text = "Cancel"; setOnClickListener { r.clear(); box.removeAllViews() } })
        row.addView(Button(this).apply { text = if (down) "Send: still broken" else "Send"; isAllCaps = false; setOnClickListener {
            val text = edit.text.toString().trim(); val a = r.file
            if (!down && text.isEmpty() && a == null) { info.text = "Say or type something first"; return@setOnClickListener }
            isEnabled = false; info.text = "Sending..."
            send(id, if (down) "down" else if (a != null) "voice" else "text", text, raw, tx, a) { isEnabled = true; info.text = "Not sent: try again" }
        } })
        box.addView(info); box.addView(row); box.addView(edit, LinearLayout.LayoutParams(-1, -2))
    }

    private fun send(id: String, kind: String, text: String, raw: String, tx: String, audio: java.io.File?, failed: () -> Unit = {}) {
        Thread {
            val r = Feedback.reply(this, id, kind, text, raw, tx, audio)
            runOnUiThread {
                r.onSuccess { rec?.clear()
                    toast(when (kind) { "up" -> "Marked verified fixed"; "down" -> "Reopened: still broken"; else -> "Reply sent" }); load() }
                r.onFailure { toast("Not sent: ${it.message}"); failed() }
            }
        }.start()
    }

    private fun toast(t: String) = android.widget.Toast.makeText(this, t, android.widget.Toast.LENGTH_LONG).show()

    private fun small(t: String) = TextView(this).apply { text = t; textSize = 13f; alpha = 0.75f; setPadding(0, (3 * dp).toInt(), 0, 0) }

    /** a bundle image, fetched with the token (thumbnails halved: the marked screenshot is 4x the game's picture) */
    private fun image(id: String, name: String, iv: ImageView, sample: Int = 2) {
        val k = "$id/$name/$sample"
        images[k]?.let { iv.setImageBitmap(it); return }
        Thread {
            val b = try { get("mine/file/$id/$name")?.takeIf { it.responseCode == 200 }?.inputStream?.use {
                BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) } } catch (x: Exception) { null }
            if (b != null) runOnUiThread { images[k] = b; iv.setImageBitmap(b) }
        }.start()
    }

    private fun full(id: String, name: String) {
        val iv = ImageView(this).apply { adjustViewBounds = true; setBackgroundColor(Color.BLACK) }
        image(id, name, iv, 1)
        android.app.Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen).apply {
            setContentView(iv); iv.setOnClickListener { dismiss() }; show() }
    }

    /** the voice, streamed with the token; the same button stops it */
    private fun play(b: Button, id: String, name: String) = play(b, "mine/file/$id/$name")
    private fun play(b: Button, path: String) {
        val was = playing
        player?.release(); player = null; playing?.text = "▶ Voice"; playing = null
        if (was === b) return
        Thread {
            val tok = Auth.token(this)
            val u = Feedback.url(this, path) ?: return@Thread
            runOnUiThread {
                try {
                    player = MediaPlayer().apply {
                        setDataSource(this@FeedbackListActivity, Uri.parse(u.toString()), mapOf("Authorization" to "Bearer $tok"))
                        setOnPreparedListener { it.start() }
                        setOnCompletionListener { b.text = "▶ Voice"; if (playing === b) playing = null }
                        prepareAsync()
                    }
                    b.text = "■ Stop"; playing = b
                } catch (x: Exception) { android.widget.Toast.makeText(this, "Cannot play: ${x.message}", android.widget.Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }
}
