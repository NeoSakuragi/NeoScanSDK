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
    override fun attachBaseContext(base: android.content.Context) { super.attachBaseContext(Lang.wrap(base)); Lang.init(base) }
    companion object {
        /** a note's status as one word (the profile menu's "Reply to which note?" too) */
        fun statusWord(ctx: android.content.Context, s: String): String = when (s) {
            "new" -> ctx.getString(R.string.st_new); "read" -> ctx.getString(R.string.st_read); "in_progress" -> ctx.getString(R.string.st_in_progress)
            "fixed" -> ctx.getString(R.string.st_fixed); "shipped" -> ctx.getString(R.string.st_shipped); "wont_do" -> ctx.getString(R.string.st_wont_do)
            "duplicate" -> ctx.getString(R.string.st_duplicate); "verified" -> ctx.getString(R.string.st_verified); "reopened" -> ctx.getString(R.string.st_reopened)
            else -> s.uppercase()
        }
    }
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
        title = getString(R.string.app_feedback)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; val m = (14 * dp).toInt(); setPadding(m, 0, m, m * 2) }
        head = TextView(this).apply { gravity = Gravity.CENTER; textSize = 13f; alpha = 0.7f; height = 0; text = getString(R.string.release_refresh) }
        col.addView(head, LinearLayout.LayoutParams(-1, -2))
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (12 * dp).toInt(), 0, 0) }
        top.addView(TextView(this).apply { text = getString(R.string.list_title); textSize = 24f; setTypeface(typeface, Typeface.BOLD) }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(Button(this).apply { text = getString(R.string.refresh); setOnClickListener { load() } })
        col.addView(top)
        col.addView(TextView(this).apply { textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0)
            text = getString(R.string.list_you_run, running, RomFetch.loadedBuild(this@FeedbackListActivity).let { if (it == 0L) getString(R.string.list_local) else "$it" }, BuildConfig.VERSION_NAME) })
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

    /** pull down at the top: the header grows (getString(R.string.release_refresh)); released far enough = [load] */
    private inner class PullScroll : ScrollView(this@FeedbackListActivity) {
        private var y0 = -1f
        private val need = 70 * dp
        override fun dispatchTouchEvent(e: MotionEvent): Boolean {
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> y0 = if (scrollY == 0) e.y else -1f
                MotionEvent.ACTION_MOVE -> if (y0 >= 0 && scrollY == 0) {
                    val d = ((e.y - y0) / 2).coerceIn(0f, need * 1.5f)
                    head.height = d.toInt(); head.text = getString(if (d >= need) R.string.release_refresh else R.string.pull_refresh)
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
        if (list.childCount == 0) msg(getString(R.string.loading))
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
        if (!Auth.admin(this) && (filter == "decisions" || filter == "answered")) filter = "open"
        for (row in listOf(listOf("open" to getString(R.string.f_open), "ready" to getString(R.string.f_ready), "all" to getString(R.string.f_all)),
                           listOf("decisions" to getString(R.string.f_decisions), "answered" to getString(R.string.f_answered))).take(if (Auth.admin(this)) 2 else 1)) {   // 0.0.37: decisions = admins
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
                text = if (filter == "decisions") resources.getQuantityString(R.plurals.dec_waiting, shown.size, user, shown.size)
                       else getString(R.string.dec_answered_n, user, shown.size) })
            if (shown.isEmpty()) list.addView(TextView(this).apply { textSize = 15f; setPadding(0, (16 * dp).toInt(), 0, 0)
                text = getString(if (filter == "decisions") R.string.dec_none else R.string.dec_none_answered) })
            for (v in shown) list.addView(decisionCard(v))
            scroll.post { scroll.scrollTo(0, y) }
            return
        }
        val shown = (0 until rows.length()).map { rows.getJSONObject(it) }.filter { matches(it, filter) }
        list.addView(TextView(this).apply { text = resources.getQuantityString(R.plurals.list_count, rows.length(), user, shown.size, rows.length())
            textSize = 13f; alpha = 0.7f; setPadding(0, (4 * dp).toInt(), 0, (8 * dp).toInt()) })
        val q = (0 until rows.length()).map { rows.getJSONObject(it) }.filter { Feedback.wantsTest(it, running) && testable(it) }.reversed()
        if (q.isNotEmpty()) list.addView(Button(this).apply { text = "▶ " + getString(R.string.menu_test_queue, q.size); isAllCaps = false
            setOnClickListener { verify(q) } }, LinearLayout.LayoutParams(-1, -2))
        if (rows.length() == 0) msg(getString(R.string.list_empty))
        else if (shown.isEmpty()) list.addView(TextView(this).apply { textSize = 15f; setPadding(0, (16 * dp).toInt(), 0, 0)
            text = if (filter == "ready") getString(R.string.list_none_ready, running) else getString(R.string.list_none_open) })
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
        c.addView(TextView(this).apply { text = getString(R.string.dec_head, id) + v.optString("title"); textSize = 15f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE) })
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (2 * dp).toInt(), 0, (6 * dp).toInt()) }
        top.addView(TextView(this).apply { text = getString(R.string.dec_asked, Feedback.ago(v.optString("created"))) + v.optString("todo").let { if (it.isEmpty()) "" else ", TODO #$it" }; textSize = 13f; alpha = 0.8f },
            LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(TextView(this).apply {
            text = getString(if (Decisions.isOpen(v)) R.string.dec_waiting_you else R.string.dec_answered); textSize = 12f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
            val m = (5 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
            background = GradientDrawable().apply { setStroke(maxOf(2, (1.5f * dp).toInt()), Color.WHITE); cornerRadius = 4 * dp }
        })
        c.addView(top)
        c.addView(TextView(this).apply { text = v.optString("question"); textSize = 21f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE); setPadding(0, 0, 0, (6 * dp).toInt()) })
        val opts = v.optJSONArray("options") ?: org.json.JSONArray()
        val labels = (0 until opts.length()).map { opts.getJSONObject(it).optString("label") }
        c.addView(small(getString(R.string.dec_what_each)).apply { setTypeface(typeface, Typeface.BOLD) })
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
        c.addView(small(getString(R.string.dec_tap_pic)).apply { setPadding(0, (4 * dp).toInt(), 0, 0) })
        val answerBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (!Decisions.isOpen(v)) {
            c.addView(TextView(this).apply { text = getString(R.string.dec_your_answer, v.optString("answer")); textSize = 18f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
                setPadding(0, (12 * dp).toInt(), 0, 0) })
            c.addView(small(getString(R.string.dec_answered_when, Feedback.ago(v.optString("answered_at")), Feedback.local(v.optString("answered_at")), v.optString("answer_source"))))
            v.optString("answer_text").takeIf { it.isNotEmpty() }?.let { c.addView(TextView(this).apply { text = getString(R.string.your_note, it); textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0) }) }
            v.optString("answer_audio").takeIf { it.isNotEmpty() }?.let { a -> c.addView(Button(this).apply { text = getString(R.string.voice_play); setOnClickListener { play(this, "mine/review/$id/$a") } }, LinearLayout.LayoutParams(-2, -2)) }
            c.addView(Button(this).apply { text = getString(R.string.dec_change); isAllCaps = false; setOnClickListener { visibility = View.GONE; answerer(answerBox, id, labels, opts) } },
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
        val info = small(getString(R.string.dec_note_info)).apply { setPadding(0, (12 * dp).toInt(), 0, 0) }
        val edit = android.widget.EditText(this).apply { minLines = 2; maxLines = 6; gravity = Gravity.TOP or Gravity.START; hint = getString(R.string.dec_note_hint)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        val mic = Button(this).apply { text = getString(R.string.hold_to_talk); isAllCaps = false }
        mic.setOnTouchListener { vv, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED && Feedback.testAudio(this) == null) {
                        requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 2); return@setOnTouchListener true }
                    rec?.clear(); rec = r
                    if (r.start()) { mic.text = getString(R.string.rec_release_stop); info.text = getString(R.string.recording) } else info.text = getString(R.string.mic_unavailable)
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    mic.text = getString(R.string.hold_to_talk)
                    val f = r.stop()
                    if (f == null) info.text = getString(R.string.too_short)
                    else { info.text = getString(R.string.transcribing)
                        Thread { val t = Feedback.transcribeFile(this, f)
                            runOnUiThread {
                                if (t == null) info.text = getString(R.string.tx_unavail_answer)
                                else { raw = t.first; tx = t.third; info.text = getString(R.string.dec_correct_pick)
                                    edit.setText((edit.text.toString().trim() + " " + t.first).trim()); edit.setSelection(edit.text.length) }
                            } }.start() }
                    vv.performClick()
                }
            }
            true
        }
        box.addView(info); box.addView(mic, LinearLayout.LayoutParams(-1, -2)); box.addView(edit, LinearLayout.LayoutParams(-1, -2))
        box.addView(small(getString(R.string.dec_your_answer_lbl)).apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (8 * dp).toInt(), 0, 0) })
        for (k in labels.indices) {
            val label = labels[k]; val effect = opts.getJSONObject(k).optString("effect")
            box.addView(Button(this).apply {
                text = label; textSize = 17f; isAllCaps = false; minHeight = (64 * dp).toInt(); setTypeface(typeface, Typeface.BOLD)
                setOnClickListener {
                    val note = edit.text.toString().trim(); val a = r.file
                    if (label.lowercase().startsWith("needs work") && note.isEmpty()) { info.text = getString(R.string.dec_needs_note, label); toast(info.text.toString()); return@setOnClickListener }
                    android.app.AlertDialog.Builder(this@FeedbackListActivity).setTitle(label)
                        .setMessage("$effect" + (if (note.isNotEmpty()) "\n\n" + getString(R.string.your_note, note) else "") + (if (a != null) "\n\n" + getString(R.string.with_voice) else ""))
                        .setPositiveButton(getString(R.string.dec_send_answer)) { _, _ ->
                            info.text = getString(R.string.sending)
                            Thread { val res = Decisions.answer(this@FeedbackListActivity, id, label, note, raw, tx, a)
                                runOnUiThread {
                                    res.onSuccess { r.clear(); toast(getString(R.string.dec_answer_sent, label)); load() }
                                    res.onFailure { info.text = getString(R.string.not_sent, it.message); toast(getString(R.string.not_sent, it.message)) }
                                } }.start()
                        }.setNegativeButton(getString(R.string.back), null).show()
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
        "shipped" -> getString(R.string.status_shipped_rel, r.optString("release"))
        "duplicate" -> getString(R.string.status_dup_of, r.optString("duplicate_of"))
        else -> statusWord(this, s)
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
        val title = r.optString("title").takeIf { it.isNotEmpty() && it != "null" } ?: text.take(70).ifEmpty { getString(R.string.no_text) }
        c.addView(TextView(this).apply { this.text = title; textSize = 18f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE) })
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (2 * dp).toInt(), 0, (6 * dp).toInt()) }
        top.addView(TextView(this).apply { this.text = getString(R.string.card_ago_on, Feedback.ago(r.optString("created")), r.optString("game_version")); textSize = 14f; alpha = 0.8f
            setOnLongClickListener { toast(when_(r.optString("created")) + "  " + getString(R.string.card_versions, r.optString("game_version"), r.optString("apk_version"))); true } },
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
                contentDescription = getString(if (can) R.string.cd_verify else R.string.cd_screenshot) }
            frame.addView(iv, android.widget.FrameLayout.LayoutParams(minOf((420 * dp).toInt(), resources.displayMetrics.widthPixels - (60 * dp).toInt()), -2))
            frame.addView(TextView(this).apply { this.text = if (can) getString(R.string.test_it) else getString(R.string.no_test_yet); textSize = if (can) 15f else 11f
                setTypeface(typeface, Typeface.BOLD); setTextColor(if (can) Color.BLACK else Color.WHITE)
                val m = (6 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
                background = GradientDrawable().apply { setColor(if (can) Color.WHITE else Color.argb(200, 0, 0, 0)); setStroke((1.5f * dp).toInt(), if (can) Color.BLACK else Color.WHITE); cornerRadius = 4 * dp }
            }, android.widget.FrameLayout.LayoutParams(-2, -2, Gravity.TOP or Gravity.START).apply { val m = (6 * dp).toInt(); setMargins(m, m, m, m) })
            image(id, shot, iv)
            frame.setOnClickListener { if (can) verify(listOf(r)) else full(id, shot) }
            c.addView(frame, LinearLayout.LayoutParams(-2, -2))
        } else if (can) c.addView(Button(this).apply { this.text = getString(R.string.test_it); setOnClickListener { verify(listOf(r)) } })
        val rel = r.optString("release")
        if (rel.isNotEmpty() && r.optString("status") in setOf("shipped", "verified", "reopened")) c.addView(TextView(this).apply {
            this.text = getString(R.string.card_fix_rel, rel); textSize = 14f; setTypeface(Typeface.MONOSPACE, Typeface.BOLD); setTextColor(Color.WHITE); setPadding(0, (8 * dp).toInt(), 0, 0) })
        r.optString("fix").takeIf { it.isNotEmpty() && it != "null" }?.let { c.addView(TextView(this).apply { this.text = getString(R.string.card_fix, it); textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0) }) }
        r.optString("rca").takeIf { it.isNotEmpty() && it != "null" }?.let { c.addView(TextView(this).apply { this.text = getString(R.string.card_cause, it); textSize = 14f; alpha = 0.85f; setPadding(0, (2 * dp).toInt(), 0, 0) }) }
        // More (collapsed): his latest reply, the note as sent, the voice, the timeline, the origin
        val more = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE }
        val open = expanded.contains(id)
        if (open) more.visibility = View.VISIBLE
        c.addView(Button(this).apply { this.text = if (open) getString(R.string.less) else getString(R.string.more); isAllCaps = false; setOnClickListener {
            if (more.visibility == View.GONE) { more.visibility = View.VISIBLE; this.text = getString(R.string.less); expanded.add(id) }
            else { more.visibility = View.GONE; this.text = getString(R.string.more); expanded.remove(id) } } },
            LinearLayout.LayoutParams(-2, -2).apply { topMargin = (6 * dp).toInt() })
        val rep = r.optJSONArray("replies")
        val last = rep?.let { a -> (a.length() - 1 downTo 0).map { a.getJSONObject(it) }.firstOrNull { it.optString("text").isNotEmpty() } }
        if (last != null) more.addView(TextView(this).apply { this.text = getString(R.string.card_latest_reply, Feedback.ago(last.optString("at")), last.optString("text")); textSize = 14f })
        more.addView(TextView(this).apply { this.text = getString(R.string.your_note, text.ifEmpty { getString(R.string.no_text) }); textSize = 14f; setPadding(0, (6 * dp).toInt(), 0, 0) })
        val tags = listOfNotNull(r.optString("category").ifEmpty { null }?.let { getString(R.string.card_category, it) }, r.optString("fighters").ifEmpty { null }?.let { getString(R.string.card_fighters, it) })
        if (tags.isNotEmpty()) more.addView(small(tags.joinToString("   ")))
        if (r.optString("notes").isNotEmpty()) more.addView(small(getString(R.string.card_dev_notes, r.optString("notes"))))
        val audio = r.optString("audio_path")
        if (audio.isNotEmpty()) more.addView(Button(this).apply { this.text = getString(R.string.voice_play); setOnClickListener { play(this, id, audio) } }, LinearLayout.LayoutParams(-2, -2))
        if (rep != null) for (k in 0 until rep.length()) { val x = rep.getJSONObject(k); val a = x.optString("audio_path")
            if (a.isNotEmpty()) more.addView(Button(this).apply { this.text = getString(R.string.card_reply_voice, Feedback.ago(x.optString("at"))); isAllCaps = false; setOnClickListener { play(this, id, a) } }, LinearLayout.LayoutParams(-2, -2)) }
        val tl = r.optJSONArray("timeline")
        if (tl != null && tl.length() > 0) {
            more.addView(small(getString(R.string.card_timeline)).apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (8 * dp).toInt(), 0, 0) })
            for (k in 0 until tl.length()) { val e = tl.getJSONObject(k)
                more.addView(small("${when_(e.optString("at"))}  ${e.optString("kind").replace('_', ' ').uppercase()}  ${e.optString("text")}  (${e.optString("by")})")) }
        }
        more.addView(small(getString(R.string.card_sent_from, r.optString("device").ifEmpty { "?" }) + r.optString("android").let { if (it.isEmpty() || it == "null") "" else ", Android $it" } +
                           ", " + getString(R.string.card_origin, r.optString("ip").ifEmpty { "?" }.replace("null", "?"), r.optString("apk_version"), r.optString("install_id").take(8))).apply { setPadding(0, (8 * dp).toInt(), 0, 0) })
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
        acts.addView(act(getString(R.string.act_fixed)) {
            android.app.AlertDialog.Builder(this).setMessage(getString(R.string.act_fixed_q, running))
                .setPositiveButton(getString(R.string.act_yes_fixed)) { _, _ -> send(id, "up", "", "", "", null) }.setNegativeButton(getString(R.string.no), null).show()
        }, LinearLayout.LayoutParams(0, -2, 1f))
        acts.addView(act(getString(R.string.act_broken)) { composer(box, id, true) }, LinearLayout.LayoutParams(0, -2, 1f))
        acts.addView(act(getString(R.string.act_reply)) { composer(box, id, false) }, LinearLayout.LayoutParams(0, -2, 1f))
        c.addView(acts); c.addView(box)
    }

    /** the reply box under a note: hold to talk (recorded, transcribed, the text editable) or type; [down] = the thumbs
     *  down with an optional reply */
    private fun composer(box: LinearLayout, id: String, down: Boolean) {
        rec?.clear(); box.removeAllViews()
        var raw = ""; var tx = ""
        val r = Feedback.VoiceRec(this).also { rec = it }
        val info = small(getString(if (down) R.string.comp_down_info else R.string.comp_info))
        val edit = android.widget.EditText(this).apply { minLines = 2; maxLines = 6; gravity = Gravity.TOP or Gravity.START
            hint = getString(if (down) R.string.comp_down_hint else R.string.comp_hint)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        val mic = Button(this).apply { text = getString(R.string.hold_to_talk); isAllCaps = false }
        mic.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED && Feedback.testAudio(this) == null) {
                        requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 2); return@setOnTouchListener true }
                    if (r.start()) { mic.text = getString(R.string.rec_release_stop); info.text = getString(R.string.recording) } else info.text = getString(R.string.mic_unavailable)
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    mic.text = getString(R.string.hold_to_talk)
                    val f = r.stop()
                    if (f == null) info.text = getString(R.string.too_short)
                    else {
                        info.text = getString(R.string.transcribing)
                        Thread {
                            val t = Feedback.transcribeFile(this, f)
                            runOnUiThread {
                                if (t == null) info.text = getString(R.string.tx_unavail_reply)
                                else { raw = t.first; tx = t.third; info.text = getString(R.string.comp_correct_send)
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
        row.addView(Button(this).apply { text = getString(R.string.cancel); setOnClickListener { r.clear(); box.removeAllViews() } })
        row.addView(Button(this).apply { text = getString(if (down) R.string.send_still_broken else R.string.send); isAllCaps = false; setOnClickListener {
            val text = edit.text.toString().trim(); val a = r.file
            if (!down && text.isEmpty() && a == null) { info.text = getString(R.string.say_something); return@setOnClickListener }
            isEnabled = false; info.text = getString(R.string.sending)
            send(id, if (down) "down" else if (a != null) "voice" else "text", text, raw, tx, a) { isEnabled = true; info.text = getString(R.string.not_sent_retry) }
        } })
        box.addView(info); box.addView(row); box.addView(edit, LinearLayout.LayoutParams(-1, -2))
    }

    private fun send(id: String, kind: String, text: String, raw: String, tx: String, audio: java.io.File?, failed: () -> Unit = {}) {
        Thread {
            val r = Feedback.reply(this, id, kind, text, raw, tx, audio)
            runOnUiThread {
                r.onSuccess { rec?.clear()
                    toast(getString(when (kind) { "up" -> R.string.marked_verified; "down" -> R.string.reopened_broken; else -> R.string.reply_sent })); load() }
                r.onFailure { toast(getString(R.string.not_sent, it.message)); failed() }
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
        player?.release(); player = null; playing?.text = getString(R.string.voice_play); playing = null
        if (was === b) return
        Thread {
            val tok = Auth.token(this)
            val u = Feedback.url(this, path) ?: return@Thread
            runOnUiThread {
                try {
                    player = MediaPlayer().apply {
                        setDataSource(this@FeedbackListActivity, Uri.parse(u.toString()), mapOf("Authorization" to "Bearer $tok"))
                        setOnPreparedListener { it.start() }
                        setOnCompletionListener { b.text = getString(R.string.voice_play); if (playing === b) playing = null }
                        prepareAsync()
                    }
                    b.text = getString(R.string.stop); playing = b
                } catch (x: Exception) { android.widget.Toast.makeText(this, getString(R.string.cannot_play, x.message), android.widget.Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }
}
