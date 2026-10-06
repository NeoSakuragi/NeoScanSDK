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
    private var filter = "open"                                        // open | ready | all
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
            text = "You run game v$running (build ${RomFetch.installedBuild(this@FeedbackListActivity)}), player ${BuildConfig.VERSION_NAME}" })
        filter = getSharedPreferences("feedback", 0).getString("listFilter", "open") ?: "open"
        filters = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, (6 * dp).toInt(), 0, (6 * dp).toInt()) }
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
            runOnUiThread {
                r.onFailure { msg(it.message ?: "?") }
                r.onSuccess { j -> rows = j.getJSONArray("rows"); user = j.optString("user"); render() }
            }
        }.start()
    }

    private fun matches(r: JSONObject, f: String) = when (f) {
        "open" -> Feedback.isOpen(r); "ready" -> Feedback.isReady(r, running); else -> true }

    /** the filter buttons (with their counts) and the cards they keep; the scroll position stays */
    private fun render() {
        val y = scroll.scrollY
        filters.removeAllViews()
        for ((k, t) in listOf("open" to "Open", "ready" to "Shipped: test it", "all" to "All")) {
            val n = (0 until rows.length()).count { matches(rows.getJSONObject(it), k) }
            filters.addView(Button(this).apply {
                text = (if (filter == k) "● " else "") + "$t ($n)"; isAllCaps = false; setTypeface(typeface, if (filter == k) Typeface.BOLD else Typeface.NORMAL)
                setOnClickListener { filter = k; getSharedPreferences("feedback", 0).edit().putString("listFilter", k).apply(); render(); scroll.scrollTo(0, 0) }
            }, LinearLayout.LayoutParams(0, -2, 1f))
        }
        list.removeAllViews()
        val shown = (0 until rows.length()).map { rows.getJSONObject(it) }.filter { matches(it, filter) }
        list.addView(TextView(this).apply { text = "$user: ${shown.size} of ${rows.length()} note" + (if (rows.length() == 1) "" else "s") + ", newest first"
            textSize = 13f; alpha = 0.7f; setPadding(0, (4 * dp).toInt(), 0, (8 * dp).toInt()) })
        if (rows.length() == 0) msg("No notes yet: hold the mic button in the game and talk, or tap it to type.")
        else if (shown.isEmpty()) list.addView(TextView(this).apply { textSize = 15f; setPadding(0, (16 * dp).toInt(), 0, 0)
            text = if (filter == "ready") "Nothing shipped to test in v$running." else "No open notes." })
        for (r in shown) list.addView(card(r))
        scroll.post { scroll.scrollTo(0, y) }
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

    private fun card(r: JSONObject): View {
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; val m = (12 * dp).toInt(); setPadding(m, m, m, m)
            background = GradientDrawable().apply { setColor(Color.rgb(30, 30, 36)); setStroke(maxOf(1, dp.toInt()), Color.rgb(90, 90, 100)); cornerRadius = 8 * dp }
        }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        top.addView(TextView(this).apply { text = when_(r.optString("created")); textSize = 15f; setTypeface(typeface, Typeface.BOLD) }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(TextView(this).apply {                          // the status: a bordered label, the word itself carries it
            text = statusText(r); textSize = 13f; setTypeface(typeface, Typeface.BOLD); setTextColor(Color.WHITE)
            val m = (6 * dp).toInt(); setPadding(m, m / 2, m, m / 2)
            background = GradientDrawable().apply { setStroke(maxOf(2, (1.5f * dp).toInt()), Color.WHITE); cornerRadius = 4 * dp }
        })
        c.addView(top)
        c.addView(small("game v${r.optString("game_version")}, player ${r.optString("apk_version")}"))
        c.addView(small("sent from ${r.optString("device").ifEmpty { "?" }}" + r.optString("android").let { if (it.isEmpty() || it == "null") "" else ", Android $it" } +
                        ", IP ${r.optString("ip").ifEmpty { "?" }.replace("null", "?")}, install ${r.optString("install_id").take(8)}"))
        val text = r.optString("final_text").ifEmpty { r.optString("raw_transcript") }
        c.addView(TextView(this).apply { this.text = text.ifEmpty { "(no text)" }; textSize = 16f; setPadding(0, (8 * dp).toInt(), 0, 0)
            if (r.optString("final_text").isEmpty()) setTypeface(typeface, Typeface.ITALIC) })
        val tags = listOfNotNull(r.optString("category").ifEmpty { null }?.let { "category: $it" },
                                 r.optString("fighters").ifEmpty { null }?.let { "fighters: $it" })
        if (tags.isNotEmpty()) c.addView(small(tags.joinToString("   ")))
        if (r.optString("notes").isNotEmpty()) c.addView(TextView(this).apply {
            this.text = "Developer's notes: " + r.optString("notes"); textSize = 14f; setPadding(0, (8 * dp).toInt(), 0, 0) })
        val shot = r.optString("screen")
        val audio = r.optString("audio_path")
        if (shot.isNotEmpty() || audio.isNotEmpty()) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, (10 * dp).toInt(), 0, 0) }
            if (shot.isNotEmpty()) {
                val iv = ImageView(this).apply { adjustViewBounds = true; scaleType = ImageView.ScaleType.FIT_START; contentDescription = "screenshot"
                    maxWidth = (360 * dp).toInt() }                    // a thumbnail: tap = full screen
                row.addView(iv, LinearLayout.LayoutParams(-2, -2))
                row.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
                image(r.optString("id"), shot, iv)
                iv.setOnClickListener { full(r.optString("id"), shot) }
            }
            if (audio.isNotEmpty()) row.addView(Button(this).apply { this.text = "▶ Voice"; setOnClickListener { play(this, r.optString("id"), audio) } },
                                                LinearLayout.LayoutParams(-2, -2).apply { leftMargin = (8 * dp).toInt() })
            c.addView(row)
        }
        val h = r.optJSONArray("history")
        if (h != null && h.length() > 0) {
            c.addView(small("History").apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (10 * dp).toInt(), 0, 0) })
            for (i in 0 until h.length()) {
                val e = h.getJSONObject(i)
                val from = e.optString("from_status"); val to = e.optString("to_status")
                val what = if (from.isEmpty()) to else if (from == to) "" else "$from → $to"
                val note = e.optString("note")
                c.addView(small("${when_(e.optString("at"))}  " + listOf(what, note).filter { it.isNotEmpty() }.joinToString(": ") + "  (${e.optString("by")})"))
            }
        }
        thread(c, r)
        return LinearLayout(this).apply { setPadding(0, 0, 0, (12 * dp).toInt()); addView(c, LinearLayout.LayoutParams(-1, -2)) }
    }

    /** the note's reply thread (oldest first) and its actions: thumbs up / thumbs down / Reply */
    private fun thread(c: LinearLayout, r: JSONObject) {
        val id = r.optString("id")
        val rep = r.optJSONArray("replies")
        if (rep != null && rep.length() > 0) {
            c.addView(small("Your replies").apply { setTypeface(typeface, Typeface.BOLD); setPadding(0, (10 * dp).toInt(), 0, 0) })
            for (i in 0 until rep.length()) {
                val x = rep.getJSONObject(i)
                val kind = when (x.optString("kind")) { "up" -> "👍 Fixed"; "down" -> "👎 Still broken"; "voice" -> "Voice"; else -> "Text" }
                val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                line.addView(TextView(this).apply { textSize = 14f; setPadding(0, (4 * dp).toInt(), 0, 0)
                    text = "${when_(x.optString("at"))}  $kind" + x.optString("text").let { if (it.isEmpty()) "" else ": $it" } },
                    LinearLayout.LayoutParams(0, -2, 1f))
                val a = x.optString("audio_path")
                if (a.isNotEmpty()) line.addView(Button(this).apply { text = "▶ Voice"; setOnClickListener { play(this, id, a) } })
                c.addView(line)
            }
        }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val acts = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, (8 * dp).toInt(), 0, 0) }
        fun act(t: String, f: () -> Unit) = Button(this).apply { text = t; isAllCaps = false; setOnClickListener { f() } }
        acts.addView(act("👍 Fixed") {
            android.app.AlertDialog.Builder(this).setMessage("Verified fixed in v$running?")
                .setPositiveButton("Yes, fixed") { _, _ -> send(id, "up", "", "", "", null) }.setNegativeButton("No", null).show()
        }, LinearLayout.LayoutParams(0, -2, 1f))
        acts.addView(act("👎 Still broken") { composer(box, id, true) }, LinearLayout.LayoutParams(0, -2, 1f))
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
    private fun play(b: Button, id: String, name: String) {
        val was = playing
        player?.release(); player = null; playing?.text = "▶ Voice"; playing = null
        if (was === b) return
        Thread {
            val tok = Auth.token(this)
            val u = Feedback.url(this, "mine/file/$id/$name") ?: return@Thread
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
